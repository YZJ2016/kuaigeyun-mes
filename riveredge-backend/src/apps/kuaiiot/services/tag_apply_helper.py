"""快数采点位套用辅助（模板 / 产品物模型共用）。"""

from __future__ import annotations

from typing import Any

from apps.kuaiiot.models.iot import IotDevice, IotTagDefinition
from apps.kuaiiot.services.tag_service import TagService


async def apply_tag_definitions_to_device(
    tenant_id: int,
    device: IotDevice,
    tags: list[dict[str, Any]],
) -> tuple[int, int]:
    created = 0
    skipped = 0
    for tag in tags or []:
        if not isinstance(tag, dict):
            continue
        tag_key = str(tag.get("tag_key") or "").strip()
        if not tag_key:
            continue
        map_target = str(tag.get("map_target") or "").strip()
        TagService._validate_map_target(map_target)
        exists = await IotTagDefinition.filter(
            tenant_id=tenant_id,
            device_id=device.id,
            tag_key=tag_key,
            deleted_at__isnull=True,
        ).exists()
        if exists:
            skipped += 1
            continue
        await IotTagDefinition.create(
            tenant_id=tenant_id,
            device_id=device.id,
            tag_key=tag_key,
            name=str(tag.get("name") or tag_key),
            value_type=str(tag.get("value_type") or "number"),
            unit=tag.get("unit"),
            map_target=map_target,
            fill_target=tag.get("fill_target"),
        )
        created += 1
    return created, skipped
