"""星数采产品物模型服务。"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from tortoise.transactions import in_transaction

from apps.kuaiiot.constants import DEVICE_BATCH_MAX, EVENT_LEVELS, MODBUS_DATA_TYPES, TAG_VALUE_TYPES, VALUE_TYPES
from apps.kuaiiot.models.iot import IotDevice, IotProduct, IotTagDefinition
from apps.kuaiiot.schemas.iot import LoadBuiltinProductPresetsResponse, ProductCreate, ProductUpdate
from apps.kuaiiot.schemas.product import (
    DeviceBatchCreate,
    ProductCreate as LocalProductCreate,
    ProductEdgeActionIn,
    ProductEventIn,
    ProductFunctionIn,
    ProductTagIn,
    ProductUpdate as LocalProductUpdate,
)
from apps.kuaiiot.services.tag_apply_helper import apply_tag_definitions_to_device
from apps.kuaiiot.services.tag_service import TagService, _validate_fill_target, _validate_map_target
from apps.kuaiiot.tag_templates import TAG_TEMPLATES
from core.utils.timezone_utils import resolve_business_datetime
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError


class ProductService:
    @staticmethod
    def _validate_tags(tags: Any) -> list[dict[str, Any]]:
        if not isinstance(tags, list) or not tags:
            raise ValidationError("tags 不能为空")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in tags:
            if not isinstance(item, dict):
                raise ValidationError("tags 项必须为对象")
            tag_key = str(item.get("tag_key") or "").strip()
            if not tag_key:
                raise ValidationError("tag_key 不能为空")
            if tag_key in seen:
                raise ValidationError(f"tag_key 重复: {tag_key}")
            seen.add(tag_key)
            map_target = str(item.get("map_target") or "").strip()
            TagService._validate_map_target(map_target)
            value_type = str(item.get("value_type") or "number").strip()
            if value_type not in {"string", "number", "boolean"}:
                raise ValidationError(f"无效 value_type: {value_type}")
            normalized.append(
                {
                    "tag_key": tag_key,
                    "name": str(item.get("name") or tag_key),
                    "value_type": value_type,
                    "unit": item.get("unit"),
                    "map_target": map_target,
                    "fill_target": item.get("fill_target"),
                }
            )
        return normalized

    @staticmethod
    def _validate_events(events: Any) -> list[dict[str, Any]]:
        if events is None:
            return []
        if not isinstance(events, list):
            raise ValidationError("events 必须为数组")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in events:
            if not isinstance(item, dict):
                raise ValidationError("events 项必须为对象")
            event_key = str(item.get("event_key") or "").strip()
            if not event_key:
                raise ValidationError("event_key 不能为空")
            if event_key in seen:
                raise ValidationError(f"event_key 重复: {event_key}")
            seen.add(event_key)
            level = str(item.get("level") or "info").strip()
            if level not in EVENT_LEVELS:
                raise ValidationError(f"无效 level: {level}")
            normalized.append(
                {
                    "event_key": event_key,
                    "name": str(item.get("name") or event_key),
                    "level": level,
                }
            )
        return normalized

    @staticmethod
    def _validate_functions(functions: Any) -> list[dict[str, Any]]:
        if functions is None:
            return []
        if not isinstance(functions, list):
            raise ValidationError("functions 必须为数组")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in functions:
            if not isinstance(item, dict):
                raise ValidationError("functions 项必须为对象")
            function_key = str(item.get("function_key") or "").strip()
            if not function_key:
                raise ValidationError("function_key 不能为空")
            if function_key in seen:
                raise ValidationError(f"function_key 重复: {function_key}")
            seen.add(function_key)
            timeout_seconds = int(item.get("timeout_seconds") or 30)
            if timeout_seconds < 1 or timeout_seconds > 3600:
                raise ValidationError("timeout_seconds 必须在 1-3600 之间")
            params_raw = item.get("params") or []
            if not isinstance(params_raw, list):
                raise ValidationError("params 必须为数组")
            params: list[dict[str, Any]] = []
            param_seen: set[str] = set()
            for param in params_raw:
                if not isinstance(param, dict):
                    raise ValidationError("params 项必须为对象")
                key = str(param.get("key") or "").strip()
                if not key:
                    raise ValidationError("param key 不能为空")
                if key in param_seen:
                    raise ValidationError(f"param key 重复: {key}")
                param_seen.add(key)
                value_type = str(param.get("value_type") or "number").strip()
                if value_type not in TAG_VALUE_TYPES:
                    raise ValidationError(f"无效 value_type: {value_type}")
                params.append(
                    {
                        "key": key,
                        "name": str(param.get("name") or key),
                        "value_type": value_type,
                        "required": bool(param.get("required", True)),
                    }
                )
            edge_action = item.get("edge_action")
            if edge_action is not None and not isinstance(edge_action, dict):
                raise ValidationError("edge_action 必须为对象")
            normalized.append(
                {
                    "function_key": function_key,
                    "name": str(item.get("name") or function_key),
                    "params": params,
                    "timeout_seconds": timeout_seconds,
                    "edge_action": edge_action,
                }
            )
        return normalized

    @staticmethod
    def get_event_definition(product: IotProduct, event_key: str) -> dict[str, Any] | None:
        events = product.events if isinstance(product.events, list) else []
        for item in events:
            if isinstance(item, dict) and str(item.get("event_key") or "") == event_key:
                return item
        return None

    @staticmethod
    async def list_products(
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        q: Optional[str] = None,
    ) -> tuple[list[IotProduct], int]:
        query = IotProduct.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if q:
            query = query.filter(name__icontains=q)
        total = await query.count()
        items = await query.order_by("-created_at", "-id").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotProduct:
        item = await IotProduct.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"产品物模型不存在: {uuid}")
        return item

    @staticmethod
    async def get_by_id(tenant_id: int, product_id: int) -> IotProduct:
        item = await IotProduct.filter(tenant_id=tenant_id, id=product_id, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"产品物模型不存在: {product_id}")
        return item

    @staticmethod
    async def create(tenant_id: int, data: ProductCreate) -> IotProduct:
        exists = await IotProduct.filter(tenant_id=tenant_id, code=data.code, deleted_at__isnull=True).exists()
        if exists:
            raise ValidationError(f"产品编码已存在: {data.code}")
        tags = ProductService._validate_tags(data.model_dump()["tags"])
        events = ProductService._validate_events(data.model_dump().get("events") or [])
        functions = ProductService._validate_functions(data.model_dump().get("functions") or [])
        return await IotProduct.create(
            tenant_id=tenant_id,
            code=data.code,
            name=data.name,
            description=data.description,
            tags=tags,
            events=events,
            functions=functions,
            remark=data.remark,
        )

    @staticmethod
    async def update(tenant_id: int, uuid: str, data: ProductUpdate) -> IotProduct:
        item = await ProductService.get_by_uuid(tenant_id, uuid)
        payload = data.model_dump(exclude_unset=True)
        if "tags" in payload:
            payload["tags"] = ProductService._validate_tags(payload["tags"])
        if "events" in payload:
            payload["events"] = ProductService._validate_events(payload["events"])
        if "functions" in payload:
            payload["functions"] = ProductService._validate_functions(payload["functions"])
        for key, value in payload.items():
            setattr(item, key, value)
        await item.save()
        return item

    @staticmethod
    async def delete(tenant_id: int, uuid: str) -> None:
        item = await ProductService.get_by_uuid(tenant_id, uuid)
        item.deleted_at = resolve_business_datetime()
        await item.save()

    @staticmethod
    async def load_builtin_presets(tenant_id: int) -> LoadBuiltinProductPresetsResponse:
        created = 0
        skipped = 0
        for code, template in TAG_TEMPLATES.items():
            exists = await IotProduct.filter(tenant_id=tenant_id, code=code, deleted_at__isnull=True).exists()
            if exists:
                skipped += 1
                continue
            tags = ProductService._validate_tags(template.get("tags") or [])
            events = ProductService._validate_events(template.get("events") or [])
            functions = ProductService._validate_functions(template.get("functions") or [])
            await IotProduct.create(
                tenant_id=tenant_id,
                code=code,
                name=str(template.get("name") or code),
                description=template.get("description"),
                tags=tags,
                events=events,
                functions=functions,
            )
            created += 1
        total = await IotProduct.filter(tenant_id=tenant_id, deleted_at__isnull=True).count()
        return LoadBuiltinProductPresetsResponse(created=created, skipped=skipped, total=total)

    @staticmethod
    async def apply_product_for_device(tenant_id: int, device: IotDevice, product_id: int) -> tuple[int, int]:
        product = await ProductService.get_by_id(tenant_id, product_id)
        tags = product.tags if isinstance(product.tags, list) else []
        return await apply_tag_definitions_to_device(tenant_id, device, tags)

    @staticmethod
    async def apply_product_for_device_id(tenant_id: int, device: IotDevice, product_id: Optional[int]) -> None:
        if not product_id:
            return
        await ProductService.apply_product_for_device(tenant_id, device, product_id)


# ---- 星数采本地执行版：产品物模型与按产品批量建设备（整型 ID 接口） ----

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
            raise ValidationError("点位值类型仅允许 number、boolean、text、string")
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
    payload: LocalProductCreate,
    *,
    user_id: Optional[int] = None,
) -> IotProduct:
    tid = _require_tenant(tenant_id)
    code = payload.code.strip()
    name = payload.name.strip()
    if not code or not name:
        raise ValidationError("产品编码和名称不能为空")
    exists = await IotProduct.filter(tenant_id=tid, code=code, deleted_at__isnull=True).exists()
    if exists:
        raise ValidationError("产品编码已存在")
    return await IotProduct.create(
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


async def list_products(tenant_id: int) -> list[IotProduct]:
    tid = _require_tenant(tenant_id)
    return await IotProduct.filter(tenant_id=tid, deleted_at__isnull=True).order_by("id").limit(500)


async def load_builtin_products(tenant_id: int, *, user_id: Optional[int] = None) -> dict[str, int]:
    """复用既有三套模板；重复加载不覆盖用户资料，也不复活已删除编码。"""
    from apps.kuaiiot.tag_templates import TAG_TEMPLATES

    tid = _require_tenant(tenant_id)
    created = 0
    async with in_transaction():
        for code, template in TAG_TEMPLATES.items():
            if await IotProduct.filter(tenant_id=tid, code=code).exists():
                continue
            await create_product(tid, LocalProductCreate(
                code=code, name=template["name"], tags=template["tags"],
            ), user_id=user_id)
            created += 1
    return {"created": created, "skipped": len(TAG_TEMPLATES) - created}


async def get_product(tenant_id: int, product_id: int) -> IotProduct:
    tid = _require_tenant(tenant_id)
    row = await IotProduct.filter(tenant_id=tid, id=product_id, deleted_at__isnull=True).first()
    if row is None:
        raise NotFoundError("产品不存在")
    return row


async def update_product(
    tenant_id: int,
    product_id: int,
    payload: LocalProductUpdate,
    *,
    user_id: Optional[int] = None,
) -> IotProduct:
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
    row.deleted_at = resolve_business_datetime()
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
    created: list[dict] = []
    async with in_transaction():
        # 编码预检放进事务，与批量插入同一临界区。
        if await IotDevice.filter(
            tenant_id=tid, code__in=codes, deleted_at__isnull=True
        ).exists():
            raise ValidationError("设备编码已存在")
        for index, code in enumerate(codes, start=1):
            token = _new_device_token()
            device = await IotDevice.create(
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
                await IotTagDefinition.create(
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
