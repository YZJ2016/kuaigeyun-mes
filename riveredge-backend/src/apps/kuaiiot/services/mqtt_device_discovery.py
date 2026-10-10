"""从连接源最近 MQTT 报文中发现现场设备（供新建设备下拉选择）。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from apps.kuaiiot.models.iot import (
    IotConnection,
    IotConnectionMessage,
    IotDevice,
    IotDiscoveredMqttDevice,
)
from apps.kuaiiot.services.sanyi_line_adapter import device_external_id

_DEVICE_PAIR_RE = re.compile(
    r'"device_id"\s*:\s*"([^"]+)"\s*,\s*"device_name"\s*:\s*"([^"]+)"'
    r'(?:\s*,\s*"device_key"\s*:\s*"([^"]*)")?',
)

_COMPACT_DEVICE_KEYS = (
    "device_id",
    "device_name",
    "device_key",
    "name",
    "id",
    "line_id",
    "line_name",
    "workshop_id",
    "workshop_name",
    "status",
    "ip",
    "port",
    "unit_id",
    "timestamp",
)


def _pick_str(data: dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def compact_devices_for_store(payload: Any) -> list[dict[str, Any]]:
    """去掉 variables[]，只保留下拉/展示需要的设备身份字段。"""
    if not isinstance(payload, dict):
        return []
    devices = payload.get("devices")
    if not isinstance(devices, list):
        return []
    compact: list[dict[str, Any]] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        item = {key: device[key] for key in _COMPACT_DEVICE_KEYS if key in device}
        if device_external_id(item) or device_external_id(device):
            if "device_id" not in item:
                ext = device_external_id(device)
                if ext:
                    item["device_id"] = ext
            compact.append(item)
    return compact


def compact_payload_for_store(payload: Any, *, max_chars: int) -> Any:
    """超长产线快照：保留 workshop/line/devices 身份，variables 不入库。"""
    if payload is None:
        return None
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"truncated": True, "preview": str(payload)[:max_chars]}
    if len(text) <= max_chars:
        return payload
    if not isinstance(payload, dict):
        return {"truncated": True, "preview": text[:max_chars]}
    compact_devices = compact_devices_for_store(payload)
    stored: dict[str, Any] = {
        "truncated": True,
        "timestamp": payload.get("timestamp"),
        "workshop": payload.get("workshop") if isinstance(payload.get("workshop"), dict) else None,
        "line": payload.get("line") if isinstance(payload.get("line"), dict) else None,
        "devices": compact_devices,
        "preview": text[:max_chars],
    }
    return stored


def _salvage_devices_from_preview(preview: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for match in _DEVICE_PAIR_RE.finditer(preview or ""):
        device_id, device_name, device_key = match.group(1), match.group(2), match.group(3)
        item: dict[str, Any] = {
            "device_id": device_id,
            "device_name": device_name,
        }
        if device_key:
            item["device_key"] = device_key
        results.append(item)
    return results


def _unwrap_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            salvaged = _salvage_devices_from_preview(text)
            return {"devices": salvaged} if salvaged else {}
    if not isinstance(payload, dict):
        return payload
    if not payload.get("truncated"):
        return payload
    devices = payload.get("devices")
    if isinstance(devices, list) and devices:
        return payload
    preview = payload.get("preview")
    if isinstance(preview, str) and preview.strip():
        try:
            parsed = json.loads(preview)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            salvaged = _salvage_devices_from_preview(preview)
            if salvaged:
                return {
                    "workshop": payload.get("workshop"),
                    "line": payload.get("line"),
                    "devices": salvaged,
                }
    return payload


def extract_devices_from_payload(payload: Any) -> list[dict[str, Any]]:
    payload = _unwrap_payload(payload)
    if not isinstance(payload, dict):
        return []
    results: list[dict[str, Any]] = []
    workshop = payload.get("workshop") if isinstance(payload.get("workshop"), dict) else {}
    line = payload.get("line") if isinstance(payload.get("line"), dict) else {}
    workshop_name = _pick_str(workshop, "name") or _pick_str(payload, "workshop_name")
    workshop_code = _pick_str(workshop, "code")
    line_name = _pick_str(line, "name") or _pick_str(payload, "line_name")
    line_code = _pick_str(line, "code")
    devices = payload.get("devices")

    if isinstance(devices, list) and devices:
        for device in devices:
            if not isinstance(device, dict):
                continue
            external_id = device_external_id(device)
            if not external_id:
                continue
            results.append(
                {
                    "external_device_id": external_id,
                    "device_name": _pick_str(device, "device_name", "name") or external_id,
                    "device_key": _pick_str(device, "device_key"),
                    "line_name": _pick_str(device, "line_name") or line_name,
                    "line_code": line_code,
                    "workshop_name": _pick_str(device, "workshop_name") or workshop_name,
                    "workshop_code": workshop_code,
                    "status": _pick_str(device, "status"),
                    "connection_id": None,
                }
            )
        if results:
            return results

    external_id = _pick_str(payload, "device_id", "external_device_id", "device_key")
    if external_id:
        results.append(
            {
                "external_device_id": external_id,
                "device_name": _pick_str(payload, "device_name", "name") or external_id,
                "device_key": _pick_str(payload, "device_key"),
                "line_name": line_name,
                "line_code": line_code,
                "workshop_name": workshop_name,
                "workshop_code": workshop_code,
                "status": _pick_str(payload, "status"),
            }
        )
    return results


class MqttDeviceDiscoveryService:
    @staticmethod
    def _to_item(row: IotDiscoveredMqttDevice) -> dict[str, Any]:
        name = row.device_name or row.external_device_id
        return {
            "external_device_id": row.external_device_id,
            "device_name": name,
            "device_key": row.device_key,
            "line_name": row.line_name,
            "line_code": row.line_code,
            "workshop_name": row.workshop_name,
            "workshop_code": row.workshop_code,
            "status": row.status,
            "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            "topic": row.topic,
            "connection_id": row.connection_id,
            "label": f"{name} / {row.external_device_id}",
        }

    @classmethod
    async def upsert_from_payload(
        cls,
        tenant_id: int,
        connection_id: int,
        payload: Any,
        *,
        topic: Optional[str] = None,
        seen_at: Optional[datetime] = None,
    ) -> int:
        items = extract_devices_from_payload(payload)
        if not items:
            return 0
        now = seen_at or datetime.now(timezone.utc)
        written = 0
        for item in items:
            external_id = item["external_device_id"]
            defaults = {
                "device_name": (item.get("device_name") or "")[:100] or None,
                "device_key": (item.get("device_key") or "")[:100] or None,
                "line_name": (item.get("line_name") or "")[:100] or None,
                "line_code": (item.get("line_code") or "")[:50] or None,
                "workshop_name": (item.get("workshop_name") or "")[:100] or None,
                "workshop_code": (item.get("workshop_code") or "")[:50] or None,
                "status": (item.get("status") or "")[:30] or None,
                "topic": (topic or "")[:255] or None,
                "last_seen_at": now,
                "deleted_at": None,
            }
            row = await IotDiscoveredMqttDevice.filter(
                tenant_id=tenant_id,
                connection_id=connection_id,
                external_device_id=external_id,
            ).first()
            if row is None:
                await IotDiscoveredMqttDevice.create(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    external_device_id=external_id[:100],
                    **defaults,
                )
            else:
                await row.update_from_dict(defaults)
                await row.save()
            written += 1
        return written

    @classmethod
    async def _iter_recent_messages(
        cls,
        tenant_id: int,
        connection_id: Optional[int],
    ):
        query = IotConnectionMessage.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if connection_id is not None:
            query = query.filter(connection_id=connection_id)
            rows = await query.order_by("-created_at").limit(50)
            return rows
        connections = await IotConnection.filter(
            tenant_id=tenant_id,
            connection_type="mqtt",
            deleted_at__isnull=True,
        )
        rows = []
        for conn in connections:
            part = await IotConnectionMessage.filter(
                tenant_id=tenant_id,
                connection_id=conn.id,
                deleted_at__isnull=True,
            ).order_by("-created_at").limit(20)
            rows.extend(part)
        return rows

    @classmethod
    async def _backfill_from_messages(
        cls,
        tenant_id: int,
        connection_id: Optional[int],
    ) -> None:
        try:
            rows = await cls._iter_recent_messages(tenant_id, connection_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("kuaiiot load messages for discovered backfill failed: {}", exc)
            return
        for row in rows:
            try:
                await cls.upsert_from_payload(
                    tenant_id,
                    row.connection_id,
                    row.payload,
                    topic=row.topic,
                    seen_at=row.created_at,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("kuaiiot backfill discovered devices failed: {}", exc)

    @classmethod
    async def _merge_from_persisted_messages(
        cls,
        tenant_id: int,
        connection_id: Optional[int],
        merged: dict[str, dict[str, Any]],
    ) -> None:
        try:
            rows = await cls._iter_recent_messages(tenant_id, connection_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("kuaiiot merge discovered from messages failed: {}", exc)
            return
        for row in rows:
            for item in extract_devices_from_payload(row.payload):
                external_id = item["external_device_id"]
                if external_id in merged:
                    continue
                merged[external_id] = {
                    **item,
                    "connection_id": row.connection_id,
                    "last_seen_at": row.created_at.isoformat() if row.created_at else None,
                    "topic": row.topic,
                    "label": f"{item.get('device_name') or external_id} / {external_id}",
                }

    @classmethod
    async def list_discovered_devices(
        cls,
        tenant_id: int,
        connection_id: Optional[int] = None,
        *,
        message_limit: int = 50,
    ) -> list[dict[str, Any]]:
        del message_limit  # 名录表为主，条数由现场设备决定
        catalog_query = IotDiscoveredMqttDevice.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        )
        if connection_id is not None:
            catalog_query = catalog_query.filter(connection_id=connection_id)
        try:
            rows = await catalog_query.order_by("device_name")
            if not rows:
                await cls._backfill_from_messages(tenant_id, connection_id)
                rows = await catalog_query.order_by("device_name")
        except Exception as exc:  # noqa: BLE001
            logger.warning("kuaiiot list discovered catalog failed: {}", exc)
            rows = []
            await cls._backfill_from_messages(tenant_id, connection_id)

        merged: dict[str, dict[str, Any]] = {}
        for row in rows:
            merged[row.external_device_id] = cls._to_item(row)

        if not merged:
            await cls._merge_from_persisted_messages(tenant_id, connection_id, merged)
            await cls._merge_from_live_buffer(tenant_id, connection_id, merged)

        external_ids = list(merged.keys())
        bound: set[str] = set()
        if external_ids:
            existing = await IotDevice.filter(
                tenant_id=tenant_id,
                external_device_id__in=external_ids,
                deleted_at__isnull=True,
            ).values_list("external_device_id", flat=True)
            bound = {str(item) for item in existing}

        items = []
        for external_id, item in merged.items():
            items.append(
                {
                    **item,
                    "already_bound": external_id in bound,
                    "label": item.get("label")
                    or f"{item.get('device_name') or external_id} / {external_id}",
                }
            )
        items.sort(key=lambda x: (x.get("already_bound") is True, str(x.get("device_name") or "")))
        return items

    @classmethod
    async def _merge_from_live_buffer(
        cls,
        tenant_id: int,
        connection_id: Optional[int],
        merged: dict[str, dict[str, Any]],
    ) -> None:
        from apps.kuaiiot.services.mqtt_message_buffer import MqttMessageBuffer

        connections: list[IotConnection]
        if connection_id is not None:
            conn = await IotConnection.filter(id=connection_id, tenant_id=tenant_id).first()
            connections = [conn] if conn else []
        else:
            connections = await IotConnection.filter(
                tenant_id=tenant_id,
                connection_type="mqtt",
                deleted_at__isnull=True,
            )
        for conn in connections:
            for msg in MqttMessageBuffer.list_messages(conn.id, limit=50):
                for item in extract_devices_from_payload(msg.get("payload")):
                    external_id = item["external_device_id"]
                    if external_id in merged:
                        continue
                    merged[external_id] = {
                        **item,
                        "connection_id": conn.id,
                        "last_seen_at": msg.get("received_at"),
                        "topic": msg.get("topic"),
                        "label": f"{item.get('device_name') or external_id} / {external_id}",
                    }
