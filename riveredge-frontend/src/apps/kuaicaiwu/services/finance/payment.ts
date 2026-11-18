import { apiRequest } from '../../../../services/api';
import type { DocumentPushPreview } from '../../../kuaizhizao/services/purchase-requisition';

export interface PaymentListParams {
  skip?: number;
  limit?: number;
  status?: string;
  supplier_id?: number;
  unsettled_only?: boolean;
  settlement_type?: string;
  source_id?: number;
  start_date?: string;
  end_date?: string;
  keyword?: string;
  payment_code?: string;
  supplier_name?: string;
  created_start_date?: string;
  created_end_date?: string;
  updated_start_date?: string;
  updated_end_date?: string;
  sort_field?: string;
  sort_order?: 'asc' | 'desc';
}

export interface PaymentVoucher {
  id: number;
  payment_code: string;
  supplier_id: number;
  supplier_name: string;
  total_amount: number;
  settled_amount: number;
  unsettled_amount: number;
  payment_date: string;
  payment_method: string;
  bank_account?: string;
  bank_account_id?: number;
  status: string;
  settlement_type?: string;
  refunded_amount?: number;
  refund_execution_status?: string;
  notes?: string;
  /** 来自付款申请：确认过账前必须上传付款凭证 */
  require_payment_voucher?: boolean;
  attachments?: unknown;
  created_at: string;
  updated_at?: string;
  created_by_name?: string;
  updated_by_name?: string;
  linked_source_documents?: Array<{
    source_type: 'payable' | 'payment_application' | string;
    id: number;
    code: string;
  }>;
  capabilities?: {
    pull_payment_refund?: { allowed?: boolean; reason?: string };
    repair_bank_flow?: { allowed?: boolean; reason?: string };
    print?: { allowed?: boolean; reason?: string };
  };
  pull_lines?: Array<{
    line_no: number;
    source_type: string;
    source_id: number;
    source_code?: string;
    amount: number;
    max_amount?: number;
  }>;
  offset_prepayment_lines?: Array<{
    line_no: number;
    prepayment_payment_id: number;
    source_code?: string;
    amount: number;
    purchase_order_id?: number;
    purchase_order_code?: string;
    unsettled_amount?: number;
  }>;
}


export type PaymentPullPreview = DocumentPushPreview & {
  source_code?: string;
  source_type?: 'payable' | 'payment_application';
  supplier_id?: number;
  supplier_name?: string;
  payable_id?: number | null;
  payable_code?: string | null;
  require_payment_voucher?: boolean;
  max_push_total?: number;
  counterparty_account_name?: string | null;
  counterparty_bank_name?: string | null;
  counterparty_bank_account?: string | null;
  payment_method?: string | null;
  advance_payee_id?: number | null;
  advance_payee_name?: string | null;
};

export type PaymentPullCandidate = {
  id: number;
  code: string;
  payable_code?: string;
  application_kind?: 'prepayment' | 'goods' | 'mixed' | 'invoice' | string;
  supplier_id?: number;
  supplier_name?: string;
  source_status?: string;
  review_status?: string;
  source_date?: string;
  amount?: number;
  remaining_amount?: number;
  capabilities?: { pull_payment?: { allowed?: boolean; reason?: string } };
};

export type PaymentCreateData = {
  supplier_id: number;
  supplier_name: string;
  total_amount: number;
  payment_date: string;
  payment_method: string;
  bank_account?: string;
  bank_account_id?: number;
  counterparty_account_name?: string;
  counterparty_bank_name?: string;
  counterparty_bank_account?: string;
  advance_payee_id?: number;
  advance_payee_name?: string;
  settlement_type?: string;
  notes?: string;
  require_payment_voucher?: boolean;
  attachments?: unknown;
  source_type?: 'payable' | 'payment_application';
  source_id?: number;
  pull_lines?: Array<{
    source_type: string;
    source_id: number;
    source_code?: string;
    amount: number;
  }>;
};

const PAYMENT_API = '/apps/kuaicaiwu/payments';

export const paymentService = {
  create: (data: PaymentCreateData) =>
    apiRequest<PaymentVoucher>(PAYMENT_API, {
      method: 'POST',
      data,
    }),

  listPayments: (params: PaymentListParams) => {
    return apiRequest<{ items: PaymentVoucher[]; total: number }>(PAYMENT_API, {
      method: 'GET',
      params,
    });
  },

  getPayment: (id: number) => {
    return apiRequest<PaymentVoucher>(`${PAYMENT_API}/${id}`, {
      method: 'GET',
    });
  },

  confirmPayment: (id: number) => {
    return apiRequest<PaymentVoucher>(`${PAYMENT_API}/${id}/confirm`, {
      method: 'POST',
    });
  },

  cancelPayment: (id: number) => {
    return apiRequest<PaymentVoucher>(`${PAYMENT_API}/${id}/cancel`, {
      method: 'POST',
    });
  },

  unconfirmPayment: (id: number) => {
    return apiRequest<PaymentVoucher>(`${PAYMENT_API}/${id}/unconfirm`, {
      method: 'POST',
    });
  },

  updatePayment: (id: number, data: Partial<PaymentCreateData>) => {
    return apiRequest<PaymentVoucher>(`${PAYMENT_API}/${id}`, {
      method: 'PUT',
      data,
    });
  },

  deletePayment: (id: number) => {
    return apiRequest<void>(`${PAYMENT_API}/${id}`, {
      method: 'DELETE',
    });
  },

  listPayablePullCandidates: async (params?: { skip?: number; limit?: number; keyword?: string }) =>
    apiRequest<{ data: PaymentPullCandidate[]; total: number; success: boolean }>(
      `${PAYMENT_API}/pull-candidates/payables`,
      { method: 'GET', params },
    ),

  previewPullFromPayable: async (payableId: number) =>
    apiRequest<PaymentPullPreview>(`${PAYMENT_API}/from-payable/${payableId}/pull-preview`, {
      method: 'GET',
    }),

  previewPullFromPayables: async (payableIds: number[]) =>
    apiRequest<PaymentPullPreview>(`${PAYMENT_API}/from-payables/pull-preview`, {
      method: 'GET',
      params: { payable_ids: payableIds.join(',') },
    }),

  listPaymentApplicationPullCandidates: async (params?: {
    skip?: number;
    limit?: number;
    keyword?: string;
    supplier_id?: number;
    application_kind?: 'prepayment' | 'goods' | 'mixed' | 'invoice' | string;
  }) =>
    apiRequest<{ data: PaymentPullCandidate[]; total: number; success: boolean }>(
      `${PAYMENT_API}/pull-candidates/payment-applications`,
      { method: 'GET', params },
    ),

  previewPullFromPaymentApplication: async (applicationId: number) =>
    apiRequest<PaymentPullPreview>(
      `${PAYMENT_API}/from-payment-application/${applicationId}/pull-preview`,
      { method: 'GET' },
    ),

  previewPullFromPurchaseOrder: async (purchaseOrderId: number) =>
    apiRequest<PaymentPullPreview>(
      `${PAYMENT_API}/from-purchase-order/${purchaseOrderId}/pull-preview`,
      { method: 'GET' },
    ),
};
