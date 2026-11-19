"""通用外推 API（任意页面：source_type + source_id + target_profile[s]）。

注意：与 /document-push-pull（系统内下推）不同。
P2：支持 target_profiles 多目标 fan-out；target_profile=* 读业务配置。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from apps.kuaizhizao.api._kuaizhizao_document_gate import (
    resolve_external_push_permission,
    resolve_hub_history_permission_codes,
)
from apps.kuaizhizao.services.document_push_service import DocumentPushService
from core.api.deps import get_current_tenant, get_current_user
from core.api.deps.access import AuthContext, ensure_permission_codes, get_auth_context
from core.schemas.base import BaseSchema
from infra.exceptions.exceptions import BusinessLogicError, ValidationError
from infra.models.user import User

router = APIRouter(
    prefix="/document-push",
    tags=["App - Kuaige Zhizao - Document Push (External)"],
)


class DocumentPushTargetBody(BaseModel):
    connection_code: Optional[str] = None
    save_api_uuid: Optional[str] = None
    target_profile: str


class DocumentPushBody(BaseModel):
    source_type: str = Field(..., description="源单据类型，如 work_order / reporting_record")
    source_id: int = Field(..., description="源单据 ID")
    targets: Optional[List[DocumentPushTargetBody]] = Field(
        None,
        description="多连接器目标（每条独立 connection + Save 接口 + profile）",
    )
    target_profile: Optional[str] = Field(
        None,
        description="单一目标，如 kingdee_prd_mo / oa_http_webhook；传 * 则按业务配置多目标",
    )
    target_profiles: Optional[List[str]] = Field(
        None,
        description="多目标列表（优先于 target_profile）；一单可同时推金蝶+OA",
    )
    connection_code: Optional[str] = Field(None, description="覆盖应用连接器 code")
    save_api_uuid: Optional[str] = Field(None, description="覆盖接口管理 Save UUID")
    dry_run: bool = Field(False, description="只组装报文不落库不调用")
    force: bool = Field(
        False,
        description="强制重新推送：已有 DocumentRelation 时仍新建外部单并记录二次推送关联（静默自动推送勿传）",
    )


class DocumentPushProfileOut(BaseModel):
    source_type: str
    target_profile: str


class DocumentPushRunHistoryItem(BaseSchema):
    """同步/外推运行历史（core_sync_run_logs，只读）。"""

    id: int
    entity_type: str = "document_push"
    mode: str = "push"
    status: str = "success"
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    fetched: int = 0
    truncated: bool = False
    duration_ms: int = 0
    error_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    category: Optional[str] = None
    connector_type: Optional[str] = None
    target_profile: Optional[str] = None


class DocumentPushRunHistoryListResponse(BaseSchema):
    data: List[DocumentPushRunHistoryItem] = Field(default_factory=list)
    total: int = 0
    success: bool = True


@router.get("/slo", summary="Document push SLO by category×connector×profile")
async def get_document_push_slo(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> Dict[str, Any]:
    """进程内 SLO 快照（category × connector_type × target_profile）。"""
    _ = current_user, tenant_id
    from core.services.integration.document_push_slo import document_push_slo

    return {"dimensions": ["category", "connector_type", "target_profile"], "rows": document_push_slo.snapshot()}


@router.get("/status", summary="Latest external push status per target profile for a document")
async def get_document_push_status(
    source_type: str = Query(..., description="源单据类型，如 work_order / sales_order"),
    source_id: int = Query(..., description="源单据 ID"),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> Dict[str, Any]:
    """按源单据查各 target_profile 最近一次外推结果（spec 142：失败须可见未推送）。

    数据源为 core_sync_run_logs（entity_type=document_push）：status=failed 即
    「已尝试但未推送成功」，无记录表示从未推送；重试走 POST /document-push。
    """
    _ = current_user
    from core.models.sync_run_log import SyncRunLog

    rows = await SyncRunLog.filter(
        tenant_id=tenant_id,
        entity_type="document_push",
        source_type=str(source_type).strip(),
        source_id=int(source_id),
    ).order_by("-id").all()
    latest: Dict[str, Any] = {}
    for row in rows:
        profile = str(getattr(row, "target_profile", None) or "")
        if profile and profile not in latest:
            latest[profile] = row
    pushes = [
        {
            "target_profile": profile,
            "status": row.status,
            "pushed": row.status == "success",
            "connector_type": getattr(row, "connector_type", None),
            "category": getattr(row, "category", None),
            "error_summary": getattr(row, "error_summary", None),
            "duration_ms": getattr(row, "duration_ms", None),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }
        for profile, row in latest.items()
    ]
    return {
        "source_type": str(source_type).strip(),
        "source_id": int(source_id),
        # 顶层汇总：pushed=所有目标均已成功（无记录视为未推送）；ever_pushed=任一目标成功过
        "pushed": bool(pushes) and all(p["pushed"] for p in pushes),
        "ever_pushed": any(p["pushed"] for p in pushes),
        "pushes": pushes,
    }


@router.get("/profiles", summary="List supported external push profiles")
async def list_document_push_profiles(
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> List[DocumentPushProfileOut]:
    _ = current_user, tenant_id
    return [DocumentPushProfileOut(**item) for item in DocumentPushService().list_profiles()]


@router.get(
    "/run-history",
    summary="List sync/push run history for a Hub source_type",
)
async def list_document_push_run_history(
    request: Request,
    source_type: str = Query(..., min_length=1, description="业务源类型（Hub historySourceType）"),
    target_profiles: Optional[str] = Query(
        None,
        description="逗号分隔；仅过滤 entity_type=document_push 的 target_profile",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> DocumentPushRunHistoryListResponse:
    """只读：入站 SyncRunLog + 外推（document_push 且摘要前缀匹配）。"""
    _ = current_user
    st = str(source_type or "").strip()
    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        list(resolve_hub_history_permission_codes(st)),
        require_all=False,
        check_abac=False,
    )

    from core.services.data.sync_run_history_service import list_sync_run_history_rows

    profiles = [
        p.strip()
        for p in str(target_profiles or "").split(",")
        if p and str(p).strip()
    ]
    rows, total = await list_sync_run_history_rows(
        tenant_id,
        st,
        target_profiles=profiles,
        skip=skip,
        limit=limit,
    )
    return DocumentPushRunHistoryListResponse(
        data=[DocumentPushRunHistoryItem.model_validate(row) for row in rows],
        total=total,
        success=True,
    )


class DocumentPushReconcileBody(BaseModel):
    source_type: str = Field(..., description="Hub source_type，如 purchase_receipt")
    source_ids: List[int] = Field(
        ...,
        min_length=1,
        description="当前页或勾选的本地单据 ID（最多 50）",
    )


class DocumentPushReconcileRow(BaseSchema):
    source_id: int
    local_code: str = ""
    local_status: str = ""
    local_qty: Optional[str] = None
    remote_billno: Optional[str] = None
    remote_status: Optional[str] = None
    remote_qty: Optional[str] = None
    result: str = "not_pushed"
    mismatch_fields: List[str] = Field(default_factory=list)
    message: Optional[str] = None


class DocumentPushReconcileResponse(BaseSchema):
    success: bool = True
    source_type: str
    target_type: str = ""
    form_id: str = ""
    doc_label: str = ""
    total: int = 0
    summary: Dict[str, int] = Field(default_factory=dict)
    rows: List[DocumentPushReconcileRow] = Field(default_factory=list)


@router.post(
    "/reconcile",
    summary="Reconcile local documents vs Kingdee IM bills",
)
async def reconcile_document_push(
    body: DocumentPushReconcileBody,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> DocumentPushReconcileResponse:
    """组件级同步对账：按 DocumentRelation.billno 查金蝶，对比本地状态/数量。"""
    _ = current_user
    push_code = resolve_external_push_permission(body.source_type)
    await ensure_permission_codes(
        auth,
        tenant_id,
        request,
        [push_code],
        require_all=True,
        check_abac=False,
    )
    from apps.kuaizhizao.services.document_push_reconcile_service import (
        reconcile_documents,
    )

    try:
        payload = await reconcile_documents(
            tenant_id,
            source_type=body.source_type,
            source_ids=body.source_ids,
        )
    except ValidationError as exc:
        raise BusinessLogicError(str(exc)) from exc
    return DocumentPushReconcileResponse(
        success=bool(payload.get("success", True)),
        source_type=str(payload.get("source_type") or body.source_type),
        target_type=str(payload.get("target_type") or ""),
        form_id=str(payload.get("form_id") or ""),
        doc_label=str(payload.get("doc_label") or ""),
        total=int(payload.get("total") or 0),
        summary=dict(payload.get("summary") or {}),
        rows=[DocumentPushReconcileRow(**row) for row in (payload.get("rows") or [])],
    )


@router.post("", summary="Push document to external system")
async def push_document_external(
    body: DocumentPushBody,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> Dict[str, Any]:
    try:
        targets_payload = None
        if body.targets:
            targets_payload = [t.model_dump() for t in body.targets]
        return await DocumentPushService().push(
            tenant_id=tenant_id,
            acting_user_id=int(getattr(current_user, "id", 0) or 0),
            source_type=body.source_type,
            source_id=body.source_id,
            targets=targets_payload,
            target_profile=body.target_profile,
            target_profiles=body.target_profiles,
            connection_code=body.connection_code,
            save_api_uuid=body.save_api_uuid,
            dry_run=bool(body.dry_run),
            force=bool(body.force),
        )
    except ValidationError as exc:
        raise BusinessLogicError(str(exc)) from exc
