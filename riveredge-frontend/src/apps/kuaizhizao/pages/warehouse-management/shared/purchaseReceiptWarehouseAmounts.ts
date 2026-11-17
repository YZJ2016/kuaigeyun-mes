/**
 * 采购入库（仓储 Hub）价税只读：仅认库内/接口已落库字段，禁止税率反算。
 */
import { resolvePurchaseReceiptLineTaxPercent } from '../../purchase-management/shared/purchaseOrderAmounts';

export type PurchaseReceiptLineAmountRow = {
  total_amount?: number | null;
  tax_amount?: number | null;
  net_amount?: number | null;
  tax_rate?: number | null;
  settlement_excl?: number | null;
  settlementExcl?: number | null;
  settlement_tax?: number | null;
  settlementTax?: number | null;
  settlement_gross?: number | null;
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

/** 行未税/税额/价税：须有三项真源之一（库字段或 settlement_*），否则返回 null 由 UI 显示 — */
export function readPurchaseReceiptDetailLineAmounts(
  row: PurchaseReceiptLineAmountRow,
  headerTaxRate?: number | null,
): { excl: number; tax: number; incl: number; taxPct: number } | null {
  const excl = pickLineNumber(
    row.settlement_excl,
    row.settlementExcl,
    row.total_amount,
  );
  const tax = pickLineNumber(row.settlement_tax, row.settlementTax, row.tax_amount);
  const incl = pickLineNumber(row.settlement_gross, row.settlementGross, row.net_amount);
  if (excl == null || tax == null || incl == null) return null;
  const taxPct = resolvePurchaseReceiptLineTaxPercent(row.tax_rate, headerTaxRate);
  return { excl, tax, incl, taxPct };
}

export function readPurchaseReceiptHeaderInclAmount(receipt: {
  settlement_gross?: number | null;
  settlementGross?: number | null;
  net_amount?: number | null;
  netAmount?: number | null;
}): number | null {
  const settlement = pickLineNumber(receipt.settlement_gross, receipt.settlementGross);
  if (settlement != null) return settlement;
  return pickLineNumber(receipt.net_amount, receipt.netAmount);
}

export function readPurchaseReceiptFormUnitPrice(line: Record<string, unknown>): number {
  const display = line.display_unit_price ?? line.displayUnitPrice;
  if (display != null && Number(display) > 0) return Number(display);
  return Number(line.unit_price) || 0;
}
