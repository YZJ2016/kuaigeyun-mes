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

export const QMS_REVIEW_STATUS_OPTIONS = [
  { value: 'draft', labelKey: 'app.kuaizhizao.quality.qms.reviewStatus.draft' },
  { value: 'in_progress', labelKey: 'app.kuaizhizao.quality.qms.reviewStatus.inProgress' },
  { value: 'completed', labelKey: 'app.kuaizhizao.quality.qms.reviewStatus.completed' },
  { value: 'closed', labelKey: 'app.kuaizhizao.quality.qms.reviewStatus.closed' },
] as const;
