import { apiRequest } from '../../../../services/api';

export interface PartnerStatementLine {
  date: string;
  doc_type: string;
  doc_code: string;
  summary?: string;
  /** 关联进项/销项发票开票日期 */
  invoice_date?: string | null;
  debit: number;
  credit: number;
  balance: number;
  doc_id?: number;
  doc_amount?: number;
  prior_stated_amount?: number;
  remaining_amount?: number;
  statement_amount?: number;
  /** 0=应收/应付等主行，1=其下核销的收/付款单 */
  tree_level?: number;
  parent_doc_id?: number;
  parent_doc_code?: string;
  inbound_detail_doc_type?: string;
  inbound_detail_doc_id?: number;
  /** 采购入库已保存未税合计；其它单据无拆分时为空 */
  amount_excluding_tax?: number | null;
  /** 采购入库已保存税额 */
  tax_amount?: number | null;
  /** 采购入库已保存价税合计 */
  amount_including_tax?: number | null;
}

export type PartnerStatementAmountBasis = 'tax_inclusive' | 'tax_exclusive';

export interface PartnerStatementSummary {
  opening_balance: number;
  debit_total: number;
  credit_total: number;
  closing_balance: number;
}

export interface PartnerStatementPreview {
  partner_id: number;
  partner_name: string;
  partner_type: string;
  start_date: string;
  end_date: string;
  company_name: string;
  balance_label: string;
  summary: PartnerStatementSummary;
  lines: PartnerStatementLine[];
  /** 单据头粒度；列表展示与勾选须用本字段 */
  document_lines?: PartnerStatementLine[];
  partner_snapshot?: Record<string, unknown>;
  /** 本期因已纳入其它对账单而排除的行数 */
  excluded_from_period?: number;
  /** 同一往来同一 YYYY-MM 已存在的对账单 */
  existing_period_statement_id?: number | null;
  existing_period_statement_code?: string | null;
  existing_period?: string | null;
  amount_basis?: PartnerStatementAmountBasis;
  /** 预览：与详情 GET 同语义，控制是否展示立账方式 */
  partner_uses_statement_ledger?: boolean | null;
}

export interface PartnerStatement {
  id: number;
  statement_code: string;
  partner_id: number;
  partner_name: string;
  partner_type: string;
  statement_period: string;
  start_date: string;
  end_date: string;
  opening_balance: number;
  debit_total: number;
  credit_total: number;
  closing_balance: number;
  status: string;
  review_status?: string;
  reviewer_id?: number | null;
  reviewer_name?: string | null;
  review_time?: string | null;
  review_remarks?: string | null;
  company_name?: string;
  transaction_details?: {
    summary?: PartnerStatementSummary;
    lines?: PartnerStatementLine[];
    document_lines?: PartnerStatementLine[];
    balance_label?: string;
    partner_snapshot?: Record<string, unknown>;
    amount_basis?: PartnerStatementAmountBasis;
  };
  confirmed_at?: string;
  sent_at?: string;
  sent_channel?: string;
  dispute_reason?: string;
  disputed_at?: string;
  notes?: string;
  created_at: string;
  updated_at?: string;
  created_by_name?: string;
  updated_by_name?: string;
  audit?: {
    phase?: string;
    enabled?: boolean;
    allowed_actions?: string[];
    entity_type?: string;
  };
  ledger_posted_at?: string | null;
  ledger_posting_mode?: 'immediate' | 'by_invoice' | string | null;
  /** 详情 GET 组装：客商是否按月结对账单立账 */
  partner_uses_statement_ledger?: boolean | null;
}

export interface PartnerStatementRefreshPreviewResult {
  warnings: string[];
  statement: PartnerStatement;
}

export interface PartnerStatementLineAmountInput {
  doc_type: string;
  doc_id: number;
  statement_amount: number;
}

export interface PartnerStatementListParams {
  skip?: number;
  limit?: number;
  partner_type?: string;
  partner_id?: number;
  statement_period?: string;
  status?: string;
  keyword?: string;
  statement_code?: string;
  partner_name?: string;
  created_start_date?: string;
  created_end_date?: string;
  updated_start_date?: string;
  updated_end_date?: string;
  sort_field?: string;
  sort_order?: 'asc' | 'desc';
}

const API = '/apps/kuaicaiwu/partner-statements';

export const partnerStatementService = {
  preview: (params: {
    partner_id: number;
    partner_type: string;
    start_date: string;
    end_date: string;
    amount_basis?: PartnerStatementAmountBasis;
  }) =>
    apiRequest<PartnerStatementPreview>(`${API}/preview`, { method: 'GET', params }),

  create: (data: {
    partner_id: number;
    partner_type: string;
    statement_period: string;
    start_date?: string;
    end_date?: string;
    notes?: string;
    attachments?: Array<{ uid?: string; name?: string; status?: string; url?: string }>;
    line_amounts?: PartnerStatementLineAmountInput[];
    ledger_posting_mode?: 'immediate' | 'by_invoice';
    amount_basis?: PartnerStatementAmountBasis;
  }) => apiRequest<PartnerStatement>(API, { method: 'POST', data }),

  list: (params?: PartnerStatementListParams) =>
    apiRequest<{ items: PartnerStatement[]; total: number }>(API, { method: 'GET', params }),

  get: (id: number) => apiRequest<PartnerStatement>(`${API}/${id}`, { method: 'GET' }),

  updateLines: (id: number, lines: PartnerStatementLineAmountInput[]) =>
    apiRequest<PartnerStatement>(`${API}/${id}/lines`, {
      method: 'PATCH',
      data: { lines },
    }),

  updateHeader: (
    id: number,
    data: { ledger_posting_mode?: 'immediate' | 'by_invoice' },
  ) =>
    apiRequest<PartnerStatement>(`${API}/${id}/header`, {
      method: 'PATCH',
      data,
    }),

  listMaterialLines: (id: number) =>
    apiRequest<{ items: PartnerStatementLine[]; total: number }>(`${API}/${id}/material-lines`),

  refreshPreview: (id: number, data: { amount_basis: PartnerStatementAmountBasis }) =>
    apiRequest<PartnerStatementRefreshPreviewResult>(`${API}/${id}/refresh-preview`, {
      method: 'POST',
      data,
    }),

  confirm: (id: number) => apiRequest<PartnerStatement>(`${API}/${id}/confirm`, { method: 'POST' }),

  commitStatement: (id: number) =>
    apiRequest<PartnerStatement>(`/core/uni-audit/partner_statement/${id}/submit`, {
      method: 'POST',
    }),

  submitStatementForReview: (id: number) =>
    apiRequest<PartnerStatement>(`/core/uni-audit/partner_statement/${id}/submit_review`, {
      method: 'POST',
    }),

  withdrawStatement: (id: number) =>
    apiRequest<PartnerStatement>(`/core/uni-audit/partner_statement/${id}/withdraw`, {
      method: 'POST',
    }),

  approveStatement: (id: number) =>
    apiRequest<PartnerStatement>(`/core/uni-audit/partner_statement/${id}/approve`, {
      method: 'POST',
    }),

  revokeStatement: (id: number) =>
    apiRequest<PartnerStatement>(`/core/uni-audit/partner_statement/${id}/revoke`, {
      method: 'POST',
    }),

  postLedger: (id: number) =>
    apiRequest<PartnerStatement>(`${API}/${id}/post-ledger`, { method: 'POST' }),

  markSent: (id: number, data: { channel: string; notes?: string }) =>
    apiRequest<PartnerStatement>(`${API}/${id}/mark-sent`, { method: 'POST', data }),

  dispute: (id: number, reason: string) =>
    apiRequest<PartnerStatement>(`${API}/${id}/dispute`, { method: 'POST', data: { reason } }),

  delete: (id: number) => apiRequest<void>(`${API}/${id}`, { method: 'DELETE' }),

  exportFile: (id: number, format: 'xlsx' | 'pdf') =>
    apiRequest<Blob>(`${API}/${id}/export`, {
      method: 'GET',
      params: { format },
      responseType: 'blob',
    }),

  getLineDetail: (params: { doc_type: string; doc_id: number }) =>
    apiRequest<{ items: Array<Record<string, unknown>> }>(`${API}/line-detail`, {
      method: 'GET',
      params,
    }),
};

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
