import {
  salesInvoiceService,
  type SalesInvoicePullPreview,
} from '../../../services/finance/sales-invoice';

export type SalesInvoicePullPreviewKind = 'sales_order' | 'sales_delivery' | 'receivable';

export function resolveSalesInvoicePullPreviewCap(
  data: SalesInvoicePullPreview | null | undefined,
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

export async function fetchSalesInvoicePullPreview(
  kind: SalesInvoicePullPreviewKind,
  sourceIds: number[],
  partnerStatementIds?: number[],
): Promise<SalesInvoicePullPreview> {
  return salesInvoiceService.previewPull({
    source_type: kind,
    source_ids: sourceIds,
    partner_statement_ids: partnerStatementIds,
  });
}