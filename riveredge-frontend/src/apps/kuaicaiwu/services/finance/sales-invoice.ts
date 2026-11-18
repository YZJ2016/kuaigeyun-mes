import { apiRequest } from '../../../../services/api';
import type { FinancePullCandidateListParams } from './financePullListParams';
import type { DocumentPushPreview } from '../../../kuaizhizao/services/purchase-requisition';
import type { SalesInvoice, SalesInvoiceListParams } from '../../types/finance/sales-invoice';

export type { SalesInvoice, SalesInvoiceListParams };

export type SalesInvoicePullPreview = DocumentPushPreview & {
  source_code?: string;
  source_type?: 'sales_order' | 'sales_delivery' | 'receivable';
  customer_id?: number;
  customer_name?: string;
  sales_order_id?: number | null;
  sales_order_code?: string | null;
  receivable_id?: number;
  receivable_code?: string;
  price_type?: 'tax_inclusive' | 'tax_exclusive' | string;
  /** 同时收款上限（应收剩余可收） */
  remaining_settle_amount?: number;
  max_push_total?: number;
};

export type SalesInvoicePullCandidate = {
  id: number;
  code: string;
  doc_code?: string;
  order_code?: string;
  delivery_code?: string;
  receivable_code?: string;
  statement_code?: string;
  customer_name?: string;
  customer_id?: number;
  source_status?: string;
  source_date?: string;
  amount?: number;
  closing_balance?: number;
  invoiceable_amount?: number;
  invoiced_amount?: number;
  delivery_ids?: number[];
  receivable_ids?: number[];
  ledger_posting_mode?: 'immediate' | 'by_invoice' | string;
  capabilities?: { pull_sales_invoice?: { allowed?: boolean; reason?: string } };
};

export const salesInvoiceService = {
  list: (params: SalesInvoiceListParams) =>
    apiRequest<{ items: SalesInvoice[]; total: number }>('/apps/kuaicaiwu/sales-invoices', {
      method: 'GET',
      params,
    }),

  listSalesOrderPullCandidates: async (params?: FinancePullCandidateListParams) =>
    apiRequest<{ data: SalesInvoicePullCandidate[]; total: number; success: boolean }>(
      '/apps/kuaicaiwu/sales-invoices/pull-candidates/sales-orders',
      { method: 'GET', params },
    ),
  listSalesDeliveryPullCandidates: async (params?: FinancePullCandidateListParams) =>
    apiRequest<{ data: SalesInvoicePullCandidate[]; total: number; success: boolean }>(
      '/apps/kuaicaiwu/sales-invoices/pull-candidates/sales-deliveries',
      { method: 'GET', params },
    ),
  previewPullFromSalesOrder: async (orderId: number) =>
    apiRequest<SalesInvoicePullPreview>(`/apps/kuaicaiwu/sales-invoices/from-sales-order/${orderId}/pull-preview`, {
      method: 'GET',
      notifyOnGatewayError: true,
      timeoutMs: 60_000,
    }),
  previewPullFromSalesDelivery: async (deliveryId: number) =>
    apiRequest<SalesInvoicePullPreview>(
      `/apps/kuaicaiwu/sales-invoices/from-sales-delivery/${deliveryId}/pull-preview`,
      { method: 'GET', notifyOnGatewayError: true, timeoutMs: 60_000 },
    ),
  listReceivablePullCandidates: async (params?: FinancePullCandidateListParams) =>
    apiRequest<{ data: SalesInvoicePullCandidate[]; total: number; success: boolean }>(
      '/apps/kuaicaiwu/sales-invoices/pull-candidates/receivables',
      { method: 'GET', params },
    ),
  listPartnerStatementPullCandidates: async (params?: FinancePullCandidateListParams) =>
    apiRequest<{ data: SalesInvoicePullCandidate[]; total: number; success: boolean }>(
      '/apps/kuaicaiwu/sales-invoices/pull-candidates/partner-statements',
      { method: 'GET', params },
    ),
  previewPullFromReceivable: async (receivableId: number) =>
    apiRequest<SalesInvoicePullPreview>(
      `/apps/kuaicaiwu/sales-invoices/from-receivable/${receivableId}/pull-preview`,
      { method: 'GET', notifyOnGatewayError: true, timeoutMs: 60_000 },
    ),
};
