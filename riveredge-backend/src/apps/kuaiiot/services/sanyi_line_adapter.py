"""三易产线 MQTT 报文适配：devices[] + variables[] → 快数采 IngestPayload。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def is_sanyi_line_payload(payload: Any) -> bool:
    """识别三易产线快照报文（含 devices[].variables[]）。"""
    if not isinstance(payload, dict):
        return False
    devices = payload.get("devices")
    if not isinstance(devices, list) or not devices:
        return False
    first = devices[0]
    if not isinstance(first, dict):
        return False
    if not (first.get("device_id") or first.get("device_key")):
        return False
    variables = first.get("variables")
    return isinstance(variables, list)


def _parse_timestamp(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def device_external_id(device: dict[str, Any]) -> Optional[str]:
    for key in ("device_id", "device_key", "id"):
        value = device.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def convert_device_to_tags(device: dict[str, Any]) -> dict[str, Any]:
    """将单台设备拍平为 tags（variable_code → value，并附 online）。"""
    tags: dict[str, Any] = {}
    status = str(device.get("status") or "").strip().lower()
    if status:
        tags["online"] = status in {"online", "1", "true", "yes", "on"}
        tags["status"] = str(device.get("status"))
    exception = device.get("exception")
    if exception not in (None, ""):
        tags["exception"] = str(exception)

    variables = device.get("variables") or []
    if isinstance(variables, list):
        for item in variables:
            if not isinstance(item, dict):
                continue
            code = str(item.get("variable_code") or "").strip()
            if not code:
                continue
            tags[code] = item.get("value")
    return tags


def iter_sanyi_device_ingest(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    拆成多台设备入站草案。

    每项：
      - external_device_id
      - device_name
      - tags
      - timestamp (datetime | None)
    """
    root_ts = _parse_timestamp(payload.get("timestamp"))
    results: list[dict[str, Any]] = []
    for device in payload.get("devices") or []:
        if not isinstance(device, dict):
            continue
        external_id = device_external_id(device)
        if not external_id:
            continue
        tags = convert_device_to_tags(device)
        if not tags:
            continue
        results.append(
            {
                "external_device_id": external_id,
                "device_name": str(device.get("device_name") or external_id),
                "tags": tags,
                "timestamp": _parse_timestamp(device.get("timestamp")) or root_ts,
            }
        )
    return results
