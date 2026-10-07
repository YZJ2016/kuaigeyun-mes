import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def agent_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymodbus", MagicMock())
    monkeypatch.setitem(sys.modules, "pymodbus.client", MagicMock())
    path = Path(__file__).parents[3] / "src/apps/kuaiiot/edge-agent/agent.py"
    spec = importlib.util.spec_from_file_location("spec178_agent", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def make_agent(module, tmp_path):
    agent = module.EdgeAgent(module.LocalConfig("https://cloud.invalid", "synthetic", "edge", buffer_db_path=str(tmp_path / "buffer.db")))
    agent.cloud = MagicMock()
    return agent


def test_sample_is_persistent_before_first_send_and_keeps_identity(agent_module, tmp_path):
    agent = make_agent(agent_module, tmp_path)
    def fail(items):
        assert agent.buffer.pending_count() == 1
        assert items[0]["idempotency_key"]
        raise RuntimeError("lost response")
    agent.cloud.ingest_batch.side_effect = fail
    agent.publish_tags({"temp": 20})
    first_key = agent.buffer.fetch_batch()[0][1]
    agent.flush_buffer()
    assert agent.buffer.fetch_batch()[0][1] == first_key


def test_flush_sends_only_one_batch_per_tick(agent_module, tmp_path):
    agent = make_agent(agent_module, tmp_path)
    for i in range(201):
        agent.buffer.enqueue(str(i), {"tags": {}, "timestamp": "2026-10-07T00:00:00Z"})
    agent.flush_buffer()
    assert agent.cloud.ingest_batch.call_count == 1
    assert agent.buffer.pending_count() == 101


def test_failed_new_config_keeps_old_poller(agent_module, tmp_path, monkeypatch):
    agent = make_agent(agent_module, tmp_path)
    old = MagicMock()
    agent.poller = old
    agent.cloud.pull_runtime_config.return_value = {"protocol": "modbus_tcp", "config": {}}
    candidate = MagicMock()
    candidate.connect.side_effect = RuntimeError("PLC unavailable")
    monkeypatch.setattr(agent_module, "ModbusPoller", MagicMock(return_value=candidate))
    with pytest.raises(RuntimeError):
        agent.reload_runtime()
    assert agent.poller is old
    old.close.assert_not_called()


def test_lost_command_receipt_does_not_reexecute(agent_module, tmp_path):
    agent = make_agent(agent_module, tmp_path)
    agent.poller = MagicMock()
    agent.poller.execute_command.return_value = {"written": True}
    agent.cloud.heartbeat.return_value = {"pending_commands": [{"command_uuid": "cmd-one"}]}
    agent.cloud.submit_command_result.side_effect = RuntimeError("network")
    agent.maybe_heartbeat()
    agent.last_heartbeat_at = 0
    agent.maybe_heartbeat()
    assert agent.poller.execute_command.call_count == 1
    assert all(call.kwargs["success"] for call in agent.cloud.submit_command_result.call_args_list)
