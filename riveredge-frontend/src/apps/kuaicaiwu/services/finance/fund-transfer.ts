import { apiRequest } from '../../../../services/api';

export type FundTransferType = 'internal' | 'external_out' | 'external_in';

export type FundTransfer = {
  id: number;
  tenant_id: number;
  transfer_code: string;
  transfer_date: string;
  transfer_type: FundTransferType;
  from_bank_account_id?: number | null;
  to_bank_account_id?: number | null;
  from_account_code?: string | null;
  from_account_name?: string | null;
  to_account_code?: string | null;
  to_account_name?: string | null;
  external_account_name?: string | null;
  external_bank_name?: string | null;
  external_account_number?: string | null;
  amount: number;
  currency: string;
  status: string;
  review_status?: string | null;
  notes?: string | null;
  attachments?: unknown;
  created_at?: string;
  updated_at?: string;
  created_by_name?: string | null;
  updated_by_name?: string | null;
  audit?: Record<string, unknown>;
};

export type FundTransferListParams = {
  skip?: number;
  limit?: number;
  keyword?: string;
  transfer_code?: string;
  transfer_type?: FundTransferType;
  status?: string;
  transfer_date_start?: string;
  transfer_date_end?: string;
  sort_field?: string;
  sort_order?: string;
};

export type FundTransferCreateData = {
  transfer_date: string;
  transfer_type: FundTransferType;
  amount: number;
  from_bank_account_id?: number;
  to_bank_account_id?: number;
  external_account_name?: string;
  external_bank_name?: string;
  external_account_number?: string;
  currency?: string;
  notes?: string;
  attachments?: unknown;
};

export type FundTransferUpdateData = Partial<FundTransferCreateData>;

const API = '/apps/kuaicaiwu/fund-transfers';

export const FUND_TRANSFER_RESOURCE = 'kuaicaiwu:fund-transfer';

export const fundTransferService = {
  list: (params?: FundTransferListParams) =>
    apiRequest<{ items: FundTransfer[]; total: number }>(API, { method: 'GET', params }),

  get: (id: number) => apiRequest<FundTransfer>(`${API}/${id}`, { method: 'GET' }),

  create: (data: FundTransferCreateData) =>
    apiRequest<FundTransfer>(API, { method: 'POST', data }),

  update: (id: number, data: FundTransferUpdateData) =>
    apiRequest<FundTransfer>(`${API}/${id}`, { method: 'PUT', data }),

  delete: (id: number) => apiRequest<void>(`${API}/${id}`, { method: 'DELETE' }),

  confirm: (id: number) => apiRequest<FundTransfer>(`${API}/${id}/confirm`, { method: 'POST' }),

  unconfirm: (id: number) => apiRequest<FundTransfer>(`${API}/${id}/unconfirm`, { method: 'POST' }),

  cancel: (id: number) => apiRequest<FundTransfer>(`${API}/${id}/cancel`, { method: 'POST' }),

  commitTransfer: (id: number) =>
    apiRequest<FundTransfer>(`/core/uni-audit/fund_transfer/${id}/submit`, { method: 'POST' }),

  submitTransferForReview: (id: number) =>
    apiRequest<FundTransfer>(`/core/uni-audit/fund_transfer/${id}/submit_review`, {
      method: 'POST',
    }),

  withdrawTransfer: (id: number) =>
    apiRequest<FundTransfer>(`/core/uni-audit/fund_transfer/${id}/withdraw`, { method: 'POST' }),

  approveTransfer: (id: number) =>
    apiRequest<FundTransfer>(`/core/uni-audit/fund_transfer/${id}/approve`, { method: 'POST' }),

  revokeTransfer: (id: number) =>
    apiRequest<FundTransfer>(`/core/uni-audit/fund_transfer/${id}/revoke`, { method: 'POST' }),
};
