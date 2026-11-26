import type { QmsEvidenceLink } from '../../../services/quality-qms';

export const EVIDENCE_LINKS_PARSE_INVALID_JSON = 'evidence_links_invalid_json';

function isNoteOnlyLink(link: QmsEvidenceLink): boolean {
  return (
    link.ref_type === 'note' &&
    link.ref_id == null &&
    !link.ref_code &&
    !link.ref_name &&
    !link.path
  );
}

/** 表单文本 → 证据链接：支持纯文本（每行一条说明）或 JSON 数组。 */
export function parseEvidenceLinksText(raw: unknown): QmsEvidenceLink[] {
  if (raw == null || raw === '') return [];
  if (Array.isArray(raw)) return raw as QmsEvidenceLink[];
  const text = String(raw).trim();
  if (!text) return [];

  if (text.startsWith('[')) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error(EVIDENCE_LINKS_PARSE_INVALID_JSON);
    }
    if (!Array.isArray(parsed)) {
      throw new Error('evidence_links_must_be_array');
    }
    return parsed as QmsEvidenceLink[];
  }

  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((note) => ({ ref_type: 'note', note }));
}

export function stringifyEvidenceLinks(links?: QmsEvidenceLink[] | null): string {
  if (!links || !links.length) return '';
  if (links.every(isNoteOnlyLink)) {
    return links.map((l) => l.note ?? '').filter(Boolean).join('\n');
  }
  return JSON.stringify(links, null, 2);
}

export const QMS_DOC_TYPE_OPTIONS = [
  { value: 'manual', labelKey: 'app.kuaizhizao.quality.qms.docType.manual' },
  { value: 'procedure', labelKey: 'app.kuaizhizao.quality.qms.docType.procedure' },
  { value: 'work_instruction', labelKey: 'app.kuaizhizao.quality.qms.docType.workInstruction' },
  { value: 'form', labelKey: 'app.kuaizhizao.quality.qms.docType.form' },
  { value: 'record', labelKey: 'app.kuaizhizao.quality.qms.docType.record' },
] as const;

export const QMS_DOC_STATUS_OPTIONS = [
  { value: 'draft', labelKey: 'app.kuaizhizao.quality.qms.docStatus.draft' },
  { value: 'pending', labelKey: 'app.kuaizhizao.quality.qms.docStatus.pending' },
  { value: 'effective', labelKey: 'app.kuaizhizao.quality.qms.docStatus.effective' },
  { value: 'obsolete', labelKey: 'app.kuaizhizao.quality.qms.docStatus.obsolete' },
  { value: 'rejected', labelKey: 'app.kuaizhizao.quality.qms.docStatus.rejected' },
] as const;

export const QMS_AUDIT_STATUS_OPTIONS = [
  { value: 'planned', labelKey: 'app.kuaizhizao.quality.qms.auditStatus.planned' },
  { value: 'in_progress', labelKey: 'app.kuaizhizao.quality.qms.auditStatus.inProgress' },
  { value: 'completed', labelKey: 'app.kuaizhizao.quality.qms.auditStatus.completed' },
  { value: 'closed', labelKey: 'app.kuaizhizao.quality.qms.auditStatus.closed' },
] as const;

export const QMS_CHECKLIST_CONCLUSION_OPTIONS = [
  { value: 'pending', labelKey: 'app.kuaizhizao.quality.qms.checklistConclusion.pending' },
  { value: 'conform', labelKey: 'app.kuaizhizao.quality.qms.checklistConclusion.conform' },
  { value: 'nonconform', labelKey: 'app.kuaizhizao.quality.qms.checklistConclusion.nonconform' },
  { value: 'observation', labelKey: 'app.kuaizhizao.quality.qms.checklistConclusion.observation' },
] as const;

export const QMS_NC_SEVERITY_OPTIONS = [
  { value: 'severe', labelKey: 'app.kuaizhizao.quality.qms.ncSeverity.severe' },
  { value: 'general', labelKey: 'app.kuaizhizao.quality.qms.ncSeverity.general' },
  { value: 'observation', labelKey: 'app.kuaizhizao.quality.qms.ncSeverity.observation' },
] as const;

export const QMS_NC_STATUS_OPTIONS = [
  { value: 'open', labelKey: 'app.kuaizhizao.quality.qms.ncStatus.open' },
  { value: 'rectifying', labelKey: 'app.kuaizhizao.quality.qms.ncStatus.rectifying' },
  { value: 'pending_verify', labelKey: 'app.kuaizhizao.quality.qms.ncStatus.pendingVerify' },
  { value: 'closed', labelKey: 'app.kuaizhizao.quality.qms.ncStatus.closed' },
] as const;

export const QMS_NC_SOURCE_OPTIONS = [
  { value: 'internal_audit', labelKey: 'app.kuaizhizao.quality.qms.ncSource.internalAudit' },
  { value: 'external_audit', labelKey: 'app.kuaizhizao.quality.qms.ncSource.externalAudit' },
] as const;

export const QMS_CA_SOURCE_OPTIONS = [
  {
    value: 'nonconformity_report',
    labelKey: 'app.kuaizhizao.quality.qms.caSource.nonconformityReport',
  },
  {
    value: 'quality_complaint',
    labelKey: 'app.kuaizhizao.quality.qms.caSource.qualityComplaint',
  },
  {
    value: 'management_review_resolution',
    labelKey: 'app.kuaizhizao.quality.qms.caSource.managementReviewResolution',
  },
] as const;

export const QMS_CA_STATUS_OPTIONS = [
  { value: 'registered', labelKey: 'app.kuaizhizao.quality.qms.caStatus.registered' },
  { value: 'in_progress', labelKey: 'app.kuaizhizao.quality.qms.caStatus.inProgress' },
  { value: 'pending_verify', labelKey: 'app.kuaizhizao.quality.qms.caStatus.pendingVerify' },
  { value: 'closed', labelKey: 'app.kuaizhizao.quality.qms.caStatus.closed' },
] as const;

export const QMS_REVIEW_STATUS_OPTIONS = [
  { value: 'draft', labelKey: 'app.kuaizhizao.quality.qms.reviewStatus.draft' },
  { value: 'in_progress', labelKey: 'app.kuaizhizao.quality.qms.reviewStatus.inProgress' },
  { value: 'completed', labelKey: 'app.kuaizhizao.quality.qms.reviewStatus.completed' },
  { value: 'closed', labelKey: 'app.kuaizhizao.quality.qms.reviewStatus.closed' },
] as const;

export const QMS_OBJECTIVE_STATUS_OPTIONS = [
  { value: 'draft', labelKey: 'app.kuaizhizao.quality.qms.objectiveStatus.draft' },
  { value: 'published', labelKey: 'app.kuaizhizao.quality.qms.objectiveStatus.published' },
  { value: 'ended', labelKey: 'app.kuaizhizao.quality.qms.objectiveStatus.ended' },
] as const;

export const QMS_OBJECTIVE_PERIOD_OPTIONS = [
  { value: 'month', labelKey: 'app.kuaizhizao.quality.qms.objectivePeriod.month' },
  { value: 'quarter', labelKey: 'app.kuaizhizao.quality.qms.objectivePeriod.quarter' },
] as const;

export const QMS_LEGAL_CONCLUSION_OPTIONS = [
  { value: 'conform', labelKey: 'app.kuaizhizao.quality.qms.legalConclusion.conform' },
  { value: 'need_rectify', labelKey: 'app.kuaizhizao.quality.qms.legalConclusion.needRectify' },
] as const;

export const QMS_EXTERNAL_AUDIT_TYPE_OPTIONS = [
  { value: 'initial', labelKey: 'app.kuaizhizao.quality.qms.externalAuditType.initial' },
  { value: 'surveillance', labelKey: 'app.kuaizhizao.quality.qms.externalAuditType.surveillance' },
  {
    value: 'recertification',
    labelKey: 'app.kuaizhizao.quality.qms.externalAuditType.recertification',
  },
] as const;

export const QMS_CERTIFICATE_STATUS_OPTIONS = [
  { value: 'valid', labelKey: 'app.kuaizhizao.quality.qms.certificateStatus.valid' },
  { value: 'expiring', labelKey: 'app.kuaizhizao.quality.qms.certificateStatus.expiring' },
  { value: 'expired', labelKey: 'app.kuaizhizao.quality.qms.certificateStatus.expired' },
] as const;
