import { apiRequest } from '../../../services/api';

export type QmsEvidenceLink = {
  ref_type: string;
  ref_id?: number | null;
  ref_code?: string | null;
  ref_name?: string | null;
  path?: string | null;
  note?: string | null;
};

export interface QmsSystemDocument {
  id: number;
  uuid?: string;
  document_code: string;
  title: string;
  doc_type: string;
  version: string;
  status: string;
  standard_id?: number | null;
  clause_ids?: number[];
  clause_labels?: string[];
  primary_clause_id?: number | null;
  content?: string;
  file_url?: string;
  effective_at?: string;
  obsolete_at?: string;
  next_review_at?: string;
  owner_name?: string;
  evidence_links?: QmsEvidenceLink[];
  training_refs?: QmsEvidenceLink[];
  attachments?: any;
  remarks?: string;
  created_at?: string;
  updated_at?: string;
  outstanding_copies?: number;
  review_due?: boolean;
}

export type QmsSystemDocumentCirculationType = 'issue' | 'recall' | 'briefing';

export interface QmsSystemDocumentCirculation {
  id: number;
  document_id: number;
  record_type: QmsSystemDocumentCirculationType;
  document_version: string;
  copies?: number | null;
  party_name: string;
  event_on: string;
  signer_name?: string | null;
  signed_on?: string | null;
  destroyed?: boolean;
  completed?: boolean;
  training_ref?: string | null;
  remarks?: string | null;
  created_by_name?: string | null;
  created_at?: string;
}

export interface QmsSystemDocumentCirculationList {
  items: QmsSystemDocumentCirculation[];
  total: number;
  outstanding_copies: number;
}

export interface QmsInternalAudit {
  id: number;
  uuid?: string;
  audit_code: string;
  title: string;
  audit_scope?: string;
  standard_id?: number | null;
  annual_plan_id?: number | null;
  annual_plan_year?: number | null;
  open_nc_count?: number;
  clause_ids?: number[];
  clause_labels?: string[];
  primary_clause_id?: number | null;
  status: string;
  planned_date?: string;
  completed_date?: string;
  lead_auditor?: string;
  audit_team?: string;
  checklist?: string;
  findings?: string;
  conclusion?: string;
  finding_links?: QmsEvidenceLink[];
  training_refs?: QmsEvidenceLink[];
  calibration_refs?: QmsEvidenceLink[];
  attachments?: any;
  remarks?: string;
  created_at?: string;
  updated_at?: string;
}

export interface QmsInternalAuditAnnualPlan {
  id: number;
  uuid?: string;
  plan_year: number;
  covered_processes?: string | null;
  planned_months?: number[] | null;
  lead_auditor?: string | null;
  remarks?: string | null;
  created_by_name?: string | null;
  updated_by_name?: string | null;
  created_at?: string;
  updated_at?: string;
}

export type QmsChecklistConclusion = 'pending' | 'conform' | 'nonconform' | 'observation';

export interface QmsInternalAuditChecklistItem {
  id: number;
  audit_id: number;
  clause_id: number;
  clause_label?: string | null;
  sort_order: number;
  checkpoint?: string | null;
  conclusion: QmsChecklistConclusion | string;
  evidence?: string | null;
  nc_report_id?: number | null;
  nc_report_code?: string | null;
  nc_report_status?: string | null;
  remarks?: string | null;
}

export type QmsNcSeverity = 'severe' | 'general' | 'observation';
export type QmsNcStatus = 'open' | 'rectifying' | 'pending_verify' | 'closed';
export type QmsNcSourceType = 'internal_audit' | 'external_audit';

export interface QmsNonconformityReport {
  id: number;
  uuid?: string;
  report_code: string;
  source_type: QmsNcSourceType | string;
  source_id?: number | null;
  source_code?: string | null;
  checklist_item_id?: number | null;
  clause_id?: number | null;
  clause_label?: string | null;
  fact: string;
  severity: QmsNcSeverity | string;
  responsible_dept?: string | null;
  due_on?: string | null;
  cause?: string | null;
  correction?: string | null;
  corrective_action?: string | null;
  verifier_name?: string | null;
  verified_on?: string | null;
  verification_conclusion?: string | null;
  capa_code?: string | null;
  status: QmsNcStatus | string;
  remarks?: string | null;
  attachments?: any;
  created_by_name?: string | null;
  updated_by_name?: string | null;
  created_at?: string;
  updated_at?: string;
}

export type QmsCorrectiveActionSourceType =
  | 'nonconformity_report'
  | 'quality_complaint'
  | 'management_review_resolution';
export type QmsCorrectiveActionStatus =
  | 'registered'
  | 'in_progress'
  | 'pending_verify'
  | 'closed';

export interface QmsCorrectiveAction {
  id: number;
  uuid?: string;
  action_code: string;
  source_type: QmsCorrectiveActionSourceType | string;
  source_id?: number | null;
  source_code?: string | null;
  problem_summary: string;
  cause?: string | null;
  correction?: string | null;
  prevention?: string | null;
  responsible_person?: string | null;
  due_on?: string | null;
  verifier_name?: string | null;
  verified_on?: string | null;
  verification_conclusion?: string | null;
  need_eight_d?: boolean;
  eight_d_code?: string | null;
  status: QmsCorrectiveActionStatus | string;
  remarks?: string | null;
  attachments?: any;
  created_by_name?: string | null;
  updated_by_name?: string | null;
  created_at?: string;
  updated_at?: string;
}

export type QmsObjectiveStatus = 'draft' | 'published' | 'ended';
export type QmsObjectivePeriod = 'month' | 'quarter';

export interface QmsQualityObjectiveLine {
  id?: number;
  objective_id?: number;
  sort_order?: number;
  name: string;
  metric_scope?: string | null;
  target_value: string;
  responsible_dept?: string | null;
  period?: QmsObjectivePeriod | string;
  actual_value?: string | null;
  achieved?: boolean | null;
  remarks?: string | null;
}

export interface QmsQualityObjective {
  id: number;
  uuid?: string;
  objective_code: string;
  plan_year: number;
  standard_id?: number | null;
  standard_label?: string | null;
  status: QmsObjectiveStatus | string;
  remarks?: string | null;
  lines?: QmsQualityObjectiveLine[];
  created_by_name?: string | null;
  updated_by_name?: string | null;
  created_at?: string;
  updated_at?: string;
}

export type QmsLegalConclusion = 'conform' | 'need_rectify';

export interface QmsLegalRegulation {
  id: number;
  uuid?: string;
  name: string;
  doc_no: string;
  issuing_authority?: string | null;
  effective_on?: string | null;
  applicable_scope?: string | null;
  evaluation_conclusion?: QmsLegalConclusion | string | null;
  evaluated_on?: string | null;
  next_evaluation_on?: string | null;
  capa_code?: string | null;
  evaluation_completed?: boolean;
  due_for_evaluation?: boolean;
  remarks?: string | null;
  created_by_name?: string | null;
  updated_by_name?: string | null;
  created_at?: string;
  updated_at?: string;
}

export type QmsExternalAuditType = 'initial' | 'surveillance' | 'recertification';

export interface QmsExternalAudit {
  id: number;
  uuid?: string;
  audit_code: string;
  body_name: string;
  audit_type: QmsExternalAuditType | string;
  planned_on?: string | null;
  actual_on?: string | null;
  audit_scope?: string | null;
  open_nc_count?: number;
  remarks?: string | null;
  created_by_name?: string | null;
  updated_by_name?: string | null;
  created_at?: string;
  updated_at?: string;
}

export type QmsCertificateStatus = 'valid' | 'expiring' | 'expired';

export interface QmsCertificate {
  id: number;
  uuid?: string;
  name: string;
  standard_name?: string | null;
  certificate_no: string;
  issuer?: string | null;
  effective_on?: string | null;
  expire_on: string;
  status: QmsCertificateStatus | string;
  remarks?: string | null;
  created_by_name?: string | null;
  updated_by_name?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface QmsManagementReviewResolution {
  id: number;
  review_id: number;
  content: string;
  responsible_person?: string | null;
  due_on?: string | null;
  convert_to_capa?: boolean;
  capa_code?: string | null;
  status: string;
  sort_order?: number;
  remarks?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface QmsStandard {
  id: number;
  uuid?: string;
  code: string;
  name: string;
  family: string;
  is_preset?: boolean;
  is_active?: boolean;
  sort_order?: number;
}

export interface QmsManagementReview {
  id: number;
  uuid?: string;
  review_code: string;
  title: string;
  standard_ids?: number[];
  standard_labels?: string[];
  status: string;
  review_date?: string;
  chairperson?: string;
  attendees?: string;
  inputs_summary?: string;
  outputs_summary?: string;
  input_links?: QmsEvidenceLink[];
  training_refs?: QmsEvidenceLink[];
  calibration_refs?: QmsEvidenceLink[];
  attachments?: any;
  remarks?: string;
  created_at?: string;
  updated_at?: string;
}

export interface QmsIsoClause {
  id: number;
  uuid?: string;
  standard_id?: number;
  standard_code: string;
  clause_code: string;
  title: string;
  description?: string;
  parent_id?: number | null;
  sort_order?: number;
  is_active?: boolean;
  created_by_name?: string;
  updated_by_name?: string;
  created_at?: string;
  updated_at?: string;
}

export interface QmsIsoClauseTreeNode extends QmsIsoClause {
  children?: QmsIsoClauseTreeNode[];
}

export interface QmsIsoClauseComplianceSummary {
  effective_document_count: number;
  review_due_count: number;
  internal_audit_count: number;
  last_audit_date?: string | null;
  has_gap: boolean;
  no_effective_document: boolean;
  no_completed_audit: boolean;
  compliance_status: 'covered' | 'review_due' | 'gap';
}

export interface QmsSystemDocumentVersion {
  id: number;
  document_id: number;
  document_code: string;
  version: string;
  status: string;
  is_effective?: boolean;
  title: string;
  content?: string | null;
  file_url?: string | null;
  change_summary?: string | null;
  effective_at?: string | null;
  obsolete_at?: string | null;
  created_by?: number | null;
  created_by_name?: string | null;
  created_at?: string | null;
}

export interface QmsSystemDocumentVersionList {
  items: QmsSystemDocumentVersion[];
  total: number;
  audience: string;
  can_view_history: boolean;
}

type ListEnvelope<T> = { items: T[]; total: number };

export const qualityQmsApi = {
  systemDocuments: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsSystemDocument>>('/apps/kuaizhizao/qms/system-documents', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsSystemDocument>(`/apps/kuaizhizao/qms/system-documents/${id}`, { method: 'GET' }),
    versions: (id: number) =>
      apiRequest<QmsSystemDocumentVersionList>(`/apps/kuaizhizao/qms/system-documents/${id}/versions`, {
        method: 'GET',
      }),
    create: (data: Partial<QmsSystemDocument>) =>
      apiRequest<QmsSystemDocument>('/apps/kuaizhizao/qms/system-documents', { method: 'POST', data }),
    update: (id: number, data: Partial<QmsSystemDocument>) =>
      apiRequest<QmsSystemDocument>(`/apps/kuaizhizao/qms/system-documents/${id}`, {
        method: 'PUT',
        data,
      }),
    revise: (id: number, data?: { version?: string; change_summary?: string }) =>
      apiRequest<QmsSystemDocument>(`/apps/kuaizhizao/qms/system-documents/${id}/revise`, {
        method: 'POST',
        data: data ?? {},
      }),
    submit: (id: number) =>
      apiRequest<QmsSystemDocument>(`/apps/kuaizhizao/qms/system-documents/${id}/submit`, {
        method: 'POST',
      }),
    reject: (id: number, data?: { reason?: string }) =>
      apiRequest<QmsSystemDocument>(`/apps/kuaizhizao/qms/system-documents/${id}/reject`, {
        method: 'POST',
        data: data ?? {},
      }),
    publish: (id: number) =>
      apiRequest<QmsSystemDocument>(`/apps/kuaizhizao/qms/system-documents/${id}/publish`, {
        method: 'POST',
      }),
    obsolete: (id: number) =>
      apiRequest<QmsSystemDocument>(`/apps/kuaizhizao/qms/system-documents/${id}/obsolete`, {
        method: 'POST',
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/system-documents/${id}`, { method: 'DELETE' }),
    reviewDueSummary: () =>
      apiRequest<{ due_count: number }>('/apps/kuaizhizao/qms/system-documents/review-due-summary', {
        method: 'GET',
      }),
    circulations: (id: number) =>
      apiRequest<QmsSystemDocumentCirculationList>(
        `/apps/kuaizhizao/qms/system-documents/${id}/circulations`,
        { method: 'GET' },
      ),
    createCirculation: (
      id: number,
      data: {
        record_type: QmsSystemDocumentCirculationType;
        party_name: string;
        copies?: number;
        event_on: string;
        signer_name?: string;
        signed_on?: string;
        destroyed?: boolean;
        completed?: boolean;
        training_ref?: string;
      },
    ) =>
      apiRequest<QmsSystemDocumentCirculation>(
        `/apps/kuaizhizao/qms/system-documents/${id}/circulations`,
        { method: 'POST', data },
      ),
    deleteCirculation: (id: number, circulationId: number) =>
      apiRequest(`/apps/kuaizhizao/qms/system-documents/${id}/circulations/${circulationId}`, {
        method: 'DELETE',
      }),
  },
  annualPlans: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsInternalAuditAnnualPlan>>(
        '/apps/kuaizhizao/qms/internal-audit-annual-plans',
        { method: 'GET', params },
      ),
    create: (data: Partial<QmsInternalAuditAnnualPlan>) =>
      apiRequest<QmsInternalAuditAnnualPlan>('/apps/kuaizhizao/qms/internal-audit-annual-plans', {
        method: 'POST',
        data,
      }),
    update: (id: number, data: Partial<QmsInternalAuditAnnualPlan>) =>
      apiRequest<QmsInternalAuditAnnualPlan>(
        `/apps/kuaizhizao/qms/internal-audit-annual-plans/${id}`,
        { method: 'PUT', data },
      ),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/internal-audit-annual-plans/${id}`, { method: 'DELETE' }),
  },
  internalAudits: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsInternalAudit>>('/apps/kuaizhizao/qms/internal-audits', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsInternalAudit>(`/apps/kuaizhizao/qms/internal-audits/${id}`, { method: 'GET' }),
    create: (data: Partial<QmsInternalAudit>) =>
      apiRequest<QmsInternalAudit>('/apps/kuaizhizao/qms/internal-audits', { method: 'POST', data }),
    update: (id: number, data: Partial<QmsInternalAudit>) =>
      apiRequest<QmsInternalAudit>(`/apps/kuaizhizao/qms/internal-audits/${id}`, {
        method: 'PUT',
        data,
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/internal-audits/${id}`, { method: 'DELETE' }),
    checklistItems: (id: number) =>
      apiRequest<ListEnvelope<QmsInternalAuditChecklistItem>>(
        `/apps/kuaizhizao/qms/internal-audits/${id}/checklist-items`,
        { method: 'GET' },
      ),
    createChecklistItem: (
      id: number,
      data: Partial<QmsInternalAuditChecklistItem> & { nc_severity?: string },
    ) =>
      apiRequest<QmsInternalAuditChecklistItem>(
        `/apps/kuaizhizao/qms/internal-audits/${id}/checklist-items`,
        { method: 'POST', data },
      ),
    updateChecklistItem: (
      id: number,
      itemId: number,
      data: Partial<QmsInternalAuditChecklistItem> & { nc_severity?: string },
    ) =>
      apiRequest<QmsInternalAuditChecklistItem>(
        `/apps/kuaizhizao/qms/internal-audits/${id}/checklist-items/${itemId}`,
        { method: 'PUT', data },
      ),
    deleteChecklistItem: (id: number, itemId: number) =>
      apiRequest(`/apps/kuaizhizao/qms/internal-audits/${id}/checklist-items/${itemId}`, {
        method: 'DELETE',
      }),
  },
  nonconformityReports: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsNonconformityReport>>('/apps/kuaizhizao/qms/nonconformity-reports', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsNonconformityReport>(`/apps/kuaizhizao/qms/nonconformity-reports/${id}`, {
        method: 'GET',
      }),
    create: (data: Partial<QmsNonconformityReport>) =>
      apiRequest<QmsNonconformityReport>('/apps/kuaizhizao/qms/nonconformity-reports', {
        method: 'POST',
        data,
      }),
    update: (id: number, data: Partial<QmsNonconformityReport>) =>
      apiRequest<QmsNonconformityReport>(`/apps/kuaizhizao/qms/nonconformity-reports/${id}`, {
        method: 'PUT',
        data,
      }),
    close: (id: number, data?: Partial<QmsNonconformityReport>) =>
      apiRequest<QmsNonconformityReport>(`/apps/kuaizhizao/qms/nonconformity-reports/${id}/close`, {
        method: 'POST',
        data: data ?? {},
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/nonconformity-reports/${id}`, { method: 'DELETE' }),
  },
  correctiveActions: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsCorrectiveAction>>('/apps/kuaizhizao/qms/corrective-actions', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsCorrectiveAction>(`/apps/kuaizhizao/qms/corrective-actions/${id}`, {
        method: 'GET',
      }),
    create: (data: Partial<QmsCorrectiveAction>) =>
      apiRequest<QmsCorrectiveAction>('/apps/kuaizhizao/qms/corrective-actions', {
        method: 'POST',
        data,
      }),
    fromSource: (data: {
      source_type: string;
      source_id?: number;
      review_id?: number;
      problem_summary?: string;
      cause?: string;
      correction?: string;
      prevention?: string;
      responsible_person?: string;
      due_on?: string;
      need_eight_d?: boolean;
      eight_d_code?: string;
      remarks?: string;
    }) =>
      apiRequest<QmsCorrectiveAction>('/apps/kuaizhizao/qms/corrective-actions/from-source', {
        method: 'POST',
        data,
      }),
    update: (id: number, data: Partial<QmsCorrectiveAction>) =>
      apiRequest<QmsCorrectiveAction>(`/apps/kuaizhizao/qms/corrective-actions/${id}`, {
        method: 'PUT',
        data,
      }),
    close: (id: number, data?: Partial<QmsCorrectiveAction>) =>
      apiRequest<QmsCorrectiveAction>(`/apps/kuaizhizao/qms/corrective-actions/${id}/close`, {
        method: 'POST',
        data: data ?? {},
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/corrective-actions/${id}`, { method: 'DELETE' }),
  },
  managementReviews: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsManagementReview>>('/apps/kuaizhizao/qms/management-reviews', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsManagementReview>(`/apps/kuaizhizao/qms/management-reviews/${id}`, {
        method: 'GET',
      }),
    create: (data: Partial<QmsManagementReview>) =>
      apiRequest<QmsManagementReview>('/apps/kuaizhizao/qms/management-reviews', {
        method: 'POST',
        data,
      }),
    update: (id: number, data: Partial<QmsManagementReview>) =>
      apiRequest<QmsManagementReview>(`/apps/kuaizhizao/qms/management-reviews/${id}`, {
        method: 'PUT',
        data,
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/management-reviews/${id}`, { method: 'DELETE' }),
    resolutions: (id: number) =>
      apiRequest<ListEnvelope<QmsManagementReviewResolution>>(
        `/apps/kuaizhizao/qms/management-reviews/${id}/resolutions`,
        { method: 'GET' },
      ),
    createResolution: (id: number, data: Partial<QmsManagementReviewResolution>) =>
      apiRequest<QmsManagementReviewResolution>(
        `/apps/kuaizhizao/qms/management-reviews/${id}/resolutions`,
        { method: 'POST', data },
      ),
    updateResolution: (
      id: number,
      resolutionId: number,
      data: Partial<QmsManagementReviewResolution>,
    ) =>
      apiRequest<QmsManagementReviewResolution>(
        `/apps/kuaizhizao/qms/management-reviews/${id}/resolutions/${resolutionId}`,
        { method: 'PUT', data },
      ),
    deleteResolution: (id: number, resolutionId: number) =>
      apiRequest(`/apps/kuaizhizao/qms/management-reviews/${id}/resolutions/${resolutionId}`, {
        method: 'DELETE',
      }),
    inputSummary: (params?: {
      period_start?: string;
      period_end?: string;
      current_review_id?: number;
    }) =>
      apiRequest<{
        summary_text: string;
        nonconforming_count: number;
        open_8d_count: number;
        iqc_pass_rate?: number | null;
        oqc_pass_rate?: number | null;
        documents?: Array<{
          ref_type: string;
          ref_id: number;
          ref_code?: string | null;
          ref_name?: string | null;
          status?: string | null;
          note?: string | null;
        }>;
        open_resolutions_from_last?: Array<{
          ref_type: string;
          ref_id: number;
          ref_code?: string | null;
          ref_name?: string | null;
          status?: string | null;
          note?: string | null;
        }>;
        quality_objectives_unmet?: Array<{
          ref_type: string;
          ref_id: number;
          ref_code?: string | null;
          ref_name?: string | null;
          status?: string | null;
          note?: string | null;
        }>;
      }>('/apps/kuaizhizao/qms/management-reviews/input-summary', { method: 'GET', params }),
  },
  qualityObjectives: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsQualityObjective>>('/apps/kuaizhizao/qms/quality-objectives', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsQualityObjective>(`/apps/kuaizhizao/qms/quality-objectives/${id}`, {
        method: 'GET',
      }),
    create: (data: Partial<QmsQualityObjective> & { lines?: QmsQualityObjectiveLine[] }) =>
      apiRequest<QmsQualityObjective>('/apps/kuaizhizao/qms/quality-objectives', {
        method: 'POST',
        data,
      }),
    update: (id: number, data: Partial<QmsQualityObjective> & { lines?: QmsQualityObjectiveLine[] }) =>
      apiRequest<QmsQualityObjective>(`/apps/kuaizhizao/qms/quality-objectives/${id}`, {
        method: 'PUT',
        data,
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/quality-objectives/${id}`, { method: 'DELETE' }),
  },
  legalRegulations: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsLegalRegulation>>('/apps/kuaizhizao/qms/legal-regulations', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsLegalRegulation>(`/apps/kuaizhizao/qms/legal-regulations/${id}`, {
        method: 'GET',
      }),
    create: (data: Partial<QmsLegalRegulation>) =>
      apiRequest<QmsLegalRegulation>('/apps/kuaizhizao/qms/legal-regulations', {
        method: 'POST',
        data,
      }),
    update: (id: number, data: Partial<QmsLegalRegulation>) =>
      apiRequest<QmsLegalRegulation>(`/apps/kuaizhizao/qms/legal-regulations/${id}`, {
        method: 'PUT',
        data,
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/legal-regulations/${id}`, { method: 'DELETE' }),
  },
  externalAudits: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsExternalAudit>>('/apps/kuaizhizao/qms/external-audits', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsExternalAudit>(`/apps/kuaizhizao/qms/external-audits/${id}`, {
        method: 'GET',
      }),
    create: (data: Partial<QmsExternalAudit>) =>
      apiRequest<QmsExternalAudit>('/apps/kuaizhizao/qms/external-audits', {
        method: 'POST',
        data,
      }),
    update: (id: number, data: Partial<QmsExternalAudit>) =>
      apiRequest<QmsExternalAudit>(`/apps/kuaizhizao/qms/external-audits/${id}`, {
        method: 'PUT',
        data,
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/external-audits/${id}`, { method: 'DELETE' }),
  },
  certificates: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsCertificate>>('/apps/kuaizhizao/qms/certificates', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsCertificate>(`/apps/kuaizhizao/qms/certificates/${id}`, { method: 'GET' }),
    create: (data: Partial<QmsCertificate>) =>
      apiRequest<QmsCertificate>('/apps/kuaizhizao/qms/certificates', {
        method: 'POST',
        data,
      }),
    update: (id: number, data: Partial<QmsCertificate>) =>
      apiRequest<QmsCertificate>(`/apps/kuaizhizao/qms/certificates/${id}`, {
        method: 'PUT',
        data,
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/certificates/${id}`, { method: 'DELETE' }),
  },
  standards: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsStandard>>('/apps/kuaizhizao/qms/standards', {
        method: 'GET',
        params,
      }),
    create: (data: Partial<QmsStandard>) =>
      apiRequest<QmsStandard>('/apps/kuaizhizao/qms/standards', { method: 'POST', data }),
    update: (id: number, data: Partial<QmsStandard>) =>
      apiRequest<QmsStandard>(`/apps/kuaizhizao/qms/standards/${id}`, {
        method: 'PUT',
        data,
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/standards/${id}`, { method: 'DELETE' }),
  },
  isoClauses: {
    list: (params?: Record<string, unknown>) =>
      apiRequest<ListEnvelope<QmsIsoClause>>('/apps/kuaizhizao/qms/iso-clauses', {
        method: 'GET',
        params,
      }),
    tree: (params?: { standard_id?: number; standard_code?: string }) =>
      apiRequest<QmsIsoClauseTreeNode[]>('/apps/kuaizhizao/qms/iso-clauses/tree', {
        method: 'GET',
        params,
      }),
    get: (id: number) =>
      apiRequest<QmsIsoClause>(`/apps/kuaizhizao/qms/iso-clauses/${id}`, { method: 'GET' }),
    create: (data: Partial<QmsIsoClause>) =>
      apiRequest<QmsIsoClause>('/apps/kuaizhizao/qms/iso-clauses', { method: 'POST', data }),
    update: (id: number, data: Partial<QmsIsoClause>) =>
      apiRequest<QmsIsoClause>(`/apps/kuaizhizao/qms/iso-clauses/${id}`, {
        method: 'PUT',
        data,
      }),
    delete: (id: number) =>
      apiRequest(`/apps/kuaizhizao/qms/iso-clauses/${id}`, { method: 'DELETE' }),
    loadPreset: (standard_code = 'ISO9001:2015') =>
      apiRequest<{ created: number; skipped: number; linked: number }>(
        '/apps/kuaizhizao/qms/iso-clauses/load-preset',
        { method: 'POST', params: { standard_code } },
      ),
    complianceSummary: (id: number) =>
      apiRequest<QmsIsoClauseComplianceSummary>(
        `/apps/kuaizhizao/qms/iso-clauses/${id}/compliance-summary`,
        { method: 'GET' },
      ),
    relatedDocuments: (id: number) =>
      apiRequest<{ items: QmsSystemDocument[] }>(
        `/apps/kuaizhizao/qms/iso-clauses/${id}/related-documents`,
        { method: 'GET' },
      ),
    relatedAudits: (id: number) =>
      apiRequest<{ items: QmsInternalAudit[] }>(
        `/apps/kuaizhizao/qms/iso-clauses/${id}/related-audits`,
        { method: 'GET' },
      ),
  },
};
