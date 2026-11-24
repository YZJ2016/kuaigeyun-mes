import { apiRequest } from '../../../../services/api';
import type { DocumentLineMaterialPreviewItem } from '../../../../components/document-line-materials-preview';

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
  payee_id?: number;
  payee_name?: string;
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
  items?: DocumentLineMaterialPreviewItem[];
  item_count?: number;
  purchase_order_code?: string | null;
  total_quantity?: number;
};

export type OtherExpenseVoucher = {
  id: number;
  expense_code: string;
  business_date: string;
  counterparty_kind: string;
  counterparty_id?: number;
  counterparty_name?: string;
  total_amount: number;
  payment_method: string;
  bank_account_id?: number;
  status: string;
  notes?: string;
  department_id?: number | null;
  department_name?: string | null;
  attachments?: unknown[];
  related_purchase_receipts?: RelatedPurchaseReceiptRef[] | null;
  lines: OtherVoucherLine[];
  capabilities?: Record<string, { allowed: boolean; reason?: string }>;
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
  submit: (id: number) => apiRequest<OtherExpenseVoucher>(`${base}/${id}/submit`, { method: 'POST' }),
  approve: (id: number, body?: { review_remarks?: string }) =>
    apiRequest<OtherExpenseVoucher>(`${base}/${id}/approve`, { method: 'POST', data: { approved: true, ...body } }),
  reject: (id: number, body?: { review_remarks?: string }) =>
    apiRequest<OtherExpenseVoucher>(`${base}/${id}/reject`, { method: 'POST', data: { approved: false, ...body } }),
  confirm: (id: number) => apiRequest<OtherExpenseVoucher>(`${base}/${id}/confirm`, { method: 'POST' }),
  unconfirm: (id: number) => apiRequest<OtherExpenseVoucher>(`${base}/${id}/unconfirm`, { method: 'POST' }),
  cancel: (id: number) => apiRequest<OtherExpenseVoucher>(`${base}/${id}/cancel`, { method: 'POST' }),
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
};
