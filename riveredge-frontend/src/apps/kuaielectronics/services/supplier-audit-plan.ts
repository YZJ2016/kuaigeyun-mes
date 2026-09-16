import { apiRequest } from '../../../services/api';

const BASE = '/apps/kuaielectronics/supplier-audit-plan-guide';

export type SupplierAuditPlanField = {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
};

export type SupplierAuditPlanGuideSummary = {
  enabled: boolean;
  plan_name_pattern?: string;
  period_type?: string;
  default_audit_mode?: string;
  default_template_code?: string;
  line_fields?: SupplierAuditPlanField[];
  month_tracking?: {
    months: number[];
    row_kinds: Array<{ key: string; label: string }>;
  };
  quarterly_review_summary?: {
    title: string;
    columns: Array<{ key: string; label: string }>;
  };
  source_note?: string;
};

export const supplierAuditPlanApi = {
  getGuide: async () =>
    (await apiRequest(`${BASE}`, { method: 'GET' })) as SupplierAuditPlanGuideSummary,
};
