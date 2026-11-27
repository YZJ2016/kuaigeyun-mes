import { apiRequest } from '../../../../services/api';
import type { OtherVoucherLine } from './other-expense';

export const OTHER_EXPENSE_APPLICATION_RESOURCE = 'kuaicaiwu:other-expense-application';

const base = '/apps/kuaicaiwu/other-expense-applications';

export type OtherExpenseApplicationVoucher = {
  id: number;
  application_code: string;
  business_date: string;
  counterparty_kind: string;
  counterparty_id?: number;
  counterparty_name?: string;
  total_amount: number;
  pushed_amount?: number;
  remaining_amount?: number;
  payment_method: string;
  bank_account_id?: number;
  status: string;
  review_status?: string;
  notes?: string;
  attachments?: unknown[];
  lines: OtherVoucherLine[];
  capabilities?: Record<string, { allowed: boolean; reason?: string }>;
  linked_expenses?: { id: number; code: string }[];
};

const noop = async () => undefined;

export const otherExpenseApplicationService = {
  list: (params?: Record<string, unknown>) =>
    apiRequest<{ items: OtherExpenseApplicationVoucher[]; total: number }>(base, {
      method: 'GET',
      params,
    }),
  get: (id: number) => apiRequest<OtherExpenseApplicationVoucher>(`${base}/${id}`, { method: 'GET' }),
  create: (data: Record<string, unknown>) =>
    apiRequest<OtherExpenseApplicationVoucher>(base, { method: 'POST', data }),
  update: (id: number, data: Record<string, unknown>) =>
    apiRequest<OtherExpenseApplicationVoucher>(`${base}/${id}`, { method: 'PUT', data }),
  delete: (id: number) => apiRequest(`${base}/${id}`, { method: 'DELETE' }),
  /** @deprecated 页面提交走 commit；保留给旧调用 */
  submit: (id: number) =>
    apiRequest<OtherExpenseApplicationVoucher>(`/core/uni-audit/other_expense_application/${id}/submit`, {
      method: 'POST',
    }),
  commit: (id: number) =>
    apiRequest<OtherExpenseApplicationVoucher>(`/core/uni-audit/other_expense_application/${id}/submit`, {
      method: 'POST',
    }),
  submitForReview: (id: number) =>
    apiRequest<OtherExpenseApplicationVoucher>(
      `/core/uni-audit/other_expense_application/${id}/submit_review`,
      { method: 'POST' },
    ),
  withdraw: (id: number) =>
    apiRequest<OtherExpenseApplicationVoucher>(`/core/uni-audit/other_expense_application/${id}/withdraw`, {
      method: 'POST',
    }),
  approve: (id: number, body?: { review_remarks?: string }) =>
    apiRequest<OtherExpenseApplicationVoucher>(`/core/uni-audit/other_expense_application/${id}/approve`, {
      method: 'POST',
      data: body,
    }),
  reject: (id: number, body?: { review_remarks?: string }) =>
    apiRequest<OtherExpenseApplicationVoucher>(`/core/uni-audit/other_expense_application/${id}/reject`, {
      method: 'POST',
      data: { reason: body?.review_remarks || '审批驳回' },
    }),
  revoke: (id: number) =>
    apiRequest<OtherExpenseApplicationVoucher>(`/core/uni-audit/other_expense_application/${id}/revoke`, {
      method: 'POST',
    }),
  withdrawSubmit: (id: number) =>
    apiRequest<OtherExpenseApplicationVoucher>(`/core/uni-audit/other_expense_application/${id}/withdraw`, {
      method: 'POST',
    }),
  pushOtherExpense: (id: number, data?: Record<string, unknown>) =>
    apiRequest<{ expense_id: number; expense_code: string }>(`${base}/${id}/push-other-expense`, {
      method: 'POST',
      data: data ?? {},
    }),
  confirm: noop,
  unconfirm: noop,
  cancel: noop,
};
