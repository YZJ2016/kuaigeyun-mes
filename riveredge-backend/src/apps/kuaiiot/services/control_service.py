"""控制面：连接、IoT 设备、点位登记，以及最新快照读取。"""

from __future__ import annotations

import secrets
from typing import Optional

from apps.kuaizhizao.services.equipment_service import EquipmentService
from apps.kuaiiot.constants import VALUE_TYPES
from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.tag import KuaiiotTagDefinition, KuaiiotTagSnapshot
from apps.kuaiiot.schemas.control import ConnectionCreate, DeviceCreate, TagCreate
from apps.kuaiiot.services.tag_service import _validate_fill_target, _validate_map_target
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError


def _require_tenant(explicit: int) -> int:
    current = get_current_tenant_id()
    if current is None:
        raise TenantContextError("组织上下文未设置")
    if int(current) != int(explicit):
        raise ValidationError("租户上下文不匹配")
    return int(current)


def _new_device_token() -> str:
    return secrets.token_urlsafe(32)[:64]


def validate_map_target(map_target: str) -> str:
    return _validate_map_target(map_target)


async def _bind_equipment_uuid(tenant_id: int, equipment_uuid: Optional[str]) -> Optional[str]:
    text = (equipment_uuid or "").strip()
    if not text:
        return None
    try:
        equipment = await EquipmentService.get_equipment_by_uuid(tenant_id, text)
    except NotFoundError as exc:
        raise ValidationError("绑定设备不属于当前租户") from exc
    return equipment.uuid


async def create_connection(
    tenant_id: int,
    payload: ConnectionCreate,
    *,
    user_id: Optional[int] = None,
) -> KuaiiotConnection:
    tid = _require_tenant(tenant_id)
    code = payload.code.strip()
    exists = await KuaiiotConnection.filter(tenant_id=tid, code=code, deleted_at__isnull=True).exists()
    if exists:
        raise ValidationError("连接编码已存在")
    return await KuaiiotConnection.create(
        tenant_id=tid,
        code=code,
        name=payload.name.strip(),
        connection_type=payload.connection_type.strip(),
        config=payload.config,
        is_enabled=payload.is_enabled,
        remark=payload.remark,
        created_by=user_id,
        updated_by=user_id,
    )


async def list_connections(tenant_id: int) -> list[KuaiiotConnection]:
    tid = _require_tenant(tenant_id)
    return await KuaiiotConnection.filter(tenant_id=tid, deleted_at__isnull=True).order_by("id")


async def create_device(
    tenant_id: int,
    payload: DeviceCreate,
    *,
    user_id: Optional[int] = None,
) -> KuaiiotDevice:
    tid = _require_tenant(tenant_id)
    external_id = (payload.external_device_id or "").strip()
    if not external_id:
        raise ValidationError("必须填写外部设备标识")
    code = payload.code.strip()
    if not code or not payload.name.strip():
        raise ValidationError("设备编码和名称不能为空")
    if payload.connection_id is not None:
        connection = await KuaiiotConnection.filter(
            tenant_id=tid,
            id=payload.connection_id,
            deleted_at__isnull=True,
        ).first()
        if connection is None:
            raise ValidationError("连接不存在")
    exists = await KuaiiotDevice.filter(tenant_id=tid, code=code, deleted_at__isnull=True).exists()
    if exists:
        raise ValidationError("设备编码已存在")
    equipment_uuid = await _bind_equipment_uuid(tid, payload.equipment_uuid)
    template_code = (payload.template_code or "").strip()
    if template_code:
        from apps.kuaiiot.tag_templates import TAG_TEMPLATES

        if template_code not in TAG_TEMPLATES:
            raise ValidationError("点位模板不存在")
    device = await KuaiiotDevice.create(
        tenant_id=tid,
        connection_id=payload.connection_id,
        external_device_id=external_id,
        code=code,
        name=payload.name.strip(),
        device_token=_new_device_token(),
        equipment_uuid=equipment_uuid,
        remark=payload.remark,
        created_by=user_id,
        updated_by=user_id,
    )
    if template_code:
        from apps.kuaiiot.services.tag_template_service import apply_template

        await apply_template(tid, device.id, template_code, user_id=user_id)
    return device


async def list_devices(tenant_id: int) -> list[KuaiiotDevice]:
    tid = _require_tenant(tenant_id)
    return await KuaiiotDevice.filter(tenant_id=tid, deleted_at__isnull=True).order_by("id")


async def rotate_device_token(
    tenant_id: int,
    device_id: int,
    *,
    user_id: Optional[int] = None,
) -> KuaiiotDevice:
    tid = _require_tenant(tenant_id)
    device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("IoT 设备不存在")
    device.device_token = _new_device_token()
    device.updated_by = user_id
    await device.save(update_fields=["device_token", "updated_by", "updated_at"])
    return device


async def create_tag(
    tenant_id: int,
    device_id: int,
    payload: TagCreate,
    *,
    user_id: Optional[int] = None,
) -> KuaiiotTagDefinition:
    tid = _require_tenant(tenant_id)
    device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("IoT 设备不存在")
    value_type = (payload.value_type or "number").strip()
    if value_type not in VALUE_TYPES:
        raise ValidationError("点位值类型仅允许 number、boolean、text")
    tag_key = payload.tag_key.strip()
    if not tag_key:
        raise ValidationError("点位键不能为空")
    map_target = validate_map_target(payload.map_target)
    fill_target = _validate_fill_target(payload.fill_target)
    exists = await KuaiiotTagDefinition.filter(
        tenant_id=tid,
        device_id=device.id,
        tag_key=tag_key,
        deleted_at__isnull=True,
    ).exists()
    if exists:
        raise ValidationError("点位键已存在")
    return await KuaiiotTagDefinition.create(
        tenant_id=tid,
        device_id=device.id,
        tag_key=tag_key,
        name=payload.name.strip(),
        value_type=value_type,
        unit=(payload.unit or "").strip() or None,
        map_target=map_target,
        fill_target=fill_target,
        is_enabled=payload.is_enabled,
        created_by=user_id,
        updated_by=user_id,
    )


async def list_device_snapshots(tenant_id: int, device_id: int) -> list[KuaiiotTagSnapshot]:
    tid = _require_tenant(tenant_id)
    device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("IoT 设备不存在")
    return await KuaiiotTagSnapshot.filter(
        tenant_id=tid,
        device_id=device.id,
        deleted_at__isnull=True,
    ).order_by("tag_key")
