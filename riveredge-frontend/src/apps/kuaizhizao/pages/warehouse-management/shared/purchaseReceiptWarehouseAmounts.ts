/**
 * 采购入库（仓储 Hub）价税只读：与后端 compute_purchase_receipt_line_settlement_amounts 同源计算，
 * 禁止用未税×税率或仅读错落的 settlement_* 充当展示真源。
 */
import {
  computePurchaseReceiptLineSettlementAmounts,
  type PurchaseReceiptLineSettlementInput,
  resolvePurchaseReceiptLineTaxPercent,
} from '../../purchase-management/shared/purchaseOrderAmounts';

export type PurchaseReceiptLineAmountRow = PurchaseReceiptLineSettlementInput & {
  tax_amount?: number | null;
  net_amount?: number | null;
  settlementExcl?: number | null;
  settlementTax?: number | null;
  settlementGross?: number | null;
};

function pickLineNumber(...candidates: unknown[]): number | null {
  for (const raw of candidates) {
    if (raw == null) continue;
    const n = Number(raw);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

/** 行未税/税额/价税：有数量与录入单价时走 calcDocumentLineAmounts，否则返回 null */
export function readPurchaseReceiptDetailLineAmounts(
  row: PurchaseReceiptLineAmountRow,
  headerTaxRate?: number | null,
  priceType = 'tax_inclusive',
): { excl: number; tax: number; incl: number; taxPct: number } | null {
  const qty = Number(row.receipt_quantity) || 0;
  const hasDisplay =
    pickLineNumber(row.display_unit_price, row.displayUnitPrice) != null &&
    Number(row.display_unit_price ?? row.displayUnitPrice) > 0;
  const hasUnit = pickLineNumber(row.unit_price) != null && Number(row.unit_price) > 0;
  if (qty > 0 && (hasDisplay || hasUnit)) {
    return computePurchaseReceiptLineSettlementAmounts(
      row,
      headerTaxRate,
      priceType,
      null,
    );
  }
  const taxPct = resolvePurchaseReceiptLineTaxPercent(row.tax_rate, headerTaxRate);
  return { excl: 0, tax: 0, incl: 0, taxPct };
}

export function readPurchaseReceiptHeaderInclAmount(receipt: {
  settlement_gross?: number | null;
  settlementGross?: number | null;
  net_amount?: number | null;
  netAmount?: number | null;
  total_amount?: number | null;
  tax_amount?: number | null;
  items?: PurchaseReceiptLineAmountRow[];
  lines?: PurchaseReceiptLineAmountRow[];
  header_tax_rate?: number | null;
  tax_rate?: number | null;
  price_type?: string | null;
}): number | null {
  const lines = (receipt.items ?? receipt.lines ?? []) as PurchaseReceiptLineAmountRow[];
  if (lines.length > 0) {
    let incl = 0;
    const headerTax = receipt.header_tax_rate ?? receipt.tax_rate;
    const priceType = String(receipt.price_type ?? 'tax_inclusive');
    for (const line of lines) {
      const amounts = readPurchaseReceiptDetailLineAmounts(line, headerTax, priceType);
      if (amounts != null) incl += amounts.incl;
    }
    if (incl > 0) return incl;
  }
  const settlement = pickLineNumber(receipt.settlement_gross, receipt.settlementGross);
  if (settlement != null) return settlement;
  return pickLineNumber(receipt.net_amount, receipt.netAmount);
}

export function readPurchaseReceiptFormUnitPrice(line: Record<string, unknown>): number {
  const display = line.display_unit_price ?? line.displayUnitPrice;
  if (display != null && Number(display) > 0) return Number(display);
  return Number(line.unit_price) || 0;
}