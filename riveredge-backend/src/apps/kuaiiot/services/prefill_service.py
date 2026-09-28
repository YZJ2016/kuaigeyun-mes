"""按星制造设备 uuid 读预填值。不插入报工单或点检单。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.tag import KuaiiotTagDefinition, KuaiiotTagSnapshot
from apps.kuaiiot.services.tag_template_service import _require_tenant
from infra.exceptions.exceptions import ValidationError

_CONTEXT_PREFIX = {
    "reporting": "sop_parameters.",
    "spot_check": "spot_check.",
}


def _snapshot_value(row: KuaiiotTagSnapshot) -> Any:
    if row.value_number is not None:
        return float(row.value_number)
    if row.value_bool is not None:
        return bool(row.value_bool)
    if row.value_text is not None:
        return row.value_text
    return None


def _value_key(fill_target: str, context: Optional[str]) -> Optional[str]:
    if context is None:
        return fill_target
    prefix = _CONTEXT_PREFIX[context]
    if not fill_target.startswith(prefix):
        return None
    suffix = fill_target[len(prefix) :]
    return suffix or None


async def read_fill_context(
    tenant_id: int,
    equipment_uuid: str,
    context: Optional[str] = None,
) -> dict[str, Any]:
    tid = _require_tenant(tenant_id)
    if context is not None and context not in _CONTEXT_PREFIX:
        raise ValidationError("预填场景仅允许 reporting 或 spot_check")
    text = (equipment_uuid or "").strip()
    if not text:
        raise ValidationError("必须填写设备 uuid")
    equipment = await Equipment.filter(tenant_id=tid, uuid=text, deleted_at__isnull=True).first()
    if equipment is None:
        return {"equipment_uuid": text, "values": {}}
    devices = await KuaiiotDevice.filter(
        tenant_id=tid,
        equipment_uuid=equipment.uuid,
        deleted_at__isnull=True,
    )
    if not devices:
        return {"equipment_uuid": equipment.uuid, "values": {}}
    device_ids = [item.id for item in devices]
    definitions = await KuaiiotTagDefinition.filter(
        tenant_id=tid,
        device_id__in=device_ids,
        is_enabled=True,
        deleted_at__isnull=True,
    )
    snapshots = await KuaiiotTagSnapshot.filter(
        tenant_id=tid,
        device_id__in=device_ids,
        deleted_at__isnull=True,
    )
    snap_by_key = {(row.device_id, row.tag_key): row for row in snapshots}
    chosen: dict[str, tuple[Any, Any]] = {}
    for definition in definitions:
        fill_target = (definition.fill_target or "").strip()
        if not fill_target.startswith("sop_parameters.") and not fill_target.startswith("spot_check."):
            continue
        key = _value_key(fill_target, context)
        if key is None:
            continue
        snapshot = snap_by_key.get((definition.device_id, definition.tag_key))
        if snapshot is None:
            continue
        value = _snapshot_value(snapshot)
        if value is None:
            continue
        current = chosen.get(key)
        if current is None or snapshot.sampled_at >= current[0]:
            chosen[key] = (snapshot.sampled_at, value)
    body: dict[str, Any] = {
        "equipment_uuid": equipment.uuid,
        "values": {key: item[1] for key, item in chosen.items()},
    }
    if len(devices) == 1:
        body["device_uuid"] = devices[0].uuid
    return body
