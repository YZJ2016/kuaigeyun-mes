"""manual_create_auto_lifecycle：全局/单证开关、skip 语义、submitter 注册与失败可见性。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.kuaizhizao.services import manual_create_auto_lifecycle as m


def test_flat_param_key_and_defaults_cover_all_docs():
    assert m.flat_param_key_for_doc("purchase_order") == "manual_create_doc_purchase_order"
    defaults = m.default_manual_create_doc_params()
    assert len(defaults) == len(m.MANUAL_CREATE_LIFECYCLE_DOCS)
    assert all(v is False for v in defaults.values())
    keys = m.parameter_keys_for_manual_create_lifecycle()
    assert keys[0] == "parameters.automation.manual_create_auto_submit"
    assert "parameters.automation.manual_create_doc_purchase_order" in keys


@pytest.mark.asyncio
async def test_unknown_node_key_not_enabled():
    assert (
        await m.is_manual_create_auto_submit_enabled(1, "no_such_node")
    ) is False


@pytest.mark.asyncio
async def test_apply_returns_false_when_disabled(monkeypatch):
    monkeypatch.setattr(m, "is_manual_create_auto_submit_enabled", AsyncMock(return_value=False))
    called = []

    async def fake_submit(tid, eid, oid):
        called.append((tid, eid, oid))

    monkeypatch.setattr(m, "_resolve_submitter", lambda key: fake_submit)
    applied = await m.apply_manual_create_auto_submit(
        tenant_id=1, node_key="purchase_order", entity_id=9, operator_id=7
    )
    assert applied is False
    assert called == []


@pytest.mark.asyncio
async def test_apply_skip_short_circuits(monkeypatch):
    enabled = AsyncMock(return_value=True)
    monkeypatch.setattr(m, "is_manual_create_auto_submit_enabled", enabled)
    applied = await m.apply_manual_create_auto_submit(
        tenant_id=1, node_key="purchase_order", entity_id=9, operator_id=7, skip=True
    )
    assert applied is False
    enabled.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_invokes_registered_submitter(monkeypatch):
    monkeypatch.setattr(m, "is_manual_create_auto_submit_enabled", AsyncMock(return_value=True))
    called = []

    async def fake_submit(tid, eid, oid):
        called.append((tid, eid, oid))

    monkeypatch.setattr(m, "_resolve_submitter", lambda key: fake_submit)
    applied = await m.apply_manual_create_auto_submit(
        tenant_id=1, node_key="purchase_order", entity_id=9, operator_id=7
    )
    assert applied is True
    assert called == [(1, 9, 7)]


@pytest.mark.asyncio
async def test_apply_failure_is_visible_not_silent(monkeypatch, caplog):
    monkeypatch.setattr(m, "is_manual_create_auto_submit_enabled", AsyncMock(return_value=True))

    async def boom(tid, eid, oid):
        raise RuntimeError("submit failed")

    monkeypatch.setattr(m, "_resolve_submitter", lambda key: boom)
    with caplog.at_level("WARNING"):
        applied = await m.apply_manual_create_auto_submit(
            tenant_id=1, node_key="purchase_order", entity_id=9, operator_id=7
        )
    assert applied is False
    assert any("手动建单自动提交失败" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_procurement_submitters_registered():
    for key in (
        "purchase_order",
        "purchase_request",
        "payment_application",
        "purchase_inquiry",
        "purchase_return",
    ):
        assert m._resolve_submitter(key) is not None, key


def test_every_declared_doc_has_registered_submitter():
    for doc in m.MANUAL_CREATE_LIFECYCLE_DOCS:
        assert m._resolve_submitter(doc["node_key"]) is not None, doc["node_key"]
