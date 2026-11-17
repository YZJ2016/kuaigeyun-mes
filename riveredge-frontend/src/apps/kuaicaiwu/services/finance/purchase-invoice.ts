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
  material_code: string;
  material_name: string;
  material_spec?: string | null;
  unit: string;
  quantity: number;
  unit_price: number;
  amount: number;
};

export type PurchaseInvoicePullPreview = DocumentPushPreview & {
  source_code?: string;
  source_type?: 'purchase_order' | 'purchase_receipt' | 'payable';
  supplier_id?: number;
  supplier_name?: string;
  purchase_order_id?: number | null;
  purchase_order_code?: string | null;
  payable_id?: number;
  payable_code?: string;
  /** 同时付款上限（应付剩余可付） */
  remaining_settle_amount?: number;
  /** 多源合并加载时的源单ID列表与可开票合计 */
  source_ids?: number[];
  max_push_total?: number;
  /** 源单物料明细，便于确认本次开票对应内容 */
  detail_lines?: PurchaseInvoicePullDetailLine[];
};

export type PurchaseInvoicePullCandidate = {
  id: number;
  code: string;
  order_code?: string;
  receipt_code?: string;
  supplier_name?: string;
  source_status?: string;
  source_date?: string;
  amount?: number;
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
      { method: 'GET', params },
    ),

  previewPullFromPurchaseOrder: async (orderId: number) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-purchase-order/${orderId}/pull-preview`,
      { method: 'GET', notifyOnGatewayError: true },
    ),

  previewPullFromPurchaseOrders: async (orderIds: number[]) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-purchase-orders/pull-preview?order_ids=${orderIds.join(',')}`,
      { method: 'GET', notifyOnGatewayError: true },
    ),

  previewPullFromPurchaseReceipt: async (receiptId: number) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-purchase-receipt/${receiptId}/pull-preview`,
      { method: 'GET', notifyOnGatewayError: true },
    ),

  previewPullFromPurchaseReceipts: async (receiptIds: number[]) =>
    apiRequest<PurchaseInvoicePullPreview>(
      `${PURCHASE_INVOICE_API}/from-purchase-receipts/pull-preview?receipt_ids=${receiptIds.join(',')}`,
      { method: 'GET', notifyOnGatewayError: true },
    ),

  listPayablePullCandidates: async (params?: FinancePullCandidateListParams) =>
    apiRequest<{ data: PurchaseInvoicePullCandidate[]; total: number; success: boolean }>(
      `${PURCHASE_INVOICE_API}/pull-candidates/payables`,
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
