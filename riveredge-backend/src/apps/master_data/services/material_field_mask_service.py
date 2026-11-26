"""物料 API 字段权限：默认供应商等嵌套在 source_config / defaults 内的字段。"""

from __future__ import annotations

from typing import Any, Iterable, List, TypeVar

from core.services.authorization.permission_policy_service import PermissionPolicyService
from apps.master_data.schemas.material_schemas import (
    MaterialCreate,
    MaterialListResponse,
    MaterialResponse,
    MaterialUpdate,
)

MATERIAL_FIELD_RESOURCE = "master-data:material"

TMaterialSchema = TypeVar("TMaterialSchema", MaterialResponse, MaterialListResponse)


def _strip_denied_supplier_fields_from_dict(payload: dict[str, Any]) -> None:
    """写请求：hidden 时移除客户端提交的默认供应商，避免旁路改库。"""
    for cfg_key in ("source_config", "sourceConfig"):
        cfg = payload.get(cfg_key)
        if isinstance(cfg, dict):
            cfg = dict(cfg)
            cfg.pop("default_supplier_id", None)
            cfg.pop("default_supplier_name", None)
            payload[cfg_key] = cfg
    defaults = payload.get("defaults")
    if isinstance(defaults, dict):
        defs = dict(defaults)
        defs.pop("defaultSuppliers", None)
        defs.pop("defaultSupplierIds", None)
        payload["defaults"] = defs


async def sanitize_material_write_payload(
    tenant_id: int,
    user_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    out = dict(payload)
    masks = await PermissionPolicyService.get_user_effective_field_masks(
        tenant_id=tenant_id,
        user_id=user_id,
        resource=MATERIAL_FIELD_RESOURCE,
    )
    level = masks.get(MATERIAL_FIELD_RESOURCE, {}).get("default_supplier_id")
    if level == "hidden":
        _strip_denied_supplier_fields_from_dict(out)
    return out


async def mask_material_dict(
    tenant_id: int,
    user_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await PermissionPolicyService.apply_material_field_masks_to_dict(
        tenant_id=tenant_id,
        user_id=user_id,
        payload=payload,
    )


async def mask_material_response(
    tenant_id: int,
    user_id: int,
    material: MaterialResponse,
) -> MaterialResponse:
    dumped = material.model_dump(by_alias=True)
    masked = await mask_material_dict(tenant_id, user_id, dumped)
    return MaterialResponse.model_validate(masked)


async def mask_material_list_response(
    tenant_id: int,
    user_id: int,
    response: MaterialListResponse,
) -> MaterialListResponse:
    items: List[MaterialResponse] = []
    for row in response.items:
        items.append(await mask_material_response(tenant_id, user_id, row))
    return MaterialListResponse(items=items, total=response.total)


async def mask_material_response_list(
    tenant_id: int,
    user_id: int,
    rows: Iterable[MaterialResponse],
) -> list[MaterialResponse]:
    out: list[MaterialResponse] = []
    for row in rows:
        out.append(await mask_material_response(tenant_id, user_id, row))
    return out


async def sanitize_material_create(
    tenant_id: int,
    user_id: int,
    data: MaterialCreate,
) -> MaterialCreate:
    raw = data.model_dump(exclude_unset=True, by_alias=True)
    cleaned = await sanitize_material_write_payload(tenant_id, user_id, raw)
    return MaterialCreate.model_validate(cleaned)


async def sanitize_material_update(
    tenant_id: int,
    user_id: int,
    data: MaterialUpdate,
) -> MaterialUpdate:
    raw = data.model_dump(exclude_unset=True, by_alias=True)
    cleaned = await sanitize_material_write_payload(tenant_id, user_id, raw)
    return MaterialUpdate.model_validate(cleaned)
