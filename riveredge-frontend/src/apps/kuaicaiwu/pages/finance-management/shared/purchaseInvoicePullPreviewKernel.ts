import {
  purchaseInvoiceService,
  type PurchaseInvoicePullPreview,
} from '../../../services/finance/purchase-invoice';

export type PurchaseInvoicePullPreviewKind =
  | 'purchase_order'
  | 'purchase_receipt'
  | 'payable'
  | 'outsource_order_receipt';

export function resolvePurchaseInvoicePullPreviewCap(
  data: PurchaseInvoicePullPreview | null | undefined,
): number {
  if (!data) return 0;
  const budget = Number(data.partner_statement_invoice_budget);
  if (budget > 0) return budget;
  const total = Number(data.max_push_total);
  if (total > 0) return total;
  return (
    (data.items || []).reduce((sum, row) => sum + Number(row.max_push_quantity ?? 0), 0) || 0
  );
}

export async function fetchPurchaseInvoicePullPreview(
  kind: PurchaseInvoicePullPreviewKind,
  sourceIds: number[],
  partnerStatementIds?: number[],
): Promise<PurchaseInvoicePullPreview> {
  return purchaseInvoiceService.previewPull({
    source_type: kind,
    source_ids: sourceIds,
    partner_statement_ids: partnerStatementIds,
  });
}

export async function fetchPurchaseInvoicePartnerStatementPullPreview(params: {
  receiptIds?: number[];
  outsourceOrderReceiptIds?: number[];
  partnerStatementIds: number[];
}): Promise<PurchaseInvoicePullPreview> {
  return purchaseInvoiceService.previewPullFromPartnerStatementSupplierSources(params);
}