export const FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED = new Set([
  'tech_work_contact',
  'confirmation',
  'review_sheet',
  'material_issue',
]);

export function isFormRequestIssueScopedBusinessType(type?: string | null): boolean {
  return FORM_REQUEST_BUSINESS_TYPES_ISSUE_SCOPED.has(String(type || '').trim().toLowerCase());
}
