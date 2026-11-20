"""质量体系 schemas：体系文件 / 内审 / 管理评审"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import Field

from core.schemas.base import BaseSchema


class QmsEvidenceLink(BaseSchema):
    ref_type: str = Field(..., description="证据类型")
    ref_id: Optional[int] = None
    ref_code: Optional[str] = None
    ref_name: Optional[str] = None
    path: Optional[str] = None
    note: Optional[str] = None


class QmsClauseLinkFields(BaseSchema):
    standard_id: Optional[int] = Field(None, description="所属标准ID")
    clause_ids: Optional[List[int]] = Field(None, description="关联条款ID列表")
    clause_labels: Optional[List[str]] = Field(None, description="关联条款展示（只读）")
    primary_clause_id: Optional[int] = Field(None, description="主条款ID（只读）")


class QmsSystemDocumentBase(BaseSchema):
    document_code: Optional[str] = Field(None, description="文件编码")
    title: str = Field(..., description="标题")
    doc_type: str = Field("procedure", description="文件类型")
    version: str = Field("A0", description="版本")
    status: str = Field("draft", description="状态")
    standard_id: Optional[int] = None
    clause_ids: Optional[List[int]] = None
    content: Optional[str] = None
    file_url: Optional[str] = None
    effective_at: Optional[datetime] = None
    obsolete_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None
    owner_name: Optional[str] = None
    evidence_links: Optional[List[Any]] = None
    training_refs: Optional[List[Any]] = None
    attachments: Optional[Any] = None
    remarks: Optional[str] = None


class QmsSystemDocumentCreate(QmsSystemDocumentBase):
    pass


class QmsSystemDocumentUpdate(BaseSchema):
    title: Optional[str] = None
    doc_type: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None
    standard_id: Optional[int] = None
    clause_ids: Optional[List[int]] = None
    content: Optional[str] = None
    file_url: Optional[str] = None
    effective_at: Optional[datetime] = None
    obsolete_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None
    owner_name: Optional[str] = None
    evidence_links: Optional[List[Any]] = None
    training_refs: Optional[List[Any]] = None
    attachments: Optional[Any] = None
    remarks: Optional[str] = None
    document_code: Optional[str] = None


class QmsSystemDocumentResponse(QmsSystemDocumentBase):
    id: int
    uuid: str
    tenant_id: int
    clause_labels: Optional[List[str]] = None
    primary_clause_id: Optional[int] = None
    outstanding_copies: int = 0
    review_due: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsSystemDocumentListResponse(BaseSchema):
    items: List[QmsSystemDocumentResponse]
    total: int


class QmsSystemDocumentVersionResponse(BaseSchema):
    id: int
    document_id: int
    document_code: str
    version: str
    status: str
    is_effective: bool = False
    title: str
    content: Optional[str] = None
    file_uuid: Optional[str] = None
    file_url: Optional[str] = None
    change_summary: Optional[str] = None
    effective_at: Optional[datetime] = None
    obsolete_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QmsSystemDocumentVersionListResponse(BaseSchema):
    items: List[QmsSystemDocumentVersionResponse]
    total: int
    audience: str
    can_view_history: bool = False


class QmsSystemDocumentReviseRequest(BaseSchema):
    version: Optional[str] = Field(None, description="新版本号；空则自动递增")
    change_summary: Optional[str] = Field(None, description="升版说明")


class QmsSystemDocumentRejectRequest(BaseSchema):
    reason: Optional[str] = Field(None, description="驳回原因")


class QmsInternalAuditBase(BaseSchema):
    audit_code: Optional[str] = None
    title: str
    audit_scope: Optional[str] = None
    standard_id: Optional[int] = None
    annual_plan_id: Optional[int] = None
    clause_ids: Optional[List[int]] = None
    status: str = Field("planned")
    planned_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    lead_auditor: Optional[str] = None
    audit_team: Optional[str] = None
    checklist: Optional[str] = None
    findings: Optional[str] = None
    conclusion: Optional[str] = None
    finding_links: Optional[List[Any]] = None
    training_refs: Optional[List[Any]] = None
    calibration_refs: Optional[List[Any]] = None
    attachments: Optional[Any] = None
    remarks: Optional[str] = None


class QmsInternalAuditCreate(QmsInternalAuditBase):
    annual_plan_id: int


class QmsInternalAuditUpdate(BaseSchema):
    title: Optional[str] = None
    audit_scope: Optional[str] = None
    standard_id: Optional[int] = None
    annual_plan_id: Optional[int] = None
    clause_ids: Optional[List[int]] = None
    status: Optional[str] = None
    planned_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    lead_auditor: Optional[str] = None
    audit_team: Optional[str] = None
    conclusion: Optional[str] = None
    finding_links: Optional[List[Any]] = None
    training_refs: Optional[List[Any]] = None
    calibration_refs: Optional[List[Any]] = None
    attachments: Optional[Any] = None
    remarks: Optional[str] = None
    audit_code: Optional[str] = None


class QmsInternalAuditResponse(QmsInternalAuditBase):
    id: int
    uuid: str
    tenant_id: int
    clause_labels: Optional[List[str]] = None
    primary_clause_id: Optional[int] = None
    annual_plan_year: Optional[int] = None
    open_nc_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsInternalAuditListResponse(BaseSchema):
    items: List[QmsInternalAuditResponse]
    total: int


class QmsInternalAuditAnnualPlanBase(BaseSchema):
    plan_year: int
    covered_processes: Optional[str] = None
    planned_months: Optional[List[int]] = None
    lead_auditor: Optional[str] = None
    remarks: Optional[str] = None


class QmsInternalAuditAnnualPlanCreate(QmsInternalAuditAnnualPlanBase):
    pass


class QmsInternalAuditAnnualPlanUpdate(BaseSchema):
    covered_processes: Optional[str] = None
    planned_months: Optional[List[int]] = None
    lead_auditor: Optional[str] = None
    remarks: Optional[str] = None


class QmsInternalAuditAnnualPlanResponse(QmsInternalAuditAnnualPlanBase):
    id: int
    uuid: str
    tenant_id: int
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsInternalAuditAnnualPlanListResponse(BaseSchema):
    items: List[QmsInternalAuditAnnualPlanResponse]
    total: int


class QmsInternalAuditChecklistItemBase(BaseSchema):
    clause_id: int
    sort_order: int = 0
    checkpoint: Optional[str] = None
    conclusion: str = "pending"
    evidence: Optional[str] = None
    remarks: Optional[str] = None
    nc_severity: Optional[str] = Field(
        None, description="结论为不符合时生成报告的类型 severe/general"
    )


class QmsInternalAuditChecklistItemCreate(QmsInternalAuditChecklistItemBase):
    pass


class QmsInternalAuditChecklistItemUpdate(BaseSchema):
    clause_id: Optional[int] = None
    sort_order: Optional[int] = None
    checkpoint: Optional[str] = None
    conclusion: Optional[str] = None
    evidence: Optional[str] = None
    remarks: Optional[str] = None
    nc_severity: Optional[str] = None


class QmsInternalAuditChecklistItemResponse(BaseSchema):
    id: int
    audit_id: int
    clause_id: int
    clause_label: Optional[str] = None
    sort_order: int = 0
    checkpoint: Optional[str] = None
    conclusion: str
    evidence: Optional[str] = None
    nc_report_id: Optional[int] = None
    nc_report_code: Optional[str] = None
    nc_report_status: Optional[str] = None
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsInternalAuditChecklistItemListResponse(BaseSchema):
    items: List[QmsInternalAuditChecklistItemResponse]
    total: int


class QmsNonconformityReportBase(BaseSchema):
    report_code: Optional[str] = None
    source_type: str
    source_id: Optional[int] = None
    source_code: Optional[str] = None
    checklist_item_id: Optional[int] = None
    clause_id: Optional[int] = None
    fact: str
    severity: str
    responsible_dept: Optional[str] = None
    due_on: Optional[date] = None
    cause: Optional[str] = None
    correction: Optional[str] = None
    corrective_action: Optional[str] = None
    verifier_name: Optional[str] = None
    verified_on: Optional[date] = None
    verification_conclusion: Optional[str] = None
    capa_code: Optional[str] = None
    status: str = "open"
    remarks: Optional[str] = None
    attachments: Optional[Any] = None


class QmsNonconformityReportCreate(QmsNonconformityReportBase):
    pass


class QmsNonconformityReportUpdate(BaseSchema):
    fact: Optional[str] = None
    severity: Optional[str] = None
    responsible_dept: Optional[str] = None
    due_on: Optional[date] = None
    cause: Optional[str] = None
    correction: Optional[str] = None
    corrective_action: Optional[str] = None
    verifier_name: Optional[str] = None
    verified_on: Optional[date] = None
    verification_conclusion: Optional[str] = None
    status: Optional[str] = None
    remarks: Optional[str] = None
    attachments: Optional[Any] = None
    clause_id: Optional[int] = None


class QmsNonconformityReportResponse(QmsNonconformityReportBase):
    id: int
    uuid: str
    tenant_id: int
    clause_label: Optional[str] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsNonconformityReportListResponse(BaseSchema):
    items: List[QmsNonconformityReportResponse]
    total: int


class QmsCorrectiveActionBase(BaseSchema):
    action_code: Optional[str] = None
    source_type: str
    source_id: Optional[int] = None
    source_code: Optional[str] = None
    problem_summary: str
    cause: Optional[str] = None
    correction: Optional[str] = None
    prevention: Optional[str] = None
    responsible_person: Optional[str] = None
    due_on: Optional[date] = None
    verifier_name: Optional[str] = None
    verified_on: Optional[date] = None
    verification_conclusion: Optional[str] = None
    need_eight_d: bool = False
    eight_d_code: Optional[str] = None
    status: str = "registered"
    remarks: Optional[str] = None
    attachments: Optional[Any] = None


class QmsCorrectiveActionCreate(QmsCorrectiveActionBase):
    pass


class QmsCorrectiveActionFromSource(BaseSchema):
    source_type: str
    source_id: Optional[int] = None
    review_id: Optional[int] = None
    problem_summary: Optional[str] = None
    cause: Optional[str] = None
    correction: Optional[str] = None
    prevention: Optional[str] = None
    responsible_person: Optional[str] = None
    due_on: Optional[date] = None
    need_eight_d: bool = False
    eight_d_code: Optional[str] = None
    remarks: Optional[str] = None


class QmsCorrectiveActionUpdate(BaseSchema):
    problem_summary: Optional[str] = None
    cause: Optional[str] = None
    correction: Optional[str] = None
    prevention: Optional[str] = None
    responsible_person: Optional[str] = None
    due_on: Optional[date] = None
    verifier_name: Optional[str] = None
    verified_on: Optional[date] = None
    verification_conclusion: Optional[str] = None
    need_eight_d: Optional[bool] = None
    eight_d_code: Optional[str] = None
    status: Optional[str] = None
    remarks: Optional[str] = None
    attachments: Optional[Any] = None


class QmsCorrectiveActionResponse(QmsCorrectiveActionBase):
    id: int
    uuid: str
    tenant_id: int
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsCorrectiveActionListResponse(BaseSchema):
    items: List[QmsCorrectiveActionResponse]
    total: int


class QmsManagementReviewResolutionCreate(BaseSchema):
    content: str
    responsible_person: Optional[str] = None
    due_on: Optional[date] = None
    convert_to_capa: bool = False
    sort_order: Optional[int] = None
    remarks: Optional[str] = None


class QmsManagementReviewResolutionUpdate(BaseSchema):
    content: Optional[str] = None
    responsible_person: Optional[str] = None
    due_on: Optional[date] = None
    convert_to_capa: Optional[bool] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None
    remarks: Optional[str] = None


class QmsManagementReviewResolutionResponse(BaseSchema):
    id: int
    review_id: int
    content: str
    responsible_person: Optional[str] = None
    due_on: Optional[date] = None
    convert_to_capa: bool = False
    capa_code: Optional[str] = None
    status: str
    sort_order: int = 0
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsManagementReviewResolutionListResponse(BaseSchema):
    items: List[QmsManagementReviewResolutionResponse]
    total: int


class QmsManagementReviewBase(BaseSchema):
    review_code: Optional[str] = None
    title: str
    standard_ids: Optional[List[int]] = Field(None, description="评审覆盖的标准")
    status: str = Field("draft")
    review_date: Optional[datetime] = None
    chairperson: Optional[str] = None
    attendees: Optional[str] = None
    inputs_summary: Optional[str] = None
    outputs_summary: Optional[str] = None
    input_links: Optional[List[Any]] = None
    training_refs: Optional[List[Any]] = None
    calibration_refs: Optional[List[Any]] = None
    attachments: Optional[Any] = None
    remarks: Optional[str] = None


class QmsManagementReviewCreate(QmsManagementReviewBase):
    pass


class QmsManagementReviewUpdate(BaseSchema):
    title: Optional[str] = None
    standard_ids: Optional[List[int]] = None
    status: Optional[str] = None
    review_date: Optional[datetime] = None
    chairperson: Optional[str] = None
    attendees: Optional[str] = None
    inputs_summary: Optional[str] = None
    outputs_summary: Optional[str] = None
    input_links: Optional[List[Any]] = None
    training_refs: Optional[List[Any]] = None
    calibration_refs: Optional[List[Any]] = None
    attachments: Optional[Any] = None
    remarks: Optional[str] = None
    review_code: Optional[str] = None


class QmsManagementReviewResponse(QmsManagementReviewBase):
    id: int
    uuid: str
    tenant_id: int
    standard_labels: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsManagementReviewListResponse(BaseSchema):
    items: List[QmsManagementReviewResponse]
    total: int


class QmsSystemDocumentCirculationCreate(BaseSchema):
    record_type: str
    copies: Optional[int] = None
    party_name: str
    event_on: date
    signer_name: Optional[str] = None
    signed_on: Optional[date] = None
    destroyed: bool = False
    completed: bool = False
    training_ref: Optional[str] = None
    remarks: Optional[str] = None


class QmsSystemDocumentCirculationResponse(BaseSchema):
    id: int
    document_id: int
    record_type: str
    document_version: str
    copies: Optional[int] = None
    party_name: str
    event_on: date
    signer_name: Optional[str] = None
    signed_on: Optional[date] = None
    destroyed: bool = False
    completed: bool = False
    training_ref: Optional[str] = None
    remarks: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class QmsSystemDocumentCirculationListResponse(BaseSchema):
    items: List[QmsSystemDocumentCirculationResponse]
    total: int
    outstanding_copies: int


class QmsSystemDocumentReviewDueSummary(BaseSchema):
    due_count: int = Field(..., description="待复审文件数（生效中且 next_review_at 已到期或为空不计）")


class QmsManagementReviewInputDocItem(BaseSchema):
    ref_type: str
    ref_id: int
    ref_code: Optional[str] = None
    ref_name: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None


class QmsManagementReviewInputSummary(BaseSchema):
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    nonconforming_count: int = 0
    open_8d_count: int = 0
    iqc_total: int = 0
    iqc_pass_count: int = 0
    iqc_pass_rate: Optional[float] = None
    oqc_total: int = 0
    oqc_pass_count: int = 0
    oqc_pass_rate: Optional[float] = None
    summary_text: str = ""
    documents: List[QmsManagementReviewInputDocItem] = Field(default_factory=list)
    open_resolutions_from_last: List[QmsManagementReviewInputDocItem] = Field(
        default_factory=list
    )
    quality_objectives_unmet: List[QmsManagementReviewInputDocItem] = Field(
        default_factory=list,
        description="第 5 期质量目标未落地前恒为空",
    )


class QmsStandardBase(BaseSchema):
    code: str = Field(..., max_length=30, description="标准代号")
    name: str = Field(..., max_length=200, description="显示名称")
    family: str = Field("custom", description="标准族")
    is_preset: bool = False
    is_active: bool = True
    sort_order: int = 0


class QmsStandardCreate(BaseSchema):
    code: str = Field(..., max_length=30)
    name: str = Field(..., max_length=200)
    family: str = Field("custom")
    is_active: bool = True
    sort_order: int = 0


class QmsStandardUpdate(BaseSchema):
    code: Optional[str] = None
    name: Optional[str] = None
    family: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class QmsStandardResponse(QmsStandardBase):
    id: int
    uuid: str
    tenant_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsStandardListResponse(BaseSchema):
    items: List[QmsStandardResponse]
    total: int


class QmsIsoClauseBase(BaseSchema):
    standard_id: Optional[int] = Field(None, description="标准ID")
    standard_code: Optional[str] = Field(None, description="标准编码")
    clause_code: str = Field(..., description="条款号")
    title: str = Field(..., description="条款标题")
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = Field(0, description="排序")
    is_active: bool = Field(True, description="是否启用")


class QmsIsoClauseCreate(QmsIsoClauseBase):
    pass


class QmsIsoClauseUpdate(BaseSchema):
    standard_id: Optional[int] = None
    standard_code: Optional[str] = None
    clause_code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class QmsIsoClauseResponse(QmsIsoClauseBase):
    id: int
    uuid: str
    tenant_id: int
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsIsoClauseListResponse(BaseSchema):
    items: List[QmsIsoClauseResponse]
    total: int


class QmsIsoClauseTreeNode(QmsIsoClauseResponse):
    children: List["QmsIsoClauseTreeNode"] = Field(default_factory=list)


class QmsIsoClauseComplianceSummary(BaseSchema):
    effective_document_count: int = 0
    review_due_count: int = 0
    internal_audit_count: int = 0
    last_audit_date: Optional[datetime] = None
    has_gap: bool = False
    no_effective_document: bool = False
    no_completed_audit: bool = False
    compliance_status: str = Field("gap", description="covered|review_due|gap")


class QmsIsoClauseLoadPresetResult(BaseSchema):
    created: int = 0
    skipped: int = 0
    linked: int = 0


class QmsIsoClauseRelatedDocumentsResponse(BaseSchema):
    items: List[QmsSystemDocumentResponse]


class QmsIsoClauseRelatedAuditsResponse(BaseSchema):
    items: List[QmsInternalAuditResponse]


class QmsQualityObjectiveLinePayload(BaseSchema):
    id: Optional[int] = None
    sort_order: int = 0
    name: str
    metric_scope: Optional[str] = None
    target_value: str
    responsible_dept: Optional[str] = None
    period: str = "month"
    actual_value: Optional[str] = None
    remarks: Optional[str] = None


class QmsQualityObjectiveLineResponse(QmsQualityObjectiveLinePayload):
    id: int
    objective_id: int
    achieved: Optional[bool] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsQualityObjectiveCreate(BaseSchema):
    objective_code: Optional[str] = None
    plan_year: int
    standard_id: Optional[int] = None
    status: str = "draft"
    remarks: Optional[str] = None
    lines: List[QmsQualityObjectiveLinePayload] = Field(default_factory=list)


class QmsQualityObjectiveUpdate(BaseSchema):
    plan_year: Optional[int] = None
    standard_id: Optional[int] = None
    status: Optional[str] = None
    remarks: Optional[str] = None
    lines: Optional[List[QmsQualityObjectiveLinePayload]] = None


class QmsQualityObjectiveResponse(BaseSchema):
    id: int
    uuid: str
    tenant_id: int
    objective_code: str
    plan_year: int
    standard_id: Optional[int] = None
    standard_label: Optional[str] = None
    status: str
    remarks: Optional[str] = None
    lines: List[QmsQualityObjectiveLineResponse] = Field(default_factory=list)
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsQualityObjectiveListResponse(BaseSchema):
    items: List[QmsQualityObjectiveResponse]
    total: int


class QmsLegalRegulationCreate(BaseSchema):
    name: str
    doc_no: str
    issuing_authority: Optional[str] = None
    effective_on: Optional[date] = None
    applicable_scope: Optional[str] = None
    evaluation_conclusion: Optional[str] = None
    evaluated_on: Optional[date] = None
    next_evaluation_on: Optional[date] = None
    capa_code: Optional[str] = None
    evaluation_completed: bool = False
    remarks: Optional[str] = None


class QmsLegalRegulationUpdate(BaseSchema):
    name: Optional[str] = None
    doc_no: Optional[str] = None
    issuing_authority: Optional[str] = None
    effective_on: Optional[date] = None
    applicable_scope: Optional[str] = None
    evaluation_conclusion: Optional[str] = None
    evaluated_on: Optional[date] = None
    next_evaluation_on: Optional[date] = None
    capa_code: Optional[str] = None
    evaluation_completed: Optional[bool] = None
    remarks: Optional[str] = None


class QmsLegalRegulationResponse(QmsLegalRegulationCreate):
    id: int
    uuid: str
    tenant_id: int
    due_for_evaluation: bool = False
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsLegalRegulationListResponse(BaseSchema):
    items: List[QmsLegalRegulationResponse]
    total: int


class QmsExternalAuditCreate(BaseSchema):
    audit_code: Optional[str] = None
    body_name: str
    audit_type: str
    planned_on: Optional[date] = None
    actual_on: Optional[date] = None
    audit_scope: Optional[str] = None
    remarks: Optional[str] = None


class QmsExternalAuditUpdate(BaseSchema):
    body_name: Optional[str] = None
    audit_type: Optional[str] = None
    planned_on: Optional[date] = None
    actual_on: Optional[date] = None
    audit_scope: Optional[str] = None
    remarks: Optional[str] = None


class QmsExternalAuditResponse(QmsExternalAuditCreate):
    id: int
    uuid: str
    tenant_id: int
    open_nc_count: int = 0
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsExternalAuditListResponse(BaseSchema):
    items: List[QmsExternalAuditResponse]
    total: int


class QmsCertificateCreate(BaseSchema):
    name: str
    standard_name: Optional[str] = None
    certificate_no: str
    issuer: Optional[str] = None
    effective_on: Optional[date] = None
    expire_on: date
    remarks: Optional[str] = None


class QmsCertificateUpdate(BaseSchema):
    name: Optional[str] = None
    standard_name: Optional[str] = None
    certificate_no: Optional[str] = None
    issuer: Optional[str] = None
    effective_on: Optional[date] = None
    expire_on: Optional[date] = None
    remarks: Optional[str] = None


class QmsCertificateResponse(QmsCertificateCreate):
    id: int
    uuid: str
    tenant_id: int
    status: str
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QmsCertificateListResponse(BaseSchema):
    items: List[QmsCertificateResponse]
    total: int


QmsIsoClauseTreeNode.model_rebuild()
