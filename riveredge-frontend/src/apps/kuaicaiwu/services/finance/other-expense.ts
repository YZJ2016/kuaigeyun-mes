import { apiRequest } from '../../../../services/api';

export const OTHER_EXPENSE_RESOURCE = 'kuaicaiwu:other-expense';

const base = '/apps/kuaicaiwu/other-expenses';

export type OtherVoucherLine = {
  id?: number;
  line_no?: number;
  category_code: string;
  category_name?: string;
  amount: number;
  description?: string;
  gl_account_code?: string;
};

export type RelatedPurchaseReceiptRef = {
  id: number;
  code: string;
};

export type OtherExpensePurchaseReceiptLinkCandidate = {
  id: number;
  code: string;
  receipt_code?: string;
  supplier_id?: number | null;
  supplier_name?: string;
  source_status?: string;
  source_date?: string;
  amount?: number;
  items?: Array<{
    material_name?: string;
    material_code?: string;
    material_spec?: string;
    material_model?: string;
  }>;
  item_count?: number;
  purchase_order_code?: string | null;
  total_quantity?: number;
};

export type OtherExpenseApplicationPullCandidate = {
  id: number;
  application_code: string;
  business_date?: string;
  counterparty_name?: string;
  total_amount?: number;
  remaining_amount?: number;
  payment_method?: string;
  capabilities?: {
    pull_other_expense?: { allowed: boolean; reason?: string };
  };
};

export type OtherExpenseVoucher = {
  id: number;
  expense_code: string;
  source_type?: string;
  source_id?: number;
  source_code?: string;
  business_date: string;
  counterparty_kind: string;
  counterparty_id?: number;
  counterparty_name?: string;
  total_amount: number;
  payment_method: string;
  bank_account_id?: number;
  status: string;
  review_status?: string;
  notes?: string;
  department_id?: number | null;
  department_name?: string | null;
  attachments?: unknown[];
  related_purchase_receipts?: RelatedPurchaseReceiptRef[] | null;
  lines: OtherVoucherLine[];
  capabilities?: Record<string, { allowed: boolean; reason?: string | null } | undefined>;
  audit?: { phase?: string; allowed_actions?: string[]; [key: string]: unknown };
  /** 审核后 MiscVoucherFinanceBridge 回写 */
  payable_id?: number;
  payable_code?: string;
  payment_id?: number;
  payment_code?: string;
};

export const otherExpenseService = {
  list: (params?: Record<string, unknown>) =>
    apiRequest<{ items: OtherExpenseVoucher[]; total: number }>(base, { method: 'GET', params }),
  get: (id: number) => apiRequest<OtherExpenseVoucher>(`${base}/${id}`, { method: 'GET' }),
  create: (data: Record<string, unknown>) => apiRequest<OtherExpenseVoucher>(base, { method: 'POST', data }),
  update: (id: number, data: Record<string, unknown>) =>
    apiRequest<OtherExpenseVoucher>(`${base}/${id}`, { method: 'PUT', data }),
  delete: (id: number) => apiRequest(`${base}/${id}`, { method: 'DELETE' }),
  listApplicationPullCandidates: (params?: {
    skip?: number;
    limit?: number;
    keyword?: string;
  }) =>
    apiRequest<{ data: OtherExpenseApplicationPullCandidate[]; total: number; success: boolean }>(
      `${base}/pull-candidates/other-expense-applications`,
      { method: 'GET', params },
    ),
  previewFromApplication: (applicationId: number) =>
    apiRequest<Record<string, unknown>>(
      `${base}/from-other-expense-application/${applicationId}/pull-preview`,
      { method: 'GET' },
    ),
  listPurchaseReceiptLinkCandidates: (params: {
    supplier_id: number;
    skip?: number;
    limit?: number;
    keyword?: string;
  }) =>
    apiRequest<{ data: OtherExpensePurchaseReceiptLinkCandidate[]; total: number; success: boolean }>(
      `${base}/pull-candidates/purchase-receipts`,
      { method: 'GET', params },
    ),
  /** @deprecated 页面提交走 commit；保留给旧调用 */
  submit: (id: number) =>
    apiRequest<OtherExpenseVoucher>(`/core/uni-audit/other_expense/${id}/submit`, { method: 'POST' }),
  commit: (id: number) =>
    apiRequest<OtherExpenseVoucher>(`/core/uni-audit/other_expense/${id}/submit`, { method: 'POST' }),
  submitForReview: (id: number) =>
    apiRequest<OtherExpenseVoucher>(`/core/uni-audit/other_expense/${id}/submit_review`, { method: 'POST' }),
  withdraw: (id: number) =>
    apiRequest<OtherExpenseVoucher>(`/core/uni-audit/other_expense/${id}/withdraw`, { method: 'POST' }),
  approve: (id: number, body?: { review_remarks?: string }) =>
    apiRequest<OtherExpenseVoucher>(`/core/uni-audit/other_expense/${id}/approve`, {
      method: 'POST',
      data: body,
    }),
  reject: (id: number, body?: { review_remarks?: string }) =>
    apiRequest<OtherExpenseVoucher>(`/core/uni-audit/other_expense/${id}/reject`, {
      method: 'POST',
      data: { reason: body?.review_remarks || '审批驳回' },
    }),
  revoke: (id: number) =>
    apiRequest<OtherExpenseVoucher>(`/core/uni-audit/other_expense/${id}/revoke`, { method: 'POST' }),
  confirm: (id: number) => apiRequest<OtherExpenseVoucher>(`${base}/${id}/confirm`, { method: 'POST' }),
  unconfirm: (id: number) => apiRequest<OtherExpenseVoucher>(`${base}/${id}/unconfirm`, { method: 'POST' }),
  cancel: (id: number) => apiRequest<OtherExpenseVoucher>(`${base}/${id}/cancel`, { method: 'POST' }),
};
