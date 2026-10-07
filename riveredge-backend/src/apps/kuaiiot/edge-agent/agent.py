#!/usr/bin/env python3
"""快数采 Edge Agent 参考实现：Modbus TCP 轮询 + 断网缓冲 + 心跳热更新。"""

from __future__ import annotations

import json
import sqlite3
import struct
import sys
import time
import uuid
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from pymodbus.client import ModbusTcpClient

AGENT_VERSION = "1.0.0"
BATCH_MAX_ITEMS = 100


@dataclass
class LocalConfig:
    base_url: str
    device_token: str
    edge_config_code: str
    poll_interval_seconds: int = 5
    heartbeat_interval_seconds: int = 30
    buffer_db_path: str = "buffer.db"
    agent_version: str = AGENT_VERSION
    buffer_max_items: int = 10000


class BufferStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_ingest (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE TABLE IF NOT EXISTS runtime_cache (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS command_results (command_uuid TEXT PRIMARY KEY, payload TEXT, delivered INTEGER NOT NULL DEFAULT 0)")

    def save_runtime(self, spec: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO runtime_cache VALUES (1, ?)", (json.dumps(spec),))

    def load_runtime(self) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT payload FROM runtime_cache WHERE id=1").fetchone()
        return json.loads(row[0]) if row else None

    def begin_command(self, command_uuid: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("INSERT OR IGNORE INTO command_results(command_uuid) VALUES (?)", (command_uuid,))
            return cursor.rowcount == 1

    def finish_command(self, command_uuid: str, payload: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE command_results SET payload=? WHERE command_uuid=?", (json.dumps(payload), command_uuid))

    def pending_results(self) -> list[tuple[str, dict]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT command_uuid,payload FROM command_results WHERE delivered=0 LIMIT 100").fetchall()
        return [(key, json.loads(payload) if payload else {"success": False, "error_message": "执行结果未知，需要人工确认，未重复执行"}) for key, payload in rows]

    def acknowledge_result(self, command_uuid: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE command_results SET delivered=1 WHERE command_uuid=?", (command_uuid,))

    def enqueue(self, idempotency_key: str, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO pending_ingest (idempotency_key, payload_json, created_at) VALUES (?, ?, ?)",
                (idempotency_key, json.dumps(payload, ensure_ascii=False), _utc_now_iso()),
            )

    def pending_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM pending_ingest").fetchone()
            return int(row[0] if row else 0)

    def fetch_batch(self, limit: int = BATCH_MAX_ITEMS) -> list[tuple[int, str, dict[str, Any]]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, idempotency_key, payload_json FROM pending_ingest ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(int(row[0]), str(row[1]), json.loads(str(row[2]))) for row in rows]

    def delete_ids(self, ids: list[int]) -> None:
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"DELETE FROM pending_ingest WHERE id IN ({placeholders})", ids)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _load_local_config(path: str) -> LocalConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    base_url = str(data.get("base_url") or "").strip().rstrip("/")
    device_token = str(data.get("device_token") or "").strip()
    edge_config_code = str(data.get("edge_config_code") or "").strip()
    if not base_url or not device_token or not edge_config_code:
        raise ValueError("config.yaml 必须配置 base_url、device_token、edge_config_code")
    return LocalConfig(
        base_url=base_url,
        device_token=device_token,
        edge_config_code=edge_config_code,
        poll_interval_seconds=int(data.get("poll_interval_seconds") or 5),
        heartbeat_interval_seconds=int(data.get("heartbeat_interval_seconds") or 30),
        buffer_db_path=str(data.get("buffer_db_path") or "buffer.db"),
        agent_version=str(data.get("agent_version") or AGENT_VERSION),
        buffer_max_items=max(1, int(data.get("buffer_max_items") or 10000)),
    )


class CloudClient:
    def __init__(self, local: LocalConfig) -> None:
        self.local = local
        self.runtime_spec: dict[str, Any] | None = None
        self.config_version: int | None = None
        self.trial_result: dict | None = None

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.local.base_url}{path}"

    def pull_runtime_config(self) -> dict[str, Any]:
        path = f"/api/v1/apps/kuaiiot/edge-runtime/{self.local.device_token}/config/{self.local.edge_config_code}"
        with httpx.Client(timeout=20.0) as client:
            response = client.get(self._url(path))
            response.raise_for_status()
            spec = response.json()
        self.runtime_spec = spec
        self.config_version = int(spec.get("config_version") or 1)
        return spec

    def heartbeat(self, buffer_pending_count: int) -> dict[str, Any]:
        path = str((self.runtime_spec or {}).get("heartbeat_path") or f"/api/v1/apps/kuaiiot/edge-runtime/{self.local.device_token}/heartbeat")
        payload = {
            "edge_config_code": self.local.edge_config_code,
            "config_version": self.config_version or 0,
            "agent_version": self.local.agent_version,
            "buffer_pending_count": buffer_pending_count,
            "status": "buffer_full" if buffer_pending_count >= self.local.buffer_max_items else "online",
            "trial_result": self.trial_result,
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(self._url(path), json=payload)
            response.raise_for_status()
            return response.json()

    def submit_command_result(
        self,
        command_uuid: str,
        *,
        success: bool,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        if not self.runtime_spec:
            raise RuntimeError("runtime spec 未加载")
        path = str(self.runtime_spec.get("command_result_path") or "")
        payload = {
            "command_uuid": command_uuid,
            "success": success,
            "result": result,
            "error_message": error_message,
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(self._url(path), json=payload)
            response.raise_for_status()
            return response.json()

    def ingest(self, tags: dict[str, Any], timestamp: str, idempotency_key: str | None = None) -> dict[str, Any]:
        if not self.runtime_spec:
            raise RuntimeError("runtime spec 未加载")
        path = str(self.runtime_spec.get("ingest_path") or "")
        payload: dict[str, Any] = {"tags": tags, "timestamp": timestamp}
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
        with httpx.Client(timeout=20.0) as client:
            response = client.post(self._url(path), json=payload)
            response.raise_for_status()
            return response.json()

    def ingest_batch(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.runtime_spec:
            raise RuntimeError("runtime spec 未加载")
        path = str(self.runtime_spec.get("batch_ingest_path") or "")
        with httpx.Client(timeout=30.0) as client:
            response = client.post(self._url(path), json={"items": items})
            response.raise_for_status()
            return response.json()


def _decode_register(raw: Any, data_type: str, scale: float = 1.0) -> Any:
    if raw is None:
        return None
    dtype = data_type.lower()
    if dtype == "bool":
        return bool(int(raw))
    if dtype == "int16":
        value = struct.unpack(">h", struct.pack(">H", int(raw) & 0xFFFF))[0]
        return value * scale
    if dtype == "uint16":
        return int(raw) * scale
    if dtype == "int32":
        hi = int(raw[0]) if isinstance(raw, (list, tuple)) else int(raw) >> 16
        lo = int(raw[1]) if isinstance(raw, (list, tuple)) else int(raw) & 0xFFFF
        packed = struct.pack(">HH", hi & 0xFFFF, lo & 0xFFFF)
        value = struct.unpack(">i", packed)[0]
        return value * scale
    if dtype == "uint32":
        hi = int(raw[0]) if isinstance(raw, (list, tuple)) else int(raw) >> 16
        lo = int(raw[1]) if isinstance(raw, (list, tuple)) else int(raw) & 0xFFFF
        packed = struct.pack(">HH", hi & 0xFFFF, lo & 0xFFFF)
        value = struct.unpack(">I", packed)[0]
        return value * scale
    if dtype == "float32":
        if isinstance(raw, (list, tuple)):
            packed = struct.pack(">HH", int(raw[0]) & 0xFFFF, int(raw[1]) & 0xFFFF)
        else:
            packed = struct.pack(">I", int(raw) & 0xFFFFFFFF)
        value = struct.unpack(">f", packed)[0]
        return round(value * scale, 6)
    raise ValueError(f"unsupported data_type: {data_type}")


def _encode_register(value: Any, data_type: str, scale: float = 1.0) -> int | list[int]:
    dtype = data_type.lower()
    if dtype == "bool":
        return 1 if bool(value) else 0
    if dtype in {"int16", "uint16"}:
        scaled = int(float(value) / scale)
        if dtype == "int16":
            return struct.unpack(">H", struct.pack(">h", scaled))[0]
        return scaled & 0xFFFF
    if dtype in {"int32", "uint32", "float32"}:
        if dtype == "float32":
            packed = struct.pack(">f", float(value) / scale)
            hi, lo = struct.unpack(">HH", packed)
            return [hi, lo]
        scaled = int(float(value) / scale)
        if dtype == "int32":
            packed = struct.pack(">i", scaled)
        else:
            packed = struct.pack(">I", scaled & 0xFFFFFFFF)
        hi, lo = struct.unpack(">HH", packed)
        return [hi, lo]
    raise ValueError(f"unsupported data_type: {data_type}")


class ModbusPoller:
    def __init__(self, protocol: str, config: dict[str, Any]) -> None:
        self.protocol = protocol
        self.config = config
        self.client: ModbusTcpClient | None = None

    def connect(self) -> None:
        if self.protocol != "modbus_tcp":
            raise RuntimeError(f"当前 Agent 仅实现 modbus_tcp，收到 {self.protocol}")
        host = str(self.config.get("host") or "127.0.0.1")
        port = int(self.config.get("port") or 502)
        self.client = ModbusTcpClient(host=host, port=port)
        if not self.client.connect():
            raise ConnectionError(f"无法连接 Modbus {host}:{port}")

    def close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None

    def poll_tags(self) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("Modbus 未连接")
        unit_id = int(self.config.get("unit_id") or 1)
        tags: dict[str, Any] = {}
        self.last_raw_values = {}
        for item in self.config.get("registers") or []:
            tag_key = str(item.get("tag_key") or "").strip()
            if not tag_key:
                continue
            try:
                address = int(item.get("address"))
                data_type = str(item.get("data_type") or "uint16").lower()
                scale = float(item.get("scale", 1.0))
                count = 2 if data_type in {"int32", "uint32", "float32"} else 1
                result = self.client.read_holding_registers(address=address, count=count, device_id=unit_id)
                if result.isError():
                    raise RuntimeError(f"读取寄存器失败 tag={tag_key} address={address}: {result}")
                raw = result.registers if count > 1 else result.registers[0]
                self.last_raw_values[tag_key] = raw
                tags[tag_key] = _decode_register(raw, data_type, scale)
            except Exception:
                tags[tag_key] = None
        return tags

    def execute_command(self, command: dict[str, Any]) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("Modbus 未连接")
        edge_action = command.get("edge_action") or {}
        if not isinstance(edge_action, dict):
            raise ValueError("edge_action 无效")
        action_type = str(edge_action.get("type") or "modbus_write")
        if action_type != "modbus_write":
            raise ValueError(f"unsupported edge_action.type: {action_type}")
        params = command.get("params") or {}
        param_key = str(edge_action.get("param_key") or "value")
        raw_value = params.get(param_key)
        if raw_value is None:
            raise ValueError(f"缺少参数: {param_key}")
        address = int(edge_action.get("address"))
        data_type = str(edge_action.get("data_type") or "uint16").lower()
        scale = float(edge_action.get("scale") or 1.0)
        unit_id = int(self.config.get("unit_id") or 1)
        encoded = _encode_register(raw_value, data_type, scale)
        if isinstance(encoded, list):
            result = self.client.write_registers(address=address, values=encoded, device_id=unit_id)
        else:
            result = self.client.write_register(address=address, value=int(encoded), device_id=unit_id)
        if result.isError():
            raise RuntimeError(f"写入寄存器失败 address={address}: {result}")
        return {"address": address, "value": raw_value}


class EdgeAgent:
    def __init__(self, local: LocalConfig) -> None:
        self.local = local
        self.cloud = CloudClient(local)
        self.buffer = BufferStore(local.buffer_db_path)
        self.poller: ModbusPoller | None = None
        self.last_heartbeat_at = 0.0
        self.collection_enabled = True
        self.poller_lock = threading.RLock()

    def reload_runtime(self) -> None:
        old_spec, old_version = self.cloud.runtime_spec, self.cloud.config_version
        candidate = None
        try:
            spec = self.cloud.pull_runtime_config()
            candidate = ModbusPoller(str(spec.get("protocol") or ""), dict(spec.get("config") or {}))
            candidate.connect()
            self.buffer.save_runtime(spec)
        except Exception:
            if candidate:
                candidate.close()
            self.cloud.runtime_spec, self.cloud.config_version = old_spec, old_version
            raise
        with self.poller_lock:
            old = self.poller
            self.poller = candidate
            if old:
                old.close()

    def flush_buffer(self) -> None:
        batch = self.buffer.fetch_batch(BATCH_MAX_ITEMS)
        if not batch:
            return
        items = []
        for _, idempotency_key, payload in batch:
            items.append(
                {
                    "tags": payload["tags"],
                    "timestamp": payload["timestamp"],
                    "idempotency_key": idempotency_key,
                    "qualities": payload.get("qualities", {}),
                }
            )
        try:
            self.cloud.ingest_batch(items)
        except Exception:
            print("batch flush failed; retained for retry")
            return
        self.buffer.delete_ids([row_id for row_id, _, _ in batch])
        print(f"flushed buffered items={len(batch)}")

    def publish_tags(self, tags: dict[str, Any]) -> None:
        if self.buffer.pending_count() >= self.local.buffer_max_items:
            print("buffer full; collection paused")
            return
        timestamp = _utc_now_iso()
        idempotency_key = f"sample-{uuid.uuid4().hex}"
        self.buffer.enqueue(idempotency_key, {"tags": tags, "timestamp": timestamp, "qualities": {key: "bad" for key, value in tags.items() if value is None}})
        self.flush_buffer()

    def flush_command_results(self) -> None:
        for command_uuid, payload in self.buffer.pending_results():
            try:
                self.cloud.submit_command_result(command_uuid, **payload)
            except Exception:
                print("command receipt retained for retry")
                return
            self.buffer.acknowledge_result(command_uuid)

    def maybe_heartbeat(self) -> None:
        now = time.time()
        if now - self.last_heartbeat_at < self.local.heartbeat_interval_seconds:
            return
        self.last_heartbeat_at = now
        try:
            result = self.cloud.heartbeat(self.buffer.pending_count())
            self.collection_enabled = bool(result.get("collection_enabled", True))
            self.flush_command_results()
            if not self.collection_enabled:
                return
            config_applied = True
            if result.get("config_changed"):
                try:
                    self.reload_runtime()
                except Exception:
                    config_applied = False
                    print("config apply failed; retaining last successful runtime")
            trial_uuid = result.get("trial_request_uuid")
            if config_applied and trial_uuid and (not self.cloud.trial_result or self.cloud.trial_result.get("request_uuid") != trial_uuid):
                try:
                    with self.poller_lock:
                        tags = self.poller.poll_tags() if self.poller else {}
                except Exception:
                    tags = {str(item.get("tag_key")): None for item in (self.poller.config.get("registers", []) if self.poller else [])}
                self.cloud.trial_result = {"request_uuid": trial_uuid, "tags": tags, "raw_values": getattr(self.poller, "last_raw_values", {}), "qualities": {key: "bad" if value is None else "good" for key, value in tags.items()}}
            for command in result.get("pending_commands") or []:
                if not isinstance(command, dict):
                    continue
                command_uuid = str(command.get("command_uuid") or "")
                if not command_uuid:
                    continue
                if not self.buffer.begin_command(command_uuid):
                    continue
                try:
                    if not config_applied:
                        self.buffer.finish_command(command_uuid, {"success": False, "error_message": "配置未应用，指令未执行"})
                        continue
                    if not self.poller:
                        self.reload_runtime()
                    with self.poller_lock:
                        exec_result = self.poller.execute_command(command)
                    payload = {"success": True, "result": exec_result}
                except Exception:
                    payload = {"success": False, "error_message": "设备执行失败"}
                self.buffer.finish_command(command_uuid, payload)
            self.flush_command_results()
        except Exception:
            print("heartbeat failed; retry on next interval")

    def _heartbeat_loop(self) -> None:
        while True:
            self.maybe_heartbeat()
            time.sleep(1)

    def run(self) -> None:
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        try:
            self.reload_runtime()
        except Exception:
            cached = self.buffer.load_runtime()
            if cached:
                self.cloud.runtime_spec = cached
                self.cloud.config_version = int(cached.get("config_version") or 1)
                self.poller = ModbusPoller(str(cached.get("protocol") or ""), dict(cached.get("config") or {}))
                try:
                    self.poller.connect()
                except Exception:
                    self.poller.close()
                    self.poller = None
        while True:
            try:
                if self.collection_enabled:
                    if not self.poller:
                        self.reload_runtime()
                    if self.buffer.pending_count() < self.local.buffer_max_items:
                        with self.poller_lock:
                            tags = self.poller.poll_tags()
                        if tags:
                            self.publish_tags(tags)
                    else:
                        self.flush_buffer()
            except Exception:
                print("poll loop failed; heartbeat remains active")
            time.sleep(max(self.local.poll_interval_seconds, 1))


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    local = _load_local_config(config_path)
    EdgeAgent(local).run()


if __name__ == "__main__":
    main()
