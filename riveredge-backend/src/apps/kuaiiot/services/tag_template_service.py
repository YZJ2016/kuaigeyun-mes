"""星数采点位模板服务。"""

from __future__ import annotations

from typing import Optional

from apps.kuaiiot.models.iot import IotDevice, IotTagDefinition
from apps.kuaiiot.schemas.iot import ApplyTagTemplateResponse, TagTemplateResponse
from apps.kuaiiot.services.device_service import DeviceService
from apps.kuaiiot.services.tag_service import TagService, _validate_fill_target, _validate_map_target
from apps.kuaiiot.tag_templates import TAG_TEMPLATES
from infra.exceptions.exceptions import NotFoundError, ValidationError


class TagTemplateService:
    @staticmethod
    def list_templates() -> list[TagTemplateResponse]:
        return [
            TagTemplateResponse(
                code=code,
                name=item["name"],
                description=item.get("description"),
                tag_count=len(item.get("tags") or []),
            )
            for code, item in TAG_TEMPLATES.items()
        ]

    @staticmethod
    async def apply_template(tenant_id: int, device_uuid: str, template_code: str) -> ApplyTagTemplateResponse:
        template = TAG_TEMPLATES.get(template_code)
        if not template:
            raise NotFoundError(f"点位模板不存在: {template_code}")

        device = await DeviceService.get_by_uuid(tenant_id, device_uuid)
        created = 0
        skipped = 0
        for tag in template.get("tags") or []:
            map_target = tag["map_target"]
            TagService._validate_map_target(map_target)
            exists = await IotTagDefinition.filter(
                tenant_id=tenant_id,
                device_id=device.id,
                tag_key=tag["tag_key"],
                deleted_at__isnull=True,
            ).exists()
            if exists:
                skipped += 1
                continue
            await IotTagDefinition.create(
                tenant_id=tenant_id,
                device_id=device.id,
                tag_key=tag["tag_key"],
                name=tag["name"],
                value_type=tag["value_type"],
                unit=tag.get("unit"),
                map_target=map_target,
            )
            created += 1
        return ApplyTagTemplateResponse(created=created, skipped=skipped, template_code=template_code)

    @staticmethod
    async def apply_template_for_device_id(tenant_id: int, device: IotDevice, template_code: str) -> None:
        if not template_code:
            return
        await TagTemplateService.apply_template(tenant_id, device.uuid, template_code)


# ---- 星数采本地执行版：租户校验与按整型设备 ID 套用模板 ----

def _require_tenant(explicit: int) -> int:
    from infra.domain.tenant_context import TenantContextError, get_current_tenant_id

    current = get_current_tenant_id()
    if current is None:
        raise TenantContextError("组织上下文未设置")
    if int(current) != int(explicit):
        raise ValidationError("租户上下文不匹配")
    return int(current)


async def apply_template(
    tenant_id: int,
    device_id: int,
    code: str,
    *,
    user_id: Optional[int] = None,
) -> list[str]:
    tid = _require_tenant(tenant_id)
    template_code = (code or "").strip()
    template = TAG_TEMPLATES.get(template_code)
    if template is None:
        raise ValidationError("点位模板不存在")
    device = await IotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("IoT 设备不存在")
    existing = {
        row.tag_key
        for row in await IotTagDefinition.filter(
            tenant_id=tid,
            device_id=device.id,
            deleted_at__isnull=True,
        )
    }
    written: list[str] = []
    for tag in template["tags"]:
        tag_key = str(tag["tag_key"]).strip()
        if tag_key in existing:
            written.append(tag_key)
            continue
        value_type = str(tag.get("value_type") or "number")
        await IotTagDefinition.create(
            tenant_id=tid,
            device_id=device.id,
            tag_key=tag_key,
            name=str(tag["name"]).strip(),
            value_type=value_type,
            unit=(str(tag["unit"]).strip() if tag.get("unit") else None),
            map_target=_validate_map_target(str(tag["map_target"])),
            fill_target=_validate_fill_target(tag.get("fill_target")),
            is_enabled=True,
            created_by=user_id,
            updated_by=user_id,
        )
        written.append(tag_key)
    return written
