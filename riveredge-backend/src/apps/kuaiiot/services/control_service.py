"""控制面：连接、IoT 设备、点位登记，以及最新快照读取。"""

from __future__ import annotations

import secrets
from typing import Optional

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from apps.kuaizhizao.services.equipment_service import EquipmentService
from apps.kuaiiot.constants import VALUE_TYPES
from apps.kuaiiot.models.alert import KuaiiotAlertRule
from apps.kuaiiot.models.connection import KuaiiotConnection
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.edge_config import KuaiiotEdgeConfig
from apps.kuaiiot.models.group import KuaiiotDeviceGroup
from apps.kuaiiot.models.tag import KuaiiotTagDefinition, KuaiiotTagSnapshot
from apps.kuaiiot.schemas.control import (
    ConnectionCreate,
    ConnectionUpdate,
    DeviceCreate,
    DeviceUpdate,
    TagCreate,
    TagUpdate,
)
from apps.kuaiiot.services.product_service import get_product, _validate_tags
from apps.kuaiiot.services.connection_runtime import EXTERNAL_TYPES, validate_mapping, validate_type, resolve_core_connection
from core.services.integration.iot_platform_client import PlatformClient
from core.models.integration_config import IntegrationConfig
from apps.kuaiiot.services.tag_service import _validate_fill_target, _validate_map_target
from core.utils.timezone_utils import resolve_business_datetime
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
    kind = payload.connection_type.strip().lower()
    if kind not in {"http", *EXTERNAL_TYPES}:
        raise ValidationError("不支持的数采连接类型")
    validate_mapping(payload.config)
    if kind in EXTERNAL_TYPES and payload.integration_uuid is None:
        raise ValidationError("请选择同租户公共连接")
    exists = await KuaiiotConnection.filter(tenant_id=tid, code=code, deleted_at__isnull=True).exists()
    if exists:
        raise ValidationError("连接编码已存在")
    try:
        async with in_transaction():
            integration_id = None
            if payload.integration_uuid is not None:
                core = await IntegrationConfig.filter(
                    uuid=str(payload.integration_uuid), tenant_id=tid, deleted_at__isnull=True,
                ).select_for_update().first()
                if core is None:
                    raise ValidationError("公共连接不存在或不属于当前租户")
                validate_type(kind, core.type)
                if not core.is_active:
                    raise ValidationError("公共连接已停用")
                integration_id = core.id
            return await KuaiiotConnection.create(
                tenant_id=tid, code=code, name=payload.name.strip(), connection_type=kind,
                integration_id=integration_id, config=payload.config, is_enabled=payload.is_enabled,
                remark=payload.remark, created_by=user_id, updated_by=user_id,
            )
    except IntegrityError as exc:
        raise ValidationError("连接编码已存在") from exc


async def list_connections(tenant_id: int) -> list[KuaiiotConnection]:
    tid = _require_tenant(tenant_id)
    return await KuaiiotConnection.filter(tenant_id=tid, deleted_at__isnull=True).order_by("id").limit(500)


async def get_connection(tenant_id: int, connection_id: int) -> KuaiiotConnection:
    tid = _require_tenant(tenant_id)
    row = await KuaiiotConnection.filter(
        tenant_id=tid, id=connection_id, deleted_at__isnull=True
    ).first()
    if row is None:
        raise NotFoundError("数采连接不存在")
    return row


async def update_connection(
    tenant_id: int,
    connection_id: int,
    payload: ConnectionUpdate,
    *,
    user_id: Optional[int] = None,
) -> KuaiiotConnection:
    row = await get_connection(tenant_id, connection_id)
    fields = payload.model_fields_set
    if "name" in fields:
        title = (payload.name or "").strip()
        if not title:
            raise ValidationError("连接名称不能为空")
        row.name = title
    if "config" in fields:
        validate_mapping(payload.config)
        row.config = payload.config
    if "is_enabled" in fields and payload.is_enabled is not None:
        row.is_enabled = payload.is_enabled
    if "remark" in fields:
        row.remark = payload.remark
    row.updated_by = user_id
    await row.save()
    return row


async def delete_connection(
    tenant_id: int,
    connection_id: int,
    *,
    user_id: Optional[int] = None,
) -> None:
    row = await get_connection(tenant_id, connection_id)
    row.deleted_at = resolve_business_datetime()
    row.deleted_by = user_id
    await row.save(update_fields=["deleted_at", "deleted_by", "updated_at"])


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
    product_tags = []
    if payload.product_id is not None:
        try:
            product = await get_product(tid, payload.product_id)
        except NotFoundError as exc:
            raise ValidationError("产品不属于当前租户") from exc
        product_tags = _validate_tags(product.tags or [])
    if payload.group_id is not None:
        group = await KuaiiotDeviceGroup.filter(
            tenant_id=tid, id=payload.group_id, deleted_at__isnull=True,
        ).first()
        if group is None:
            raise ValidationError("分组不属于当前租户")
    template_code = (payload.template_code or "").strip()
    if template_code:
        from apps.kuaiiot.tag_templates import TAG_TEMPLATES

        if template_code not in TAG_TEMPLATES:
            raise ValidationError("点位模板不存在")
    try:
        async with in_transaction():
            device = await KuaiiotDevice.create(
                tenant_id=tid,
                connection_id=payload.connection_id,
                external_device_id=external_id,
                code=code,
                name=payload.name.strip(),
                device_token=_new_device_token(),
                equipment_uuid=equipment_uuid,
                product_id=payload.product_id,
                group_id=payload.group_id,
                remark=payload.remark,
                created_by=user_id,
                updated_by=user_id,
            )
            for tag in product_tags:
                await KuaiiotTagDefinition.create(
                    tenant_id=tid, device_id=device.id, **tag,
                    created_by=user_id, updated_by=user_id,
                )
            if template_code:
                from apps.kuaiiot.services.tag_template_service import apply_template

                # 已有模板语义：保留产品同名点位，只补尚不存在的点位。
                await apply_template(tid, device.id, template_code, user_id=user_id)
    except IntegrityError as exc:
        raise ValidationError("设备编码已存在") from exc
    return device


async def discover_external_devices(tenant_id: int, connection_id: int, *, page: int = 0) -> dict:
    connection = await get_connection(tenant_id, connection_id)
    if connection.connection_type not in {"thingsboard", "jetlinks"}:
        raise ValidationError("该连接需要手动填写外部设备标识")
    core = await resolve_core_connection(connection)
    if core is None:
        raise ValidationError("数采连接未关联应用连接")
    async with PlatformClient(connection.connection_type, core.get_config()) as client:
        return await client.device_page(page)


async def list_devices(tenant_id: int) -> list[KuaiiotDevice]:
    tid = _require_tenant(tenant_id)
    return await KuaiiotDevice.filter(tenant_id=tid, deleted_at__isnull=True).order_by("id").limit(500)


async def get_device(tenant_id: int, device_id: int) -> KuaiiotDevice:
    tid = _require_tenant(tenant_id)
    row = await KuaiiotDevice.filter(
        tenant_id=tid, id=device_id, deleted_at__isnull=True
    ).first()
    if row is None:
        raise NotFoundError("IoT 设备不存在")
    return row


async def delete_device(
    tenant_id: int,
    device_id: int,
    *,
    user_id: Optional[int] = None,
) -> None:
    row = await get_device(tenant_id, device_id)
    now = resolve_business_datetime()
    async with in_transaction():
        row.deleted_at = now
        row.deleted_by = user_id
        await row.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
        # 级联软删该设备下的边缘配置与设备绑定告警规则，同事务。
        for model in (KuaiiotEdgeConfig, KuaiiotAlertRule):
            children = await model.filter(
                tenant_id=int(row.tenant_id), device_id=row.id, deleted_at__isnull=True
            )
            for child in children:
                child.deleted_at = now
                child.deleted_by = user_id
                await child.save(update_fields=["deleted_at", "deleted_by", "updated_at"])


async def update_device(
    tenant_id: int,
    device_id: int,
    payload: DeviceUpdate,
    *,
    user_id: Optional[int] = None,
) -> KuaiiotDevice:
    """改绑星制造设备/分组/产品与名称备注。clear_equipment 优先于 equipment_uuid。"""
    tid = _require_tenant(tenant_id)
    device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("IoT 设备不存在")
    fields = payload.model_fields_set
    if "name" in fields:
        title = (payload.name or "").strip()
        if not title:
            raise ValidationError("设备名称不能为空")
        device.name = title
    if "connection_id" in fields:
        if payload.connection_id is not None:
            connection = await KuaiiotConnection.filter(
                tenant_id=tid,
                id=payload.connection_id,
                deleted_at__isnull=True,
            ).first()
            if connection is None:
                raise ValidationError("连接不存在")
        device.connection_id = payload.connection_id
    if payload.clear_equipment:
        device.equipment_uuid = None
    elif "equipment_uuid" in fields:
        device.equipment_uuid = await _bind_equipment_uuid(tid, payload.equipment_uuid)
    if "group_id" in fields:
        if payload.group_id is not None:
            group = await KuaiiotDeviceGroup.filter(
                tenant_id=tid,
                id=payload.group_id,
                deleted_at__isnull=True,
            ).first()
            if group is None:
                raise ValidationError("分组不属于当前租户")
        device.group_id = payload.group_id
    if "product_id" in fields:
        if payload.product_id is not None:
            try:
                await get_product(tid, int(payload.product_id))
            except NotFoundError as exc:
                raise ValidationError("产品不属于当前租户") from exc
        device.product_id = payload.product_id
    if "remark" in fields:
        device.remark = payload.remark
    device.updated_by = user_id
    await device.save()
    return device


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
    try:
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
    except IntegrityError as exc:
        raise ValidationError("点位键已存在") from exc


async def list_device_snapshots(tenant_id: int, device_id: int) -> list[KuaiiotTagSnapshot]:
    tid = _require_tenant(tenant_id)
    device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("IoT 设备不存在")
    return await KuaiiotTagSnapshot.filter(
        tenant_id=tid,
        device_id=device.id,
        deleted_at__isnull=True,
    ).order_by("tag_key").limit(500)


async def _live_device_ids(tenant_id: int, device_id: Optional[int] = None) -> list[int]:
    query = KuaiiotDevice.filter(tenant_id=tenant_id, deleted_at__isnull=True)
    if device_id is not None:
        query = query.filter(id=device_id)
    return [row.id for row in await query]


async def list_tags(tenant_id: int, device_id: Optional[int] = None) -> list[KuaiiotTagDefinition]:
    """点位列表只含未删除设备下的点位。device_id 为空时列全租户。"""
    tid = _require_tenant(tenant_id)
    device_ids = await _live_device_ids(tid, device_id)
    if not device_ids:
        return []
    return await KuaiiotTagDefinition.filter(
        tenant_id=tid,
        device_id__in=device_ids,
        deleted_at__isnull=True,
    ).order_by("device_id", "tag_key").limit(500)


async def get_tag(tenant_id: int, tag_id: int) -> KuaiiotTagDefinition:
    tid = _require_tenant(tenant_id)
    row = await KuaiiotTagDefinition.filter(
        tenant_id=tid, id=tag_id, deleted_at__isnull=True
    ).first()
    if row is None:
        raise NotFoundError("点位不存在")
    device = await KuaiiotDevice.filter(
        tenant_id=tid, id=row.device_id, deleted_at__isnull=True
    ).first()
    if device is None:
        raise NotFoundError("点位不存在")
    return row


async def update_tag(
    tenant_id: int,
    tag_id: int,
    payload: TagUpdate,
    *,
    user_id: Optional[int] = None,
) -> KuaiiotTagDefinition:
    row = await get_tag(tenant_id, tag_id)
    fields = payload.model_fields_set
    if "name" in fields:
        title = (payload.name or "").strip()
        if not title:
            raise ValidationError("点位名称不能为空")
        row.name = title
    if "value_type" in fields and payload.value_type is not None:
        value_type = payload.value_type.strip()
        if value_type not in VALUE_TYPES:
            raise ValidationError("点位值类型仅允许 number、boolean、text")
        row.value_type = value_type
    if "unit" in fields:
        row.unit = (payload.unit or "").strip() or None
    if "map_target" in fields and payload.map_target is not None:
        row.map_target = _validate_map_target(payload.map_target)
    if "fill_target" in fields:
        row.fill_target = _validate_fill_target(payload.fill_target)
    if "is_enabled" in fields and payload.is_enabled is not None:
        row.is_enabled = payload.is_enabled
    row.updated_by = user_id
    await row.save()
    return row


async def delete_tag(
    tenant_id: int,
    tag_id: int,
    *,
    user_id: Optional[int] = None,
) -> None:
    row = await get_tag(tenant_id, tag_id)
    row.deleted_at = resolve_business_datetime()
    row.deleted_by = user_id
    await row.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
