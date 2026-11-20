"""主数据入站同步：运行历史只读（SyncFromSourceModal「同步记录」）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from apps.kuaizhizao.api._kuaizhizao_document_gate import resolve_hub_history_permission_codes
from apps.kuaizhizao.api.document_push.document_push import (
    DocumentPushRunHistoryItem,
    DocumentPushRunHistoryListResponse,
)
from core.api.deps.access import AuthContext, ensure_permission_codes, get_auth_context
from core.api.deps.deps import get_current_tenant
from core.models.sync_run_log import SYNC_ENTITY_TYPES
from core.services.data.sync_run_history_service import list_inbound_entity_sync_run_history_rows

router = APIRouter(prefix="/sync", tags=["App - Master Data - Sync"])

_MASTER_DATA_HISTORY_ENTITIES = frozenset(
    {
        "customer",
        "supplier",
        "warehouse",
        "storage_location",
        "unit",
        "material",
        "material_multi_unit",
        "material_batch_manage",
        "material_group",
        "engineering_bom",
        "process_operation",
    }
)


async def require_master_data_sync_history_read(
    request: Request,
    entity_type: str = Query(..., description="与 SyncRunLog.entity_type 一致"),
    auth: AuthContext = Depends(get_auth_context),
    tenant_id: int = Depends(get_current_tenant),
) -> None:
    et = str(entity_type or "").strip()
    if et not in _MASTER_DATA_HISTORY_ENTITIES or et not in SYNC_ENTITY_TYPES:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"不支持的主数据同步历史类型：{et!r}",
        )
    codes = resolve_hub_history_permission_codes(et)
    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        list(codes),
        require_all=False,
        check_abac=False,
    )


@router.get(
    "/run-history",
    summary="主数据入站同步运行历史（core_sync_run_logs）",
    dependencies=[Depends(require_master_data_sync_history_read)],
)
async def list_master_data_sync_run_history(
    tenant_id: Annotated[int, Depends(get_current_tenant)],
    entity_type: str = Query(..., description="customer/supplier/warehouse/unit/material/..."),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    rows, total = await list_inbound_entity_sync_run_history_rows(
        tenant_id,
        entity_type,
        skip=skip,
        limit=limit,
    )
    return DocumentPushRunHistoryListResponse(
        data=[DocumentPushRunHistoryItem.model_validate(row) for row in rows],
        total=total,
        success=True,
    )
