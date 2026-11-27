import { apiRequest } from '../../../../services/api';
import type { DocumentPushPreview } from '../../../kuaizhizao/services/purchase-requisition';
import {
  PurchaseInvoice,
  PurchaseInvoiceListParams,
  PurchaseInvoiceCreateData,
} from '../../types/finance/purchase-invoice';
import type { FinancePullCandidateListParams } from './financePullListParams';

const PURCHASE_INVOICE_API = '/apps/kuaicaiwu/purchase-invoices';

/** 收票预览：源单物料明细（对照开票内容，只读） */
export type PurchaseInvoicePullDetailLine = {
  line_no: number;
  purchase_receipt_item_id: number;
  material_code: string;
  material_name: string;
  material_spec?: string | null;
  unit: string;
  quantity: number;
  unit_price: number;
  amount: number;
  tax_rate?: number;
  tax_amount?: number;
  occupied_amount: number;
  max_push_amount: number;
  max_push_quantity: number;
  purchase_receipt_id?: number;
  source_doc_code?: string;
  gross_amount?: number;
  source_unit_price_incl?: number;
  warehouse_name?: string;
  location_code?: string;
  batch_number?: string;
};

export type PurchaseInvoicePullPreview = DocumentPushPreview & {
  source_type?: 'purchase_order' | 'purchase_receipt' | 'payable' | 'outsource_order_receipt';
  source_code?: string;
  receipt_ids?: number[];
  outsource_order_receipt_ids?: number[];
  supplier_id?: number;
  supplier_name?: string;
  purchase_order_id?: number | null;
  purchase_order_code?: string | null;
  purchase_receipt_id?: number | null;
  payable_id?: number;
  payable_code?: string;
  /** 同时付款上限（应付剩余可付） */
  remaining_settle_amount?: number;
  /** 多源合并加载时的源单ID列表与可开票合计 */
  source_ids?: number[];
  max_push_total?: number;
  /** 对账单→发票唯一可开票价税合计上限 */
  partner_statement_invoice_budget?: number;
  statement_period_amount?: number;
  /** 源单物料明细，便于确认本次开票对应内容 */
  detail_lines?: PurchaseInvoicePullDetailLine[];
  ledger_posting_mode?: 'immediate' | 'by_invoice' | string;
};

export type PurchaseInvoicePullCandidate = {
  id: number;
  code: string;
  doc_code?: string;
  order_code?: string;
  receipt_code?: string;
  payable_code?: string;
  statement_code?: string;
  supplier_name?: string;
  supplier_id?: number;
  source_status?: string;
  source_date?: string;
  amount?: number;
  period_amount?: number;
  closing_balance?: number;
  invoiceable_amount?: number;
  invoiced_amount?: number;
  /** 入库明细行数 */
  detail_line_count?: number;
  /** 已有收票占用的明细行数 */
  invoiced_line_count?: number;
  amount_basis?: 'tax_inclusive' | 'tax_exclusive' | string;
  payable_ids?: number[];
  receipt_ids?: number[];
  outsource_order_receipt_ids?: number[];
  ledger_posting_mode?: 'immediate' | 'by_invoice' | string;
  capabilities?: { pull_purchase_invoice?: { allowed?: boolean; reason?: string } };
};

export const purchaseInvoiceService = {
  create: (data: PurchaseInvoiceCreateData) => {
    return apiRequest<PurchaseInvoice>(PURCHASE_INVOICE_API, {
      method: 'POST',
      data,
    });
  },

  list: (params: PurchaseInvoiceListParams) => {
    return apiRequest<{ items: PurchaseInvoice[]; total: number }>(PURCHASE_INVOICE_API, {
      method: 'GET',
      params,
    });
  },

  get: (id: number) => {
    return apiRequest<PurchaseInvoice>(`${PURCHASE_INVOICE_API}/${id}`, {
      method: 'GET',
    });
  },

  approve: (id: number, rejection_reason?: string) => {
    return apiRequest<PurchaseInvoice>(`${PURCHASE_INVOICE_API}/${id}/approve`, {
      method: 'POST',
      params: { rejection_reason },
    });
  },

  commitPurchaseInvoice: (id: number) =>
    apiRequest<PurchaseInvoice>(`/core/uni-audit/purchase_invoice/${id}/submit`, { method: 'POST' }),

  submitPurchaseInvoiceForReview: (id: number) =>
    apiRequest<PurchaseInvoice>(`/core/uni-audit/purchase_invoice/${id}/submit_review`, {
      method: 'POST',
    }),

  withdrawPurchaseInvoice: (id: number) =>
    apiRequest<PurchaseInvoice>(`/core/uni-audit/purchase_invoice/${id}/withdraw`, { method: 'POST' }),

  approvePurchaseInvoice: (id: number) =>
    apiRequest<PurchaseInvoice>(`/core/uni-audit/purchase_invoice/${id}/approve`, { method: 'POST' }),

  revokePurchaseInvoice: (id: number) =>
    apiRequest<PurchaseInvoice>(`/core/uni-audit/purchase_invoice/${id}/revoke`, { method: 'POST' }),

  delete: (id: number) => {
    return apiRequest<void>(`${PURCHASE_INVOICE_API}/${id}`, {
      method: 'DELETE',
    });
  },

  update: (
    id: number,
    data: { invoice_number?: string; invoice_date?: string; attachments?: unknown[] },
  ) => {
    return apiRequest<PurchaseInvoice>(`${PURCHASE_INVOICE_API}/${id}`, {
      method: 'PUT',
      data,
    });
  },

  listPurchaseOrderPullCandidates: async (params?: { skip?: number; limit?: number; keyword?: string }) =>
    apiRequest<{ data: PurchaseInvoicePullCandidate[]; total: number; success: boolean }>(
      `${PURCHASE_INVOICE_API}/pull-candidates/purchase-orders`,
      { method: 'GET', params },
    ),

  listPurchaseReceiptPullCandidates: async (params?: { skip?: number; limit?: number; keyword?: string }) =>
    apiRequest<{ data: PurchaseInvoicePullCandidate[]; total: number; success: boolean }>(
      `${PURCHASE_INVOICE_API}/pull-candidates/purchase-receipts`,
      {
        method: 'GET',
        params,
        timeoutMs: 90_000,
        notifyOnGatewayError: true,
      },
    ),

  previewPull: async (params: {
    source_type: string;
    source_ids: number[];
    partner_statement_ids?: number[];
  }) =>
    apiRequest<PurchaseInvoicePullPreview>(`${PURCHASE_INVOICE_API}/pull-preview`, {
      method: 'GET',
      params: {
        source_type: params.source_type,
        source_ids: params.source_ids.join(','),
        ...(params.partner_statement_ids?.length
          ? { partner_statement_ids: params.partner_statement_ids.join(',') }
          : {}),
      },
      notifyOnGatewayError: true,
      timeoutMs: 90_000,
    }),

  previewPullFromPurchaseOrder: async (orderId: number) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-purchase-order/${orderId}/pull-preview`,
      { method: 'GET', notifyOnGatewayError: true, timeoutMs: 60_000 },
    ),

  previewPullFromPurchaseOrders: async (orderIds: number[]) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-purchase-orders/pull-preview?order_ids=${orderIds.join(',')}`,
      { method: 'GET', notifyOnGatewayError: true },
    ),

  previewPullFromPurchaseReceipt: async (
    receiptId: number,
    partnerStatementIds?: number[],
  ) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-purchase-receipt/${receiptId}/pull-preview`,
      {
        method: 'GET',
        params: partnerStatementIds?.length
          ? { partner_statement_ids: partnerStatementIds.join(',') }
          : undefined,
        notifyOnGatewayError: true,
        timeoutMs: 90_000,
      },
    ),

  previewPullFromPurchaseReceipts: async (
    receiptIds: number[],
    partnerStatementIds?: number[],
  ) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-purchase-receipts/pull-preview?receipt_ids=${receiptIds.join(',')}${
        partnerStatementIds?.length ? `&partner_statement_ids=${partnerStatementIds.join(',')}` : ''
      }`,
      { method: 'GET', notifyOnGatewayError: true, timeoutMs: 90_000 },
    ),

  previewPullFromOutsourceOrderReceipt: async (
    batchId: number,
    partnerStatementIds?: number[],
  ) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-outsource-order-receipt/${batchId}/pull-preview`,
      {
        method: 'GET',
        params: partnerStatementIds?.length
          ? { partner_statement_ids: partnerStatementIds.join(',') }
          : undefined,
        notifyOnGatewayError: true,
      },
    ),

  previewPullFromOutsourceOrderReceipts: async (
    batchIds: number[],
    partnerStatementIds?: number[],
  ) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-outsource-order-receipts/pull-preview?outsource_order_receipt_ids=${batchIds.join(',')}${
        partnerStatementIds?.length ? `&partner_statement_ids=${partnerStatementIds.join(',')}` : ''
      }`,
      { method: 'GET', notifyOnGatewayError: true },
    ),

  previewPullFromPartnerStatementSupplierSources: async (params: {
    receiptIds?: number[];
    outsourceOrderReceiptIds?: number[];
    partnerStatementIds: number[];
  }) => {
    const query = new URLSearchParams();
    query.set('partner_statement_ids', params.partnerStatementIds.join(','));
    if (params.receiptIds?.length) {
      query.set('receipt_ids', params.receiptIds.join(','));
    }
    if (params.outsourceOrderReceiptIds?.length) {
      query.set('outsource_order_receipt_ids', params.outsourceOrderReceiptIds.join(','));
    }
    return apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-partner-statement-supplier-sources/pull-preview?${query.toString()}`,
      { method: 'GET', notifyOnGatewayError: true },
    );
  },

  listPayablePullCandidates: async (params?: FinancePullCandidateListParams) =>
    apiRequest<{ data: PurchaseInvoicePullCandidate[]; total: number; success: boolean }>(
      `${PURCHASE_INVOICE_API}/pull-candidates/payables`,
      { method: 'GET', params },
    ),
  listPartnerStatementPullCandidates: async (params?: FinancePullCandidateListParams) =>
    apiRequest<{ data: PurchaseInvoicePullCandidate[]; total: number; success: boolean }>(
      `${PURCHASE_INVOICE_API}/pull-candidates/partner-statements`,
      { method: 'GET', params },
    ),

  previewPullFromPayable: async (payableId: number) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-payable/${payableId}/pull-preview`,
      { method: 'GET', notifyOnGatewayError: true },
    ),

  previewPullFromPayables: async (payableIds: number[]) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-payables/pull-preview?payable_ids=${payableIds.join(',')}`,
      { method: 'GET', notifyOnGatewayError: true },
    ),
};
