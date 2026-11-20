"""质量体系 API：体系文件 / 内审 / 管理评审"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from datetime import datetime

from apps.kuaizhizao.schemas.quality_qms import (
    QmsInternalAuditAnnualPlanCreate,
    QmsInternalAuditAnnualPlanListResponse,
    QmsInternalAuditAnnualPlanResponse,
    QmsInternalAuditAnnualPlanUpdate,
    QmsInternalAuditChecklistItemCreate,
    QmsInternalAuditChecklistItemListResponse,
    QmsInternalAuditChecklistItemResponse,
    QmsInternalAuditChecklistItemUpdate,
    QmsInternalAuditCreate,
    QmsInternalAuditListResponse,
    QmsInternalAuditResponse,
    QmsInternalAuditUpdate,
    QmsNonconformityReportCreate,
    QmsNonconformityReportListResponse,
    QmsNonconformityReportResponse,
    QmsNonconformityReportUpdate,
    QmsCorrectiveActionCreate,
    QmsCorrectiveActionFromSource,
    QmsCorrectiveActionListResponse,
    QmsCorrectiveActionResponse,
    QmsCorrectiveActionUpdate,
    QmsManagementReviewResolutionCreate,
    QmsManagementReviewResolutionListResponse,
    QmsManagementReviewResolutionResponse,
    QmsManagementReviewResolutionUpdate,
    QmsIsoClauseComplianceSummary,
    QmsIsoClauseCreate,
    QmsIsoClauseListResponse,
    QmsIsoClauseLoadPresetResult,
    QmsIsoClauseRelatedAuditsResponse,
    QmsIsoClauseRelatedDocumentsResponse,
    QmsIsoClauseResponse,
    QmsIsoClauseTreeNode,
    QmsIsoClauseUpdate,
    QmsManagementReviewCreate,
    QmsManagementReviewListResponse,
    QmsManagementReviewResponse,
    QmsManagementReviewUpdate,
    QmsManagementReviewInputSummary,
    QmsSystemDocumentCirculationCreate,
    QmsSystemDocumentCirculationListResponse,
    QmsSystemDocumentCirculationResponse,
    QmsSystemDocumentCreate,
    QmsSystemDocumentListResponse,
    QmsSystemDocumentResponse,
    QmsSystemDocumentReviseRequest,
    QmsSystemDocumentRejectRequest,
    QmsSystemDocumentReviewDueSummary,
    QmsSystemDocumentUpdate,
    QmsSystemDocumentVersionListResponse,
    QmsStandardCreate,
    QmsStandardListResponse,
    QmsStandardResponse,
    QmsStandardUpdate,
    QmsQualityObjectiveCreate,
    QmsQualityObjectiveListResponse,
    QmsQualityObjectiveResponse,
    QmsQualityObjectiveUpdate,
    QmsLegalRegulationCreate,
    QmsLegalRegulationListResponse,
    QmsLegalRegulationResponse,
    QmsLegalRegulationUpdate,
    QmsExternalAuditCreate,
    QmsExternalAuditListResponse,
    QmsExternalAuditResponse,
    QmsExternalAuditUpdate,
    QmsCertificateCreate,
    QmsCertificateListResponse,
    QmsCertificateResponse,
    QmsCertificateUpdate,
)
from apps.kuaizhizao.services.qms_iso_clause_service import iso_clause_service
from apps.kuaizhizao.services.qms_standard_service import qms_standard_service
from apps.kuaizhizao.services.quality_qms_service import (
    QmsInternalAuditService,
    QmsManagementReviewService,
    QmsSystemDocumentService,
)
from apps.kuaizhizao.services.qms_audit_nc_service import (
    annual_plan_service,
    checklist_service,
    nonconformity_service,
)
from apps.kuaizhizao.services.qms_corrective_action_service import (
    corrective_action_service,
    resolution_service,
)
from apps.kuaizhizao.services.qms_phase5_service import (
    certificate_service,
    external_audit_service,
    legal_regulation_service,
    quality_objective_service,
)
from core.api.deps import get_current_tenant, get_current_user
from core.api.deps.access import require_permission_codes
from core.services.authorization.user_permission_service import UserPermissionService
from infra.models.user import User

router = APIRouter(tags=["App - Kuaige Zhizao - Quality System"])

doc_service = QmsSystemDocumentService()
audit_service = QmsInternalAuditService()
review_service = QmsManagementReviewService()

_DOC_READ = Depends(require_permission_codes("kuaizhizao:quality-management-system-documents:read"))
_DOC_CREATE = Depends(require_permission_codes("kuaizhizao:quality-management-system-documents:create"))
_DOC_UPDATE = Depends(require_permission_codes("kuaizhizao:quality-management-system-documents:update"))
_DOC_DELETE = Depends(require_permission_codes("kuaizhizao:quality-management-system-documents:delete"))
_DOC_PUBLISH = Depends(require_permission_codes("kuaizhizao:quality-management-system-documents:publish"))
_DOC_SUBMIT = Depends(require_permission_codes("kuaizhizao:quality-management-system-documents:submit"))
_DOC_APPROVE = Depends(require_permission_codes("kuaizhizao:quality-management-system-documents:approve"))
_DOC_REJECT = Depends(require_permission_codes("kuaizhizao:quality-management-system-documents:reject"))
_DOC_OBSOLETE = Depends(require_permission_codes("kuaizhizao:quality-management-system-documents:obsolete"))

_AUDIT_READ = Depends(require_permission_codes("kuaizhizao:quality-management-internal-audits:read"))
_AUDIT_CREATE = Depends(require_permission_codes("kuaizhizao:quality-management-internal-audits:create"))
_AUDIT_UPDATE = Depends(require_permission_codes("kuaizhizao:quality-management-internal-audits:update"))
_AUDIT_DELETE = Depends(require_permission_codes("kuaizhizao:quality-management-internal-audits:delete"))

_NC_READ = Depends(require_permission_codes("kuaizhizao:quality-management-nonconformity-reports:read"))
_NC_CREATE = Depends(require_permission_codes("kuaizhizao:quality-management-nonconformity-reports:create"))
_NC_UPDATE = Depends(require_permission_codes("kuaizhizao:quality-management-nonconformity-reports:update"))
_NC_DELETE = Depends(require_permission_codes("kuaizhizao:quality-management-nonconformity-reports:delete"))
_NC_CLOSE = Depends(require_permission_codes("kuaizhizao:quality-management-nonconformity-reports:close"))

_CA_READ = Depends(require_permission_codes("kuaizhizao:quality-management-corrective-actions:read"))
_CA_CREATE = Depends(require_permission_codes("kuaizhizao:quality-management-corrective-actions:create"))
_CA_UPDATE = Depends(require_permission_codes("kuaizhizao:quality-management-corrective-actions:update"))
_CA_DELETE = Depends(require_permission_codes("kuaizhizao:quality-management-corrective-actions:delete"))
_CA_CLOSE = Depends(require_permission_codes("kuaizhizao:quality-management-corrective-actions:close"))

_REVIEW_READ = Depends(require_permission_codes("kuaizhizao:quality-management-management-reviews:read"))
_REVIEW_CREATE = Depends(require_permission_codes("kuaizhizao:quality-management-management-reviews:create"))
_REVIEW_UPDATE = Depends(require_permission_codes("kuaizhizao:quality-management-management-reviews:update"))
_REVIEW_DELETE = Depends(require_permission_codes("kuaizhizao:quality-management-management-reviews:delete"))

_CLAUSE_READ = Depends(require_permission_codes("kuaizhizao:quality-management-iso-clauses:read"))
_CLAUSE_CREATE = Depends(require_permission_codes("kuaizhizao:quality-management-iso-clauses:create"))
_CLAUSE_UPDATE = Depends(require_permission_codes("kuaizhizao:quality-management-iso-clauses:update"))
_CLAUSE_DELETE = Depends(require_permission_codes("kuaizhizao:quality-management-iso-clauses:delete"))
_CLAUSE_EXPORT = Depends(require_permission_codes("kuaizhizao:quality-management-iso-clauses:export"))

_OBJ_READ = Depends(require_permission_codes("kuaizhizao:quality-management-quality-objectives:read"))
_OBJ_CREATE = Depends(require_permission_codes("kuaizhizao:quality-management-quality-objectives:create"))
_OBJ_UPDATE = Depends(require_permission_codes("kuaizhizao:quality-management-quality-objectives:update"))
_OBJ_DELETE = Depends(require_permission_codes("kuaizhizao:quality-management-quality-objectives:delete"))

_LEGAL_READ = Depends(require_permission_codes("kuaizhizao:quality-management-legal-regulations:read"))
_LEGAL_CREATE = Depends(require_permission_codes("kuaizhizao:quality-management-legal-regulations:create"))
_LEGAL_UPDATE = Depends(require_permission_codes("kuaizhizao:quality-management-legal-regulations:update"))
_LEGAL_DELETE = Depends(require_permission_codes("kuaizhizao:quality-management-legal-regulations:delete"))

_EXT_READ = Depends(require_permission_codes("kuaizhizao:quality-management-external-audits:read"))
_EXT_CREATE = Depends(require_permission_codes("kuaizhizao:quality-management-external-audits:create"))
_EXT_UPDATE = Depends(require_permission_codes("kuaizhizao:quality-management-external-audits:update"))
_EXT_DELETE = Depends(require_permission_codes("kuaizhizao:quality-management-external-audits:delete"))


@router.post("/qms/system-documents", response_model=QmsSystemDocumentResponse, summary="Create system document")
async def create_system_document(
    payload: QmsSystemDocumentCreate,
    _auth=_DOC_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentResponse:
    actor_name = (
        getattr(current_user, "full_name", None)
        or getattr(current_user, "username", None)
        or str(current_user.id)
    )
    return await doc_service.create_document(
        tenant_id=tenant_id,
        payload=payload,
        actor_id=current_user.id,
        actor_name=actor_name,
    )


@router.get("/qms/system-documents", response_model=QmsSystemDocumentListResponse, summary="List system documents")
async def list_system_documents(
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    status_in: Optional[str] = Query(None, description="逗号分隔状态，与 status 二选一"),
    doc_type: Optional[str] = Query(None),
    standard_id: Optional[int] = Query(None),
    standard_id_null: bool = Query(False, description="仅未关联标准的文件"),
    zone: Optional[str] = Query(
        "formal",
        description="目录分区：formal 正式目录 / pending 待审区 / all 全部（受权限约束）",
    ),
    review_due: bool = Query(False, description="仅待复审：生效且下次复审时间已到"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_DOC_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentListResponse:
    permission_codes = sorted(
        await UserPermissionService.get_user_permissions(
            user_id=current_user.id,
            tenant_id=tenant_id,
        )
    )
    parsed_status_in = None
    if status_in:
        parsed_status_in = [s.strip() for s in status_in.split(",") if s.strip()]
    return await doc_service.list_documents(
        tenant_id=tenant_id,
        keyword=keyword,
        status=status,
        status_in=parsed_status_in,
        doc_type=doc_type,
        standard_id=standard_id,
        standard_id_null=standard_id_null,
        zone=zone,
        review_due=review_due,
        current_user_id=current_user.id,
        permission_codes=permission_codes,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/qms/system-documents/review-due-summary",
    response_model=QmsSystemDocumentReviewDueSummary,
    summary="Count system documents due for review",
)
async def get_system_document_review_due_summary(
    _auth=_DOC_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentReviewDueSummary:
    return await doc_service.count_review_due_documents(tenant_id=tenant_id)


@router.get(
    "/qms/system-documents/{document_id}",
    response_model=QmsSystemDocumentResponse,
    summary="Get system document",
)
async def get_system_document(
    document_id: int,
    _auth=_DOC_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentResponse:
    return await doc_service.get_document(tenant_id=tenant_id, document_id=document_id)


@router.get(
    "/qms/system-documents/{document_id}/versions",
    response_model=QmsSystemDocumentVersionListResponse,
    summary="List system document versions (INF-05 filtered)",
)
async def list_system_document_versions(
    document_id: int,
    _auth=_DOC_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentVersionListResponse:
    permission_codes = sorted(
        await UserPermissionService.get_user_permissions(
            user_id=current_user.id,
            tenant_id=tenant_id,
        )
    )
    return await doc_service.list_versions(
        tenant_id=tenant_id,
        document_id=document_id,
        current_user_id=current_user.id,
        permission_codes=permission_codes,
    )


@router.get(
    "/qms/system-documents/{document_id}/circulations",
    response_model=QmsSystemDocumentCirculationListResponse,
    summary="List system document issue, recall and briefing records",
)
async def list_system_document_circulations(
    document_id: int,
    _auth=_DOC_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentCirculationListResponse:
    return await doc_service.list_circulations(tenant_id=tenant_id, document_id=document_id)


@router.post(
    "/qms/system-documents/{document_id}/circulations",
    response_model=QmsSystemDocumentCirculationResponse,
    summary="Create system document issue, recall or briefing record",
)
async def create_system_document_circulation(
    document_id: int,
    payload: QmsSystemDocumentCirculationCreate,
    _auth=_DOC_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentCirculationResponse:
    return await doc_service.create_circulation(
        tenant_id=tenant_id,
        document_id=document_id,
        payload=payload,
        actor=current_user,
    )


@router.delete(
    "/qms/system-documents/{document_id}/circulations/{circulation_id}",
    summary="Delete system document circulation record",
)
async def delete_system_document_circulation(
    document_id: int,
    circulation_id: int,
    _auth=_DOC_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> dict:
    await doc_service.delete_circulation(
        tenant_id=tenant_id,
        document_id=document_id,
        circulation_id=circulation_id,
        actor=current_user,
    )
    return {"success": True}


@router.post(
    "/qms/system-documents/{document_id}/revise",
    response_model=QmsSystemDocumentResponse,
    summary="Revise system document (version up to draft)",
)
async def revise_system_document(
    document_id: int,
    payload: QmsSystemDocumentReviseRequest,
    _auth=_DOC_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentResponse:
    actor_name = (
        getattr(current_user, "full_name", None)
        or getattr(current_user, "username", None)
        or str(current_user.id)
    )
    return await doc_service.revise_document(
        tenant_id=tenant_id,
        document_id=document_id,
        payload=payload,
        actor_id=current_user.id,
        actor_name=actor_name,
    )


@router.post(
    "/qms/system-documents/{document_id}/reject",
    response_model=QmsSystemDocumentResponse,
    summary="Reject pending/draft system document revision",
)
async def reject_system_document(
    document_id: int,
    payload: QmsSystemDocumentRejectRequest,
    _auth=_DOC_REJECT,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentResponse:
    actor_name = (
        getattr(current_user, "full_name", None)
        or getattr(current_user, "username", None)
        or str(current_user.id)
    )
    return await doc_service.reject_document(
        tenant_id=tenant_id,
        document_id=document_id,
        payload=payload,
        actor_id=current_user.id,
        actor_name=actor_name,
    )


@router.put(
    "/qms/system-documents/{document_id}",
    response_model=QmsSystemDocumentResponse,
    summary="Update system document",
)
async def update_system_document(
    document_id: int,
    payload: QmsSystemDocumentUpdate,
    _auth=_DOC_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentResponse:
    return await doc_service.update_document(tenant_id=tenant_id, document_id=document_id, payload=payload)


@router.post(
    "/qms/system-documents/{document_id}/submit",
    response_model=QmsSystemDocumentResponse,
    summary="Submit system document for approval",
)
async def submit_system_document(
    document_id: int,
    _auth=_DOC_SUBMIT,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentResponse:
    actor_name = (
        getattr(current_user, "full_name", None)
        or getattr(current_user, "username", None)
        or str(current_user.id)
    )
    return await doc_service.submit_document(
        tenant_id=tenant_id,
        document_id=document_id,
        actor_id=current_user.id,
        actor_name=actor_name,
    )


@router.post(
    "/qms/system-documents/{document_id}/publish",
    response_model=QmsSystemDocumentResponse,
    summary="Publish system document",
)
async def publish_system_document(
    document_id: int,
    _auth=_DOC_PUBLISH,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentResponse:
    return await doc_service.publish_document(tenant_id=tenant_id, document_id=document_id)


@router.post(
    "/qms/system-documents/{document_id}/obsolete",
    response_model=QmsSystemDocumentResponse,
    summary="Obsolete system document",
)
async def obsolete_system_document(
    document_id: int,
    _auth=_DOC_OBSOLETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsSystemDocumentResponse:
    return await doc_service.obsolete_document(tenant_id=tenant_id, document_id=document_id)


@router.delete("/qms/system-documents/{document_id}", summary="Delete system document")
async def delete_system_document(
    document_id: int,
    _auth=_DOC_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await doc_service.delete_document(tenant_id=tenant_id, document_id=document_id)
    return {"success": True}


@router.get(
    "/qms/internal-audit-annual-plans",
    response_model=QmsInternalAuditAnnualPlanListResponse,
    summary="List internal audit annual plans",
)
async def list_internal_audit_annual_plans(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_AUDIT_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditAnnualPlanListResponse:
    return await annual_plan_service.list_plans(tenant_id=tenant_id, skip=skip, limit=limit)


@router.post(
    "/qms/internal-audit-annual-plans",
    response_model=QmsInternalAuditAnnualPlanResponse,
    summary="Create internal audit annual plan",
)
async def create_internal_audit_annual_plan(
    payload: QmsInternalAuditAnnualPlanCreate,
    _auth=_AUDIT_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditAnnualPlanResponse:
    return await annual_plan_service.create_plan(
        tenant_id=tenant_id, payload=payload, actor=current_user
    )


@router.put(
    "/qms/internal-audit-annual-plans/{plan_id}",
    response_model=QmsInternalAuditAnnualPlanResponse,
    summary="Update internal audit annual plan",
)
async def update_internal_audit_annual_plan(
    plan_id: int,
    payload: QmsInternalAuditAnnualPlanUpdate,
    _auth=_AUDIT_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditAnnualPlanResponse:
    return await annual_plan_service.update_plan(
        tenant_id=tenant_id, plan_id=plan_id, payload=payload, actor=current_user
    )


@router.delete("/qms/internal-audit-annual-plans/{plan_id}", summary="Delete internal audit annual plan")
async def delete_internal_audit_annual_plan(
    plan_id: int,
    _auth=_AUDIT_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await annual_plan_service.delete_plan(
        tenant_id=tenant_id, plan_id=plan_id, actor=current_user
    )
    return {"success": True}


@router.post("/qms/internal-audits", response_model=QmsInternalAuditResponse, summary="Create internal audit")
async def create_internal_audit(
    payload: QmsInternalAuditCreate,
    _auth=_AUDIT_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditResponse:
    return await audit_service.create_audit(tenant_id=tenant_id, payload=payload)


@router.get("/qms/internal-audits", response_model=QmsInternalAuditListResponse, summary="List internal audits")
async def list_internal_audits(
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    standard_id: Optional[int] = Query(None),
    annual_plan_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_AUDIT_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditListResponse:
    return await audit_service.list_audits(
        tenant_id=tenant_id,
        keyword=keyword,
        status=status,
        standard_id=standard_id,
        annual_plan_id=annual_plan_id,
        skip=skip,
        limit=limit,
    )


@router.get("/qms/internal-audits/{audit_id}", response_model=QmsInternalAuditResponse, summary="Get internal audit")
async def get_internal_audit(
    audit_id: int,
    _auth=_AUDIT_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditResponse:
    return await audit_service.get_audit(tenant_id=tenant_id, audit_id=audit_id)


@router.put(
    "/qms/internal-audits/{audit_id}",
    response_model=QmsInternalAuditResponse,
    summary="Update internal audit",
)
async def update_internal_audit(
    audit_id: int,
    payload: QmsInternalAuditUpdate,
    _auth=_AUDIT_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditResponse:
    return await audit_service.update_audit(tenant_id=tenant_id, audit_id=audit_id, payload=payload)


@router.delete("/qms/internal-audits/{audit_id}", summary="Delete internal audit")
async def delete_internal_audit(
    audit_id: int,
    _auth=_AUDIT_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await audit_service.delete_audit(tenant_id=tenant_id, audit_id=audit_id)
    return {"success": True}


@router.get(
    "/qms/internal-audits/{audit_id}/checklist-items",
    response_model=QmsInternalAuditChecklistItemListResponse,
    summary="List internal audit checklist items",
)
async def list_internal_audit_checklist_items(
    audit_id: int,
    _auth=_AUDIT_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditChecklistItemListResponse:
    return await checklist_service.list_items(tenant_id=tenant_id, audit_id=audit_id)


@router.post(
    "/qms/internal-audits/{audit_id}/checklist-items",
    response_model=QmsInternalAuditChecklistItemResponse,
    summary="Create internal audit checklist item",
)
async def create_internal_audit_checklist_item(
    audit_id: int,
    payload: QmsInternalAuditChecklistItemCreate,
    _auth=_AUDIT_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditChecklistItemResponse:
    return await checklist_service.create_item(
        tenant_id=tenant_id, audit_id=audit_id, payload=payload, actor=current_user
    )


@router.put(
    "/qms/internal-audits/{audit_id}/checklist-items/{item_id}",
    response_model=QmsInternalAuditChecklistItemResponse,
    summary="Update internal audit checklist item",
)
async def update_internal_audit_checklist_item(
    audit_id: int,
    item_id: int,
    payload: QmsInternalAuditChecklistItemUpdate,
    _auth=_AUDIT_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsInternalAuditChecklistItemResponse:
    return await checklist_service.update_item(
        tenant_id=tenant_id,
        audit_id=audit_id,
        item_id=item_id,
        payload=payload,
        actor=current_user,
    )


@router.delete(
    "/qms/internal-audits/{audit_id}/checklist-items/{item_id}",
    summary="Delete internal audit checklist item",
)
async def delete_internal_audit_checklist_item(
    audit_id: int,
    item_id: int,
    _auth=_AUDIT_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await checklist_service.delete_item(
        tenant_id=tenant_id, audit_id=audit_id, item_id=item_id, actor=current_user
    )
    return {"success": True}


@router.get(
    "/qms/nonconformity-reports",
    response_model=QmsNonconformityReportListResponse,
    summary="List nonconformity reports",
)
async def list_nonconformity_reports(
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    source_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_NC_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsNonconformityReportListResponse:
    return await nonconformity_service.list_reports(
        tenant_id=tenant_id,
        keyword=keyword,
        status=status,
        source_type=source_type,
        source_id=source_id,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/qms/nonconformity-reports",
    response_model=QmsNonconformityReportResponse,
    summary="Create nonconformity report",
)
async def create_nonconformity_report(
    payload: QmsNonconformityReportCreate,
    _auth=_NC_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsNonconformityReportResponse:
    return await nonconformity_service.create_report(
        tenant_id=tenant_id, payload=payload, actor=current_user
    )


@router.get(
    "/qms/nonconformity-reports/{report_id}",
    response_model=QmsNonconformityReportResponse,
    summary="Get nonconformity report",
)
async def get_nonconformity_report(
    report_id: int,
    _auth=_NC_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsNonconformityReportResponse:
    return await nonconformity_service.get_report(tenant_id=tenant_id, report_id=report_id)


@router.put(
    "/qms/nonconformity-reports/{report_id}",
    response_model=QmsNonconformityReportResponse,
    summary="Update nonconformity report",
)
async def update_nonconformity_report(
    report_id: int,
    payload: QmsNonconformityReportUpdate,
    _auth=_NC_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsNonconformityReportResponse:
    return await nonconformity_service.update_report(
        tenant_id=tenant_id, report_id=report_id, payload=payload, actor=current_user
    )


@router.post(
    "/qms/nonconformity-reports/{report_id}/close",
    response_model=QmsNonconformityReportResponse,
    summary="Close nonconformity report",
)
async def close_nonconformity_report(
    report_id: int,
    payload: QmsNonconformityReportUpdate,
    _auth=_NC_CLOSE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsNonconformityReportResponse:
    data = payload.model_dump(exclude_unset=True)
    data["status"] = "closed"
    return await nonconformity_service.update_report(
        tenant_id=tenant_id,
        report_id=report_id,
        payload=QmsNonconformityReportUpdate(**data),
        actor=current_user,
    )


@router.delete("/qms/nonconformity-reports/{report_id}", summary="Delete nonconformity report")
async def delete_nonconformity_report(
    report_id: int,
    _auth=_NC_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await nonconformity_service.delete_report(
        tenant_id=tenant_id, report_id=report_id, actor=current_user
    )
    return {"success": True}


@router.get(
    "/qms/corrective-actions",
    response_model=QmsCorrectiveActionListResponse,
    summary="List corrective actions",
)
async def list_corrective_actions(
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    source_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_CA_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCorrectiveActionListResponse:
    return await corrective_action_service.list_actions(
        tenant_id=tenant_id,
        keyword=keyword,
        status=status,
        source_type=source_type,
        source_id=source_id,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/qms/corrective-actions",
    response_model=QmsCorrectiveActionResponse,
    summary="Create corrective action",
)
async def create_corrective_action(
    payload: QmsCorrectiveActionCreate,
    _auth=_CA_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCorrectiveActionResponse:
    return await corrective_action_service.create_action(
        tenant_id=tenant_id, payload=payload, actor=current_user
    )


@router.post(
    "/qms/corrective-actions/from-source",
    response_model=QmsCorrectiveActionResponse,
    summary="Create corrective action from source document",
)
async def create_corrective_action_from_source(
    payload: QmsCorrectiveActionFromSource,
    _auth=_CA_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCorrectiveActionResponse:
    return await corrective_action_service.create_from_source(
        tenant_id=tenant_id, payload=payload, actor=current_user
    )


@router.get(
    "/qms/corrective-actions/{action_id}",
    response_model=QmsCorrectiveActionResponse,
    summary="Get corrective action",
)
async def get_corrective_action(
    action_id: int,
    _auth=_CA_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCorrectiveActionResponse:
    return await corrective_action_service.get_action(tenant_id=tenant_id, action_id=action_id)


@router.put(
    "/qms/corrective-actions/{action_id}",
    response_model=QmsCorrectiveActionResponse,
    summary="Update corrective action",
)
async def update_corrective_action(
    action_id: int,
    payload: QmsCorrectiveActionUpdate,
    _auth=_CA_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCorrectiveActionResponse:
    return await corrective_action_service.update_action(
        tenant_id=tenant_id, action_id=action_id, payload=payload, actor=current_user
    )


@router.post(
    "/qms/corrective-actions/{action_id}/close",
    response_model=QmsCorrectiveActionResponse,
    summary="Close corrective action",
)
async def close_corrective_action(
    action_id: int,
    payload: QmsCorrectiveActionUpdate,
    _auth=_CA_CLOSE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCorrectiveActionResponse:
    data = payload.model_dump(exclude_unset=True)
    data["status"] = "closed"
    return await corrective_action_service.update_action(
        tenant_id=tenant_id,
        action_id=action_id,
        payload=QmsCorrectiveActionUpdate(**data),
        actor=current_user,
    )


@router.delete("/qms/corrective-actions/{action_id}", summary="Delete corrective action")
async def delete_corrective_action(
    action_id: int,
    _auth=_CA_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await corrective_action_service.delete_action(
        tenant_id=tenant_id, action_id=action_id, actor=current_user
    )
    return {"success": True}


@router.get(
    "/qms/management-reviews/{review_id}/resolutions",
    response_model=QmsManagementReviewResolutionListResponse,
    summary="List management review resolutions",
)
async def list_management_review_resolutions(
    review_id: int,
    _auth=_REVIEW_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsManagementReviewResolutionListResponse:
    return await resolution_service.list_resolutions(tenant_id=tenant_id, review_id=review_id)


@router.post(
    "/qms/management-reviews/{review_id}/resolutions",
    response_model=QmsManagementReviewResolutionResponse,
    summary="Create management review resolution",
)
async def create_management_review_resolution(
    review_id: int,
    payload: QmsManagementReviewResolutionCreate,
    _auth=_REVIEW_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsManagementReviewResolutionResponse:
    return await resolution_service.create_resolution(
        tenant_id=tenant_id, review_id=review_id, payload=payload, actor=current_user
    )


@router.put(
    "/qms/management-reviews/{review_id}/resolutions/{resolution_id}",
    response_model=QmsManagementReviewResolutionResponse,
    summary="Update management review resolution",
)
async def update_management_review_resolution(
    review_id: int,
    resolution_id: int,
    payload: QmsManagementReviewResolutionUpdate,
    _auth=_REVIEW_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsManagementReviewResolutionResponse:
    return await resolution_service.update_resolution(
        tenant_id=tenant_id,
        review_id=review_id,
        resolution_id=resolution_id,
        payload=payload,
        actor=current_user,
    )


@router.delete(
    "/qms/management-reviews/{review_id}/resolutions/{resolution_id}",
    summary="Delete management review resolution",
)
async def delete_management_review_resolution(
    review_id: int,
    resolution_id: int,
    _auth=_REVIEW_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await resolution_service.delete_resolution(
        tenant_id=tenant_id,
        review_id=review_id,
        resolution_id=resolution_id,
        actor=current_user,
    )
    return {"success": True}


@router.post(
    "/qms/management-reviews",
    response_model=QmsManagementReviewResponse,
    summary="Create management review",
)
async def create_management_review(
    payload: QmsManagementReviewCreate,
    _auth=_REVIEW_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsManagementReviewResponse:
    return await review_service.create_review(tenant_id=tenant_id, payload=payload)


@router.get(
    "/qms/management-reviews",
    response_model=QmsManagementReviewListResponse,
    summary="List management reviews",
)
async def list_management_reviews(
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_REVIEW_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsManagementReviewListResponse:
    return await review_service.list_reviews(
        tenant_id=tenant_id, keyword=keyword, status=status, skip=skip, limit=limit
    )


@router.get(
    "/qms/management-reviews/input-summary",
    response_model=QmsManagementReviewInputSummary,
    summary="Aggregate management review input metrics",
)
async def get_management_review_input_summary(
    period_start: Optional[datetime] = Query(None, description="统计起始（站点墙钟）"),
    period_end: Optional[datetime] = Query(None, description="统计截止（站点墙钟）"),
    current_review_id: Optional[int] = Query(None, description="当前评审ID（排除自身）"),
    _auth=_REVIEW_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsManagementReviewInputSummary:
    return await review_service.get_input_summary(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
        current_review_id=current_review_id,
    )


@router.get(
    "/qms/management-reviews/{review_id}",
    response_model=QmsManagementReviewResponse,
    summary="Get management review",
)
async def get_management_review(
    review_id: int,
    _auth=_REVIEW_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsManagementReviewResponse:
    return await review_service.get_review(tenant_id=tenant_id, review_id=review_id)


@router.put(
    "/qms/management-reviews/{review_id}",
    response_model=QmsManagementReviewResponse,
    summary="Update management review",
)
async def update_management_review(
    review_id: int,
    payload: QmsManagementReviewUpdate,
    _auth=_REVIEW_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsManagementReviewResponse:
    return await review_service.update_review(tenant_id=tenant_id, review_id=review_id, payload=payload)


@router.delete("/qms/management-reviews/{review_id}", summary="Delete management review")
async def delete_management_review(
    review_id: int,
    _auth=_REVIEW_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await review_service.delete_review(tenant_id=tenant_id, review_id=review_id)
    return {"success": True}


@router.get("/qms/standards", response_model=QmsStandardListResponse, summary="List QMS standards")
async def list_qms_standards(
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _auth=_CLAUSE_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsStandardListResponse:
    return await qms_standard_service.list_standards(
        tenant_id=tenant_id, is_active=is_active, skip=skip, limit=limit
    )


@router.post("/qms/standards", response_model=QmsStandardResponse, summary="Create QMS standard")
async def create_qms_standard(
    payload: QmsStandardCreate,
    _auth=_CLAUSE_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsStandardResponse:
    return await qms_standard_service.create_standard(
        tenant_id=tenant_id, payload=payload, user=current_user
    )


@router.put("/qms/standards/{standard_id}", response_model=QmsStandardResponse, summary="Update QMS standard")
async def update_qms_standard(
    standard_id: int,
    payload: QmsStandardUpdate,
    _auth=_CLAUSE_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsStandardResponse:
    return await qms_standard_service.update_standard(
        tenant_id=tenant_id, standard_id=standard_id, payload=payload, user=current_user
    )


@router.delete("/qms/standards/{standard_id}", summary="Delete QMS standard")
async def delete_qms_standard(
    standard_id: int,
    _auth=_CLAUSE_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await qms_standard_service.delete_standard(tenant_id=tenant_id, standard_id=standard_id)
    return {"success": True}


@router.post("/qms/iso-clauses", response_model=QmsIsoClauseResponse, summary="Create ISO clause")
async def create_iso_clause(
    payload: QmsIsoClauseCreate,
    _auth=_CLAUSE_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsIsoClauseResponse:
    return await iso_clause_service.create_clause(tenant_id=tenant_id, payload=payload, user=current_user)


@router.get("/qms/iso-clauses", response_model=QmsIsoClauseListResponse, summary="List ISO clauses")
async def list_iso_clauses(
    standard_id: Optional[int] = Query(None),
    standard_code: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    _auth=_CLAUSE_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsIsoClauseListResponse:
    return await iso_clause_service.list_clauses(
        tenant_id=tenant_id,
        standard_id=standard_id,
        standard_code=standard_code,
        keyword=keyword,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.get("/qms/iso-clauses/tree", response_model=list[QmsIsoClauseTreeNode], summary="ISO clause tree")
async def list_iso_clause_tree(
    standard_id: Optional[int] = Query(None),
    standard_code: Optional[str] = Query(None),
    _auth=_CLAUSE_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> list[QmsIsoClauseTreeNode]:
    return await iso_clause_service.list_tree(
        tenant_id=tenant_id, standard_id=standard_id, standard_code=standard_code
    )


@router.post(
    "/qms/iso-clauses/load-preset",
    response_model=QmsIsoClauseLoadPresetResult,
    summary="Load ISO 9001:2015 preset clauses",
)
async def load_iso_clause_preset(
    standard_code: str = Query("ISO9001:2015"),
    _auth=_CLAUSE_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsIsoClauseLoadPresetResult:
    return await iso_clause_service.load_preset(
        tenant_id=tenant_id, standard_code=standard_code, user=current_user
    )


@router.get("/qms/iso-clauses/{clause_id}", response_model=QmsIsoClauseResponse, summary="Get ISO clause")
async def get_iso_clause(
    clause_id: int,
    _auth=_CLAUSE_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsIsoClauseResponse:
    return await iso_clause_service.get_clause(tenant_id=tenant_id, clause_id=clause_id)


@router.put("/qms/iso-clauses/{clause_id}", response_model=QmsIsoClauseResponse, summary="Update ISO clause")
async def update_iso_clause(
    clause_id: int,
    payload: QmsIsoClauseUpdate,
    _auth=_CLAUSE_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsIsoClauseResponse:
    return await iso_clause_service.update_clause(
        tenant_id=tenant_id, clause_id=clause_id, payload=payload, user=current_user
    )


@router.delete("/qms/iso-clauses/{clause_id}", summary="Delete ISO clause")
async def delete_iso_clause(
    clause_id: int,
    _auth=_CLAUSE_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await iso_clause_service.delete_clause(tenant_id=tenant_id, clause_id=clause_id)
    return {"success": True}


@router.get(
    "/qms/iso-clauses/{clause_id}/compliance-summary",
    response_model=QmsIsoClauseComplianceSummary,
    summary="ISO clause compliance summary",
)
async def get_iso_clause_compliance_summary(
    clause_id: int,
    _auth=_CLAUSE_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsIsoClauseComplianceSummary:
    return await iso_clause_service.get_compliance_summary(tenant_id=tenant_id, clause_id=clause_id)


@router.get(
    "/qms/iso-clauses/{clause_id}/related-documents",
    response_model=QmsIsoClauseRelatedDocumentsResponse,
    summary="Related system documents for ISO clause",
)
async def list_iso_clause_related_documents(
    clause_id: int,
    limit: int = Query(50, ge=1, le=200),
    _auth=_CLAUSE_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsIsoClauseRelatedDocumentsResponse:
    items = await iso_clause_service.list_related_documents(
        tenant_id=tenant_id, clause_id=clause_id, limit=limit
    )
    return QmsIsoClauseRelatedDocumentsResponse(items=items)


@router.get(
    "/qms/iso-clauses/{clause_id}/related-audits",
    response_model=QmsIsoClauseRelatedAuditsResponse,
    summary="Related internal audits for ISO clause",
)
async def list_iso_clause_related_audits(
    clause_id: int,
    limit: int = Query(50, ge=1, le=200),
    _auth=_CLAUSE_READ,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsIsoClauseRelatedAuditsResponse:
    items = await iso_clause_service.list_related_audits(
        tenant_id=tenant_id, clause_id=clause_id, limit=limit
    )
    return QmsIsoClauseRelatedAuditsResponse(items=items)


@router.get(
    "/qms/quality-objectives",
    response_model=QmsQualityObjectiveListResponse,
    summary="List quality objectives",
)
async def list_quality_objectives(
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    plan_year: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_OBJ_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsQualityObjectiveListResponse:
    return await quality_objective_service.list_objectives(
        tenant_id=tenant_id,
        keyword=keyword,
        status=status,
        plan_year=plan_year,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/qms/quality-objectives",
    response_model=QmsQualityObjectiveResponse,
    summary="Create quality objective",
)
async def create_quality_objective(
    payload: QmsQualityObjectiveCreate,
    _auth=_OBJ_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsQualityObjectiveResponse:
    return await quality_objective_service.create_objective(
        tenant_id=tenant_id, payload=payload, actor=current_user
    )


@router.get(
    "/qms/quality-objectives/{objective_id}",
    response_model=QmsQualityObjectiveResponse,
    summary="Get quality objective",
)
async def get_quality_objective(
    objective_id: int,
    _auth=_OBJ_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsQualityObjectiveResponse:
    return await quality_objective_service.get_objective(
        tenant_id=tenant_id, objective_id=objective_id
    )


@router.put(
    "/qms/quality-objectives/{objective_id}",
    response_model=QmsQualityObjectiveResponse,
    summary="Update quality objective",
)
async def update_quality_objective(
    objective_id: int,
    payload: QmsQualityObjectiveUpdate,
    _auth=_OBJ_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsQualityObjectiveResponse:
    return await quality_objective_service.update_objective(
        tenant_id=tenant_id, objective_id=objective_id, payload=payload, actor=current_user
    )


@router.delete("/qms/quality-objectives/{objective_id}", summary="Delete quality objective")
async def delete_quality_objective(
    objective_id: int,
    _auth=_OBJ_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await quality_objective_service.delete_objective(
        tenant_id=tenant_id, objective_id=objective_id, actor=current_user
    )
    return {"success": True}


@router.get(
    "/qms/legal-regulations",
    response_model=QmsLegalRegulationListResponse,
    summary="List legal regulations",
)
async def list_legal_regulations(
    keyword: Optional[str] = Query(None),
    due_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_LEGAL_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsLegalRegulationListResponse:
    return await legal_regulation_service.list_regulations(
        tenant_id=tenant_id,
        keyword=keyword,
        due_only=due_only,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/qms/legal-regulations",
    response_model=QmsLegalRegulationResponse,
    summary="Create legal regulation",
)
async def create_legal_regulation(
    payload: QmsLegalRegulationCreate,
    _auth=_LEGAL_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsLegalRegulationResponse:
    return await legal_regulation_service.create_regulation(
        tenant_id=tenant_id, payload=payload, actor=current_user
    )


@router.get(
    "/qms/legal-regulations/{regulation_id}",
    response_model=QmsLegalRegulationResponse,
    summary="Get legal regulation",
)
async def get_legal_regulation(
    regulation_id: int,
    _auth=_LEGAL_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsLegalRegulationResponse:
    return await legal_regulation_service.get_regulation(
        tenant_id=tenant_id, regulation_id=regulation_id
    )


@router.put(
    "/qms/legal-regulations/{regulation_id}",
    response_model=QmsLegalRegulationResponse,
    summary="Update legal regulation",
)
async def update_legal_regulation(
    regulation_id: int,
    payload: QmsLegalRegulationUpdate,
    _auth=_LEGAL_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsLegalRegulationResponse:
    return await legal_regulation_service.update_regulation(
        tenant_id=tenant_id, regulation_id=regulation_id, payload=payload, actor=current_user
    )


@router.delete("/qms/legal-regulations/{regulation_id}", summary="Delete legal regulation")
async def delete_legal_regulation(
    regulation_id: int,
    _auth=_LEGAL_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await legal_regulation_service.delete_regulation(
        tenant_id=tenant_id, regulation_id=regulation_id, actor=current_user
    )
    return {"success": True}


@router.get(
    "/qms/external-audits",
    response_model=QmsExternalAuditListResponse,
    summary="List external audits",
)
async def list_external_audits(
    keyword: Optional[str] = Query(None),
    audit_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_EXT_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsExternalAuditListResponse:
    return await external_audit_service.list_audits(
        tenant_id=tenant_id,
        keyword=keyword,
        audit_type=audit_type,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/qms/external-audits",
    response_model=QmsExternalAuditResponse,
    summary="Create external audit",
)
async def create_external_audit(
    payload: QmsExternalAuditCreate,
    _auth=_EXT_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsExternalAuditResponse:
    return await external_audit_service.create_audit(
        tenant_id=tenant_id, payload=payload, actor=current_user
    )


@router.get(
    "/qms/external-audits/{audit_id}",
    response_model=QmsExternalAuditResponse,
    summary="Get external audit",
)
async def get_external_audit(
    audit_id: int,
    _auth=_EXT_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsExternalAuditResponse:
    return await external_audit_service.get_audit(tenant_id=tenant_id, audit_id=audit_id)


@router.put(
    "/qms/external-audits/{audit_id}",
    response_model=QmsExternalAuditResponse,
    summary="Update external audit",
)
async def update_external_audit(
    audit_id: int,
    payload: QmsExternalAuditUpdate,
    _auth=_EXT_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsExternalAuditResponse:
    return await external_audit_service.update_audit(
        tenant_id=tenant_id, audit_id=audit_id, payload=payload, actor=current_user
    )


@router.delete("/qms/external-audits/{audit_id}", summary="Delete external audit")
async def delete_external_audit(
    audit_id: int,
    _auth=_EXT_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await external_audit_service.delete_audit(
        tenant_id=tenant_id, audit_id=audit_id, actor=current_user
    )
    return {"success": True}


@router.get(
    "/qms/certificates",
    response_model=QmsCertificateListResponse,
    summary="List certificates",
)
async def list_certificates(
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _auth=_EXT_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCertificateListResponse:
    return await certificate_service.list_certificates(
        tenant_id=tenant_id,
        keyword=keyword,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/qms/certificates",
    response_model=QmsCertificateResponse,
    summary="Create certificate",
)
async def create_certificate(
    payload: QmsCertificateCreate,
    _auth=_EXT_CREATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCertificateResponse:
    return await certificate_service.create_certificate(
        tenant_id=tenant_id, payload=payload, actor=current_user
    )


@router.get(
    "/qms/certificates/{certificate_id}",
    response_model=QmsCertificateResponse,
    summary="Get certificate",
)
async def get_certificate(
    certificate_id: int,
    _auth=_EXT_READ,
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCertificateResponse:
    return await certificate_service.get_certificate(
        tenant_id=tenant_id, certificate_id=certificate_id
    )


@router.put(
    "/qms/certificates/{certificate_id}",
    response_model=QmsCertificateResponse,
    summary="Update certificate",
)
async def update_certificate(
    certificate_id: int,
    payload: QmsCertificateUpdate,
    _auth=_EXT_UPDATE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
) -> QmsCertificateResponse:
    return await certificate_service.update_certificate(
        tenant_id=tenant_id, certificate_id=certificate_id, payload=payload, actor=current_user
    )


@router.delete("/qms/certificates/{certificate_id}", summary="Delete certificate")
async def delete_certificate(
    certificate_id: int,
    _auth=_EXT_DELETE,
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant),
):
    await certificate_service.delete_certificate(
        tenant_id=tenant_id, certificate_id=certificate_id, actor=current_user
    )
    return {"success": True}
