import { apiRequest } from '../../../../services/api';
import type { FinancePullCandidateListParams } from './financePullListParams';
import type { DocumentPushPreview } from '../../../kuaizhizao/services/purchase-requisition';

export interface ReceiptListParams {
  skip?: number;
  limit?: number;
  status?: string;
  customer_id?: number;
  unsettled_only?: boolean;
  settlement_type?: string;
  source_id?: number;
  start_date?: string;
  end_date?: string;
  keyword?: string;
  receipt_code?: string;
  customer_name?: string;
  created_start_date?: string;
  created_end_date?: string;
  updated_start_date?: string;
  updated_end_date?: string;
  sort_field?: string;
  sort_order?: 'asc' | 'desc';
}

export interface ReceiptVoucher {
  id: number;
  receipt_code: string;
  customer_id: number;
  customer_name: string;
  total_amount: number;
  settled_amount: number;
  unsettled_amount: number;
  receipt_date: string;
  payment_method: string;
  bank_account?: string;
  bank_account_id?: number;
  counterparty_account_name?: string;
  counterparty_bank_name?: string;
  counterparty_bank_account?: string;
  status: string;
  review_status?: string;
  audit?: {
    allowed_actions?: string[];
    phase?: string;
    enabled?: boolean;
    mode?: string;
    viewer_actions?: {
      has_my_pending_task?: boolean;
      approve?: boolean;
      my_acted?: boolean;
      block_reason?: string | null;
    } | null;
  } | null;
  source_voucher_id?: number;
  source_voucher_code?: string;
  source_vouchers?: { id: number; code: string }[];
  settlement_type?: string;
  refunded_amount?: number;
  refund_execution_status?: string;
  notes?: string;
  created_at: string;
  updated_at?: string;
  created_by_name?: string;
  updated_by_name?: string;
  linked_refund_vouchers?: Array<{ id: number; code: string }>;
  linked_source_documents?: Array<{
    source_type: string;
    id: number;
    code: string;
  }>;
  linked_partner_statements?: Array<{
    id: number;
    statement_code: string;
    statement_period: string;
    status: string;
  }>;
  capabilities?: Record<string, { allowed: boolean; reason?: string | null } | undefined>;
  pull_lines?: Array<{
    line_no: number;
    source_type: string;
    source_id: number;
    source_code?: string;
    amount: number;
    max_amount?: number;
  }>;
  attachments?: unknown;
}

export type ReceiptPullPreview = DocumentPushPreview & {
  source_code?: string;
  source_type?: 'receivable';
  customer_id?: number;
  customer_name?: string;
  receivable_id?: number | null;
  receivable_code?: string | null;
  max_push_total?: number;
};

export type ReceiptSalesOrderPrepaymentPullCandidate = {
  id: number;
  code: string;
  order_code?: string;
  customer_id?: number;
  customer_name?: string;
  partnerName?: string;
  documentDate?: string | null;
  amount?: number | null;
  status?: string;
  review_status?: string;
  capabilities?: {
    pull_prepayment?: { allowed?: boolean; reason?: string | null };
  };
};

export type ReceiptPullCandidate = {
  id: number;
  code: string;
  receivable_code?: string;
  customer_name?: string;
  customer_id?: number;
  source_status?: string;
  review_status?: string;
  source_date?: string;
  amount?: number;
  remaining_amount?: number;
  capabilities?: { pull_receipt?: { allowed?: boolean; reason?: string } };
};

export type ReceiptCreateData = {
  customer_id: number;
  customer_name: string;
  total_amount: number;
  receipt_date: string;
  payment_method: string;
  bank_account?: string;
  bank_account_id?: number;
  counterparty_account_name?: string;
  counterparty_bank_name?: string;
  counterparty_bank_account?: string;
  settlement_type?: string;
  notes?: string;
  attachments?: unknown;
  source_type?: 'receivable';
  source_id?: number;
  source_ids?: number[];
  pull_lines?: Array<{
    source_type: string;
    source_id: number;
    source_code?: string;
    amount: number;
  }>;
};

const RECEIPT_API = '/apps/kuaicaiwu/receipts';

export const receiptService = {
  create: (data: ReceiptCreateData) =>
    apiRequest<ReceiptVoucher>(RECEIPT_API, {
      method: 'POST',
      data,
    }),

  listReceipts: (params: ReceiptListParams) => {
    return apiRequest<{ items: ReceiptVoucher[]; total: number }>(RECEIPT_API, {
      method: 'GET',
      params,
    });
  },

  getReceipt: (id: number) => {
    return apiRequest<ReceiptVoucher>(`${RECEIPT_API}/${id}`, {
      method: 'GET',
    });
  },

  confirmReceipt: (id: number) => {
    return apiRequest<ReceiptVoucher>(`${RECEIPT_API}/${id}/confirm`, {
      method: 'POST',
    });
  },

  cancelReceipt: (id: number) => {
    return apiRequest<ReceiptVoucher>(`${RECEIPT_API}/${id}/cancel`, {
      method: 'POST',
    });
  },

  repairSettlement: (id: number) => {
    return apiRequest<ReceiptVoucher>(`${RECEIPT_API}/${id}/repair-settlement`, {
      method: 'POST',
    });
  },

  commitReceipt: (id: number) =>
    apiRequest<ReceiptVoucher>(`/core/uni-audit/receipt/${id}/submit`, { method: 'POST' }),

  submitReceiptForReview: (id: number) =>
    apiRequest<ReceiptVoucher>(`/core/uni-audit/receipt/${id}/submit_review`, { method: 'POST' }),

  withdrawReceipt: (id: number) =>
    apiRequest<ReceiptVoucher>(`/core/uni-audit/receipt/${id}/withdraw`, { method: 'POST' }),

  approveReceipt: (id: number) =>
    apiRequest<ReceiptVoucher>(`/core/uni-audit/receipt/${id}/approve`, { method: 'POST' }),

  revokeReceipt: (id: number) =>
    apiRequest<ReceiptVoucher>(`/core/uni-audit/receipt/${id}/revoke`, { method: 'POST' }),

  unconfirmReceipt: (id: number) => {
    return apiRequest<ReceiptVoucher>(`${RECEIPT_API}/${id}/unconfirm`, {
      method: 'POST',
    });
  },

  updateReceipt: (id: number, data: Partial<ReceiptCreateData>) => {
    return apiRequest<ReceiptVoucher>(`${RECEIPT_API}/${id}`, {
      method: 'PUT',
      data,
    });
  },

  deleteReceipt: (id: number) => {
    return apiRequest<void>(`${RECEIPT_API}/${id}`, {
      method: 'DELETE',
    });
  },

  listReceivablePullCandidates: async (params?: { skip?: number; limit?: number; keyword?: string }) =>
    apiRequest<{ data: ReceiptPullCandidate[]; total: number; success: boolean }>(
      `${RECEIPT_API}/pull-candidates/receivables`,
      { method: 'GET', params },
    ),

  listSalesOrderPrepaymentPullCandidates: async (params?: FinancePullCandidateListParams) =>
    apiRequest<{ data: ReceiptSalesOrderPrepaymentPullCandidate[]; total: number; success: boolean }>(
      `${RECEIPT_API}/pull-candidates/sales-orders`,
      { method: 'GET', params },
    ),

  previewPullFromReceivable: async (receivableId: number) =>
    apiRequest<ReceiptPullPreview>(`${RECEIPT_API}/from-receivable/${receivableId}/pull-preview`, {
      method: 'GET',
    }),

  previewPullFromReceivables: async (receivableIds: number[]) =>
    apiRequest<ReceiptPullPreview>(
      `${RECEIPT_API}/from-receivables/pull-preview?receivable_ids=${receivableIds.join(',')}`,
      { method: 'GET' },
    ),

  previewPullFromSalesOrder: async (salesOrderId: number) =>
    apiRequest<DocumentPushPreview & { customer_id?: number; source_code?: string }>(
      `${RECEIPT_API}/from-sales-order/${salesOrderId}/pull-preview`,
      { method: 'GET' },
    ),
};
