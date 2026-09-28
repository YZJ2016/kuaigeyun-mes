"""产品物模型与按产品批量建设备。不写星制造设备台账。"""

from __future__ import annotations

import secrets
from typing import Optional

from pydantic import ValidationError as SchemaError
from tortoise.transactions import in_transaction

from apps.kuaiiot.constants import DEVICE_BATCH_MAX, MODBUS_DATA_TYPES, VALUE_TYPES
from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.product import KuaiiotProduct
from apps.kuaiiot.models.tag import KuaiiotTagDefinition
from apps.kuaiiot.schemas.product import (
    DeviceBatchCreate,
    ProductCreate,
    ProductEdgeActionIn,
    ProductEventIn,
    ProductFunctionIn,
    ProductTagIn,
    ProductUpdate,
)
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


def _validate_tags(tags: list[ProductTagIn] | list[dict]) -> list[dict]:
    from pydantic import ValidationError as SchemaError

    seen: set[str] = set()
    stored: list[dict] = []
    for raw in tags:
        try:
            item = raw if isinstance(raw, ProductTagIn) else ProductTagIn.model_validate(raw)
        except SchemaError as exc:
            raise ValidationError("点位模板缺少必填字段") from exc
        value_type = (item.value_type or "number").strip()
        if value_type not in VALUE_TYPES:
            raise ValidationError("点位值类型仅允许 number、boolean、text")
        tag_key = item.tag_key.strip()
        if not tag_key:
            raise ValidationError("点位键不能为空")
        if tag_key in seen:
            raise ValidationError("点位键重复")
        seen.add(tag_key)
        name = item.name.strip()
        if not name:
            raise ValidationError("点位名称不能为空")
        stored.append(
            {
                "tag_key": tag_key,
                "name": name,
                "value_type": value_type,
                "unit": (item.unit or "").strip() or None,
                "map_target": _validate_map_target(item.map_target),
                "fill_target": _validate_fill_target(item.fill_target),
                "is_enabled": bool(item.is_enabled),
            }
        )
    return stored


_EVENT_SEVERITIES = {"info", "warning", "critical"}


def _validate_events(events: list) -> list[dict]:
    seen: set[str] = set()
    stored: list[dict] = []
    for raw in events or []:
        try:
            item = raw if isinstance(raw, ProductEventIn) else ProductEventIn.model_validate(raw)
        except SchemaError as exc:
            raise ValidationError("事件定义无效") from exc
        event_key = item.event_key.strip()
        name = item.name.strip()
        severity = item.severity.strip().lower()
        if not event_key or not name:
            raise ValidationError("事件键和名称不能为空")
        if event_key in seen:
            raise ValidationError("event_key 重复")
        if severity not in _EVENT_SEVERITIES:
            raise ValidationError("事件严重级别仅允许 info、warning、critical")
        seen.add(event_key)
        row = {"event_key": event_key, "name": name, "severity": severity}
        if item.message and item.message.strip():
            row["message"] = item.message.strip()
        stored.append(row)
    return stored


def _validate_edge_action(raw) -> dict | None:
    if raw is None:
        return None
    try:
        action = raw if isinstance(raw, ProductEdgeActionIn) else ProductEdgeActionIn.model_validate(raw)
    except SchemaError as exc:
        raise ValidationError("edge_action 无效") from exc
    action_type = (action.type or "modbus_write").strip() or "modbus_write"
    param_key = (action.param_key or "value").strip() or "value"
    data_type = (action.data_type or "uint16").strip().lower() or "uint16"
    stored: dict = {
        "type": action_type,
        "param_key": param_key,
        "data_type": data_type,
        "scale": float(action.scale),
    }
    if action_type == "modbus_write":
        if action.address is None or action.address < 0:
            raise ValidationError("modbus_write 缺少 address")
        if data_type not in MODBUS_DATA_TYPES:
            raise ValidationError("data_type 无效")
        stored["address"] = int(action.address)
    elif action.address is not None:
        stored["address"] = int(action.address)
    return stored


def _validate_functions(functions: list) -> list[dict]:
    seen: set[str] = set()
    stored: list[dict] = []
    for raw in functions or []:
        try:
            item = raw if isinstance(raw, ProductFunctionIn) else ProductFunctionIn.model_validate(raw)
        except SchemaError as exc:
            raise ValidationError("指令定义无效") from exc
        function_key = item.function_key.strip()
        name = item.name.strip()
        if not function_key or not name:
            raise ValidationError("指令键和名称不能为空")
        if function_key in seen:
            raise ValidationError("function_key 重复")
        seen.add(function_key)
        row: dict = {
            "function_key": function_key,
            "name": name,
            "params": [
                {
                    "key": param.key.strip(),
                    "name": (param.name or "").strip(),
                    "value_type": (param.value_type or "number").strip() or "number",
                    "required": bool(param.required),
                }
                for param in item.params
                if param.key.strip()
            ],
        }
        if item.timeout_seconds is not None:
            row["timeout_seconds"] = int(item.timeout_seconds)
        edge_action = _validate_edge_action(item.edge_action)
        if edge_action is not None:
            row["edge_action"] = edge_action
        stored.append(row)
    return stored


def _device_codes(code_prefix: str, count: int) -> list[str]:
    prefix = code_prefix.strip()
    if not prefix:
        raise ValidationError("设备编码前缀不能为空")
    codes = [f"{prefix}-{index:03d}" for index in range(1, count + 1)]
    if any(len(code) > 50 for code in codes):
        raise ValidationError("设备编码过长")
    return codes


async def create_product(
    tenant_id: int,
    payload: ProductCreate,
    *,
    user_id: Optional[int] = None,
) -> KuaiiotProduct:
    tid = _require_tenant(tenant_id)
    code = payload.code.strip()
    name = payload.name.strip()
    if not code or not name:
        raise ValidationError("产品编码和名称不能为空")
    exists = await KuaiiotProduct.filter(tenant_id=tid, code=code, deleted_at__isnull=True).exists()
    if exists:
        raise ValidationError("产品编码已存在")
    return await KuaiiotProduct.create(
        tenant_id=tid,
        code=code,
        name=name,
        description=payload.description,
        tags=_validate_tags(payload.tags),
        events=_validate_events(payload.events),
        functions=_validate_functions(payload.functions),
        remark=payload.remark,
        created_by=user_id,
        updated_by=user_id,
    )


async def list_products(tenant_id: int) -> list[KuaiiotProduct]:
    tid = _require_tenant(tenant_id)
    return await KuaiiotProduct.filter(tenant_id=tid, deleted_at__isnull=True).order_by("id")


async def get_product(tenant_id: int, product_id: int) -> KuaiiotProduct:
    tid = _require_tenant(tenant_id)
    row = await KuaiiotProduct.filter(tenant_id=tid, id=product_id, deleted_at__isnull=True).first()
    if row is None:
        raise NotFoundError("产品不存在")
    return row


async def update_product(
    tenant_id: int,
    product_id: int,
    payload: ProductUpdate,
    *,
    user_id: Optional[int] = None,
) -> KuaiiotProduct:
    row = await get_product(tenant_id, product_id)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise ValidationError("产品名称不能为空")
        row.name = name
    if payload.description is not None:
        row.description = payload.description
    if payload.remark is not None:
        row.remark = payload.remark
    if payload.tags is not None:
        row.tags = _validate_tags(payload.tags)
    if payload.events is not None:
        row.events = _validate_events(payload.events)
    if payload.functions is not None:
        row.functions = _validate_functions(payload.functions)
    row.updated_by = user_id
    await row.save()
    return row


async def delete_product(tenant_id: int, product_id: int, *, user_id: Optional[int] = None) -> None:
    row = await get_product(tenant_id, product_id)
    from tortoise import timezone

    row.deleted_at = timezone.now()
    row.deleted_by = user_id
    await row.save(update_fields=["deleted_at", "deleted_by", "updated_at"])


async def batch_create_devices(
    tenant_id: int,
    payload: DeviceBatchCreate,
    *,
    user_id: Optional[int] = None,
) -> list[dict]:
    tid = _require_tenant(tenant_id)
    count = payload.count
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValidationError("一批至少 1 台")
    if count > DEVICE_BATCH_MAX:
        raise ValidationError("一批不超过 100 台")
    product = await get_product(tid, payload.product_id)
    tags = _validate_tags(product.tags or [])
    name_prefix = payload.name_prefix.strip()
    if not name_prefix:
        raise ValidationError("设备名称前缀不能为空")
    codes = _device_codes(payload.code_prefix, count)
    if await KuaiiotDevice.filter(tenant_id=tid, code__in=codes, deleted_at__isnull=True).exists():
        raise ValidationError("设备编码已存在")
    created: list[dict] = []
    async with in_transaction():
        for index, code in enumerate(codes, start=1):
            token = _new_device_token()
            device = await KuaiiotDevice.create(
                tenant_id=tid,
                external_device_id=code,
                code=code,
                name=f"{name_prefix}{index}",
                device_token=token,
                product_id=product.id,
                created_by=user_id,
                updated_by=user_id,
            )
            for tag in tags:
                await KuaiiotTagDefinition.create(
                    tenant_id=tid,
                    device_id=device.id,
                    tag_key=tag["tag_key"],
                    name=tag["name"],
                    value_type=tag["value_type"],
                    unit=tag["unit"],
                    map_target=tag["map_target"],
                    fill_target=tag["fill_target"],
                    is_enabled=tag["is_enabled"],
                    created_by=user_id,
                    updated_by=user_id,
                )
            created.append(
                {
                    "id": device.id,
                    "uuid": device.uuid,
                    "code": device.code,
                    "name": device.name,
                    "product_id": product.id,
                    "device_token": token,
                }
            )
    return created
