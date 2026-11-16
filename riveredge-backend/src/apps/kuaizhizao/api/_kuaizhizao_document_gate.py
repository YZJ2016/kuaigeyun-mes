"""系统内下推 / 外推 API 的权限码映射（唯一真源，禁止路由内散落 alias）。"""

from __future__ import annotations

from typing import Iterable

from fastapi import Depends, HTTPException, Request, status

from core.api.deps.access import AuthContext, ensure_permission_codes, get_auth_context
from core.api.deps.deps import get_current_tenant

# 外推 POST：source_type → :push（与 FE useToolbarSyncPushFlags 资源一致）
_EXTERNAL_PUSH_BY_SOURCE: dict[str, str] = {
    "work_order": "kuaizhizao:work-order:push",
    "reporting_record": "kuaizhizao:production-execution-reporting:push",
    "sales_order": "kuaizhizao:sales-order:push",
    "purchase_order": "kuaizhizao:purchase-order:push",
    "purchase_receipt": "kuaizhizao:inbound:push",
    "sales_delivery": "kuaizhizao:outbound:push",
    "other_outbound": "kuaizhizao:other-outbound:push",
    "other_inbound": "kuaizhizao:other-inbound:push",
    "stocktaking": "kuaizhizao:warehouse-management-stocktaking:push",
    "material_batch": "kuaizhizao:inventory:push",
    "material": "master-data:material:push",
    "engineering_bom": "master-data:process:engineering-bom:push",
    "process_operation": "master-data:process:operation:push",
    "payment_application": "kuaizhizao:payment-application:push",
}

# Hub「同步记录」：外推 source_type → 入站 SyncRunLog.entity_type（不一致时）
_HISTORY_INBOUND_ENTITY_BY_SOURCE: dict[str, str] = {
    "reporting_record": "reporting",
    "material_batch": "inventory",
}

# 主数据等仅入站同步（无 :push）：run-history 只读权限
_INBOUND_ONLY_HISTORY_PERMISSION: dict[str, tuple[str, ...]] = {
    "warehouse": (
        "master-data:warehouse:warehouse:read",
        "master-data:warehouse:warehouse:update",
    ),
    "storage_location": (
        "master-data:warehouse:storage-location:read",
        "master-data:warehouse:storage-location:update",
    ),
    "customer": (
        "master-data:supply-chain:customer:read",
        "master-data:supply-chain:customer:update",
    ),
    "supplier": (
        "master-data:supply-chain:supplier:read",
        "master-data:supply-chain:supplier:update",
    ),
    "unit": (
        "master-data:material-unit:read",
        "master-data:material-unit:update",
    ),
    "material": (
        "master-data:material:read",
        "master-data:material:update",
    ),
    "material_group": (
        "master-data:material:read",
        "master-data:material:update",
    ),
}

_EXTERNAL_PUSH_ANY: tuple[str, ...] = tuple(sorted(set(_EXTERNAL_PUSH_BY_SOURCE.values())))

# 系统内下推：(source_type, target_type) → 创建目标单所需码
_INTERNAL_PUSH_REQUIRED: dict[tuple[str, str], tuple[str, ...]] = {
    ("demand", "demand_computation"): (
        "kuaizhizao:plan-management-demand-computation:create",
    ),
    ("demand_computation", "work_order"): ("kuaizhizao:work-order:create",),
    ("demand_computation", "purchase_order"): ("kuaizhizao:purchase-order:create",),
    ("demand_computation", "purchase_requisition"): ("kuaizhizao:purchase-requisition:create",),
    ("purchase_receipt", "incoming_inspection"): (
        "kuaizhizao:quality-management-incoming-inspection:create",
    ),
}

# 系统内加载：建立关联，需改上游需求计算
_INTERNAL_PULL_REQUIRED: dict[tuple[str, str], tuple[str, ...]] = {
    ("demand_computation", "work_order"): ("kuaizhizao:plan-management-demand-computation:update",),
    ("demand_computation", "purchase_order"): ("kuaizhizao:plan-management-demand-computation:update",),
}

# 统一撤回：document_type → :revoke
_REVERSE_BY_DOCUMENT: dict[str, str] = {
    "demand": "kuaizhizao:plan-management-demand-management:revoke",
    "sales_order": "kuaizhizao:sales-order:revoke",
    "work_order": "kuaizhizao:work-order:revoke",
}


def resolve_external_push_permission(source_type: str) -> str:
    key = str(source_type or "").strip()
    code = _EXTERNAL_PUSH_BY_SOURCE.get(key)
    if not code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PUSH_SOURCE_NOT_ALLOWED",
                "message": f"不支持的外推源类型，或未配置推送权限：{key!r}",
            },
        )
    return code


def resolve_history_inbound_entity_type(source_type: str) -> str | None:
    """Hub 同步记录入站 entity：显式别名优先，否则 source_type 本身若在 SYNC 集合则用之。"""
    key = str(source_type or "").strip()
    if not key:
        return None
    aliased = _HISTORY_INBOUND_ENTITY_BY_SOURCE.get(key)
    if aliased:
        return aliased
    from core.models.sync_run_log import SYNC_ENTITY_TYPES

    if key in SYNC_ENTITY_TYPES and key != "document_push":
        return key
    return None


def resolve_hub_history_permission_codes(source_type: str) -> tuple[str, ...]:
    """同步记录只读：持有该源 :push 或同资源 :sync 之一即可。"""
    key = str(source_type or "").strip()
    inbound_only = _INBOUND_ONLY_HISTORY_PERMISSION.get(key)
    if inbound_only:
        return inbound_only
    push_code = resolve_external_push_permission(key)
    if push_code.endswith(":push"):
        sync_code = f"{push_code[: -len('push')]}sync"
        return (push_code, sync_code)
    return (push_code,)


def resolve_internal_push_permissions(source_type: str, target_type: str) -> tuple[str, ...]:
    key = (str(source_type or "").strip(), str(target_type or "").strip())
    codes = _INTERNAL_PUSH_REQUIRED.get(key)
    if not codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PUSH_PAIR_NOT_ALLOWED",
                "message": f"不支持的下推组合或未配置权限：{key[0]} → {key[1]}",
            },
        )
    return codes


def resolve_internal_pull_permissions(source_type: str, target_type: str) -> tuple[str, ...]:
    # pull API：source=上游，target=下游
    key = (str(source_type or "").strip(), str(target_type or "").strip())
    codes = _INTERNAL_PULL_REQUIRED.get(key)
    if not codes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PULL_PAIR_NOT_ALLOWED",
                "message": f"不支持的加载组合或未配置权限：{key[0]} ← {key[1]}",
            },
        )
    return codes


def all_reverse_permission_codes() -> tuple[str, ...]:
    return tuple(sorted(set(_REVERSE_BY_DOCUMENT.values())))


def resolve_reverse_permission(document_type: str) -> str:
    key = str(document_type or "").strip()
    code = _REVERSE_BY_DOCUMENT.get(key)
    if not code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "REVERSE_TYPE_NOT_ALLOWED",
                "message": f"不支持的撤回单据类型或未配置权限：{key!r}",
            },
        )
    return code


async def _ensure(
    request: Request,
    auth: AuthContext,
    tenant_id: int,
    codes: Iterable[str],
    *,
    require_all: bool,
) -> None:
    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        list(codes),
        require_all=require_all,
        check_abac=False,
    )


def require_any_external_push_permission():
    """GET profiles / slo：具备任一外推 :push 即可。"""

    async def dependency(
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
        tenant_id: int = Depends(get_current_tenant),
    ) -> AuthContext:
        await _ensure(request, auth, tenant_id, _EXTERNAL_PUSH_ANY, require_all=False)
        return auth

    return dependency
