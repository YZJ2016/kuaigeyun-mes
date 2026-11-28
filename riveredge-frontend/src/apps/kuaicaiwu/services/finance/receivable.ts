import { apiRequest } from '../../../../services/api';
import type { DocumentPushPreview } from '../../../kuaizhizao/services/purchase-requisition';
import { Receivable, ReceivableCreateData, ReceivableListParams, ReceiptRecordCreate } from '../../types/finance/receivable';

const RECEIVABLE_API = '/apps/kuaicaiwu/receivables';

export type ReceivablePullPreview = DocumentPushPreview & {
  source_code?: string;
  source_type?: 'sales_order' | 'sales_delivery';
  customer_id?: number;
  customer_name?: string;
  sales_order_id?: number | null;
  sales_order_code?: string | null;
  max_push_total?: number;
};

export type ReceivablePullCandidate = {
  id: number;
  code: string;
  order_code?: string;
  delivery_code?: string;
  customer_id?: number | null;
  customer_name?: string;
  source_status?: string;
  source_date?: string;
  amount?: number;
  capabilities?: { pull_receivable?: { allowed?: boolean; reason?: string } };
};

export type ReceivableListItem = Receivable & {
  capabilities?: { push_receipt?: { allowed?: boolean; reason?: string } };
};

export const receivableService = {
  createReceivable: (data: ReceivableCreateData) => {
    return apiRequest<Receivable>(RECEIVABLE_API, {
      method: 'POST',
      data,
    });
  },

  listReceivables: (params: ReceivableListParams) => {
    return apiRequest<{ items: ReceivableListItem[]; total: number }>(RECEIVABLE_API, {
      method: 'GET',
      params,
    });
  },

  listSalesOrderPullCandidates: async (params?: { skip?: number; limit?: number; keyword?: string }) =>
    apiRequest<{ data: ReceivablePullCandidate[]; total: number; success: boolean }>(
      `${RECEIVABLE_API}/pull-candidates/sales-orders`,
      { method: 'GET', params },
    ),

  listSalesDeliveryPullCandidates: async (params?: { skip?: number; limit?: number; keyword?: string }) =>
    apiRequest<{ data: ReceivablePullCandidate[]; total: number; success: boolean }>(
      `${RECEIVABLE_API}/pull-candidates/sales-deliveries`,
      { method: 'GET', params },
    ),

  previewPullFromSalesOrder: async (orderId: number) =>
    apiRequest<ReceivablePullPreview>(`${RECEIVABLE_API}/from-sales-order/${orderId}/pull-preview`, {
      method: 'GET',
    }),

  previewPullFromSalesDelivery: async (deliveryId: number) =>
    apiRequest<ReceivablePullPreview>(`${RECEIVABLE_API}/from-sales-delivery/${deliveryId}/pull-preview`, {
      method: 'GET',
    }),

  previewPullFromSalesDeliveries: async (deliveryIds: number[]) =>
    apiRequest<ReceivablePullPreview>(`${RECEIVABLE_API}/from-sales-deliveries/pull-preview`, {
      method: 'GET',
      params: { delivery_ids: deliveryIds.join(',') },
    }),

  getReceivable: (id: number) => {
    return apiRequest<Receivable>(`${RECEIVABLE_API}/${id}`, {
      method: 'GET',
    });
  },

  updateReceivable: (id: number, data: Partial<ReceivableCreateData>) => {
    return apiRequest<Receivable>(`${RECEIVABLE_API}/${id}`, {
      method: 'PUT',
      data,
    });
  },

  recordReceipt: (id: number, data: ReceiptRecordCreate) => {
    return apiRequest<Receivable>(`${RECEIVABLE_API}/${id}/receipt`, {
      method: 'POST',
      data,
    });
  },

  deleteReceivable: (id: number) => {
    return apiRequest<void>(`${RECEIVABLE_API}/${id}`, {
      method: 'DELETE',
    });
  },

  mergeCreateReceipt: (data: MergeReceiptCreatePayload) =>
    apiRequest<MergeFinanceVoucherResult>(`${RECEIVABLE_API}/merge-receipt`, {
      method: 'POST',
      data,
    }),

  mergeCreateSalesInvoice: (data: MergeSalesInvoiceCreatePayload) =>
    apiRequest<MergeFinanceVoucherResult>(`${RECEIVABLE_API}/merge-sales-invoice`, {
      method: 'POST',
      data,
    }),

  commitReceivable: (id: number) =>
    apiRequest<Receivable>(`/core/uni-audit/receivable/${id}/submit`, { method: 'POST' }),

  submitReceivableForReview: (id: number) =>
    apiRequest<Receivable>(`/core/uni-audit/receivable/${id}/submit_review`, {
      method: 'POST',
    }),

  withdrawReceivable: (id: number) =>
    apiRequest<Receivable>(`/core/uni-audit/receivable/${id}/withdraw`, { method: 'POST' }),

  approveReceivable: (id: number) =>
    apiRequest<Receivable>(`/core/uni-audit/receivable/${id}/approve`, { method: 'POST' }),

  revokeReceivable: (id: number) =>
    apiRequest<Receivable>(`/core/uni-audit/receivable/${id}/revoke`, { method: 'POST' }),
};

export type MergeFinanceAllocationLine = {
  source_id: number;
  amount: number;
};

export type MergeFinanceVoucherResult = {
  voucher_type: string;
  voucher_id: number;
  voucher_code: string;
  total_amount: number;
  partner_id: number;
  partner_name: string;
  allocations: Array<{ source_id: number; source_code?: string; amount: number }>;
};

export type MergeReceiptCreatePayload = {
  allocations: MergeFinanceAllocationLine[];
  receipt_date: string;
  payment_method: string;
  bank_account?: string;
  bank_account_id?: number;
  settlement_type?: string;
  notes?: string;
  attachments?: Record<string, unknown>[];
};

export type MergeSalesInvoiceCreatePayload = {
  allocations: MergeFinanceAllocationLine[];
  invoice_date: string;
  invoice_number?: string;
  invoice_type?: string;
  tax_rate?: number;
  notes?: string;
};
