"""快数采业务表单自动填充上下文。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from apps.kuaiiot.constants import FILL_TARGET_PREFIXES
from apps.kuaiiot.models.iot import IotDevice, IotTagDefinition, IotTagSnapshot
from apps.kuaiiot.schemas.iot import FillContextResponse
from infra.exceptions.exceptions import ValidationError


class FillContextService:
    @staticmethod
    def _validate_fill_target(fill_target: str) -> None:
        if not any(fill_target.startswith(prefix) for prefix in FILL_TARGET_PREFIXES):
            raise ValidationError(f"无效的 fill_target: {fill_target}")

    @staticmethod
    def _snapshot_value(snapshot: IotTagSnapshot) -> Any:
        if snapshot.value_text is not None and str(snapshot.value_text).strip():
            return snapshot.value_text
        if snapshot.value_number is not None:
            return float(snapshot.value_number)
        if snapshot.value_bool is not None:
            return snapshot.value_bool
        return None

    @staticmethod
    async def get_fill_context(
        tenant_id: int,
        *,
        equipment_uuid: Optional[str] = None,
        device_uuid: Optional[str] = None,
        context: str,
    ) -> FillContextResponse:
        if context not in {"reporting", "spot_check"}:
            raise ValidationError(f"不支持的 context: {context}")
        prefix = "sop_parameters." if context == "reporting" else "spot_check."

        device_query = IotDevice.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if device_uuid:
            device_query = device_query.filter(uuid=device_uuid)
        elif equipment_uuid:
            device_query = device_query.filter(equipment_uuid=equipment_uuid)
        else:
            return FillContextResponse(values={}, device_uuid=None, equipment_uuid=None)

        device = await device_query.first()
        if not device:
            return FillContextResponse(values={}, device_uuid=None, equipment_uuid=equipment_uuid)

        tag_defs = await IotTagDefinition.filter(
            tenant_id=tenant_id,
            device_id=device.id,
            is_enabled=True,
            deleted_at__isnull=True,
        )
        fill_tags = [item for item in tag_defs if item.fill_target and item.fill_target.startswith(prefix)]
        if not fill_tags:
            return FillContextResponse(
                values={},
                device_uuid=device.uuid,
                equipment_uuid=device.equipment_uuid,
            )

        snapshots = await IotTagSnapshot.filter(
            tenant_id=tenant_id,
            device_id=device.id,
            deleted_at__isnull=True,
        )
        snapshot_map = {item.tag_key: item for item in snapshots}
        values: dict[str, Any] = {}
        for tag_def in fill_tags:
            snapshot = snapshot_map.get(tag_def.tag_key)
            if not snapshot:
                continue
            key = tag_def.fill_target.split(".", 1)[1]
            value = FillContextService._snapshot_value(snapshot)
            if value is None:
                continue
            values[key] = value

        return FillContextResponse(
            values=values,
            device_uuid=device.uuid,
            equipment_uuid=device.equipment_uuid,
        )
