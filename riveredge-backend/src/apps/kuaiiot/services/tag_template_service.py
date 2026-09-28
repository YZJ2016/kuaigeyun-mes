"""把三套模板写成 tag_definitions。不写告警，不改设备台账。"""

from __future__ import annotations

from typing import Optional

from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.tag import KuaiiotTagDefinition
from apps.kuaiiot.services.tag_service import _validate_fill_target, _validate_map_target
from apps.kuaiiot.tag_templates import TAG_TEMPLATES
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError


class TagTemplateView:
    def __init__(self, code: str, name: str, tags: list):
        self.code = code
        self.name = name
        self.tags = tags


class TagTemplateService:
    @staticmethod
    def list_templates() -> list[TagTemplateView]:
        return [
            TagTemplateView(code, body["name"], list(body["tags"]))
            for code, body in TAG_TEMPLATES.items()
        ]


def _require_tenant(explicit: int) -> int:
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
    device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("IoT 设备不存在")
    existing = {
        row.tag_key
        for row in await KuaiiotTagDefinition.filter(
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
        await KuaiiotTagDefinition.create(
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
