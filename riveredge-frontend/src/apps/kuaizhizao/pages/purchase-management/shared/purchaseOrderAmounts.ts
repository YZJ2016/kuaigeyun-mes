/**
 * 采购订单金额展示：库内 unit_price / total_amount 为未税；
 * 列表/详情「订单金额」应对齐价税合计（net_amount）。
 */
import { calcDocumentLineAmounts } from '../../../utils/documentLineAmounts';

/** 头表 tax_rate 存小数（0.13），表单与详情展示用百分比 */
export function purchaseOrderTaxRateToPercent(raw: unknown): number {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return n <= 1 ? n * 100 : n;
}

export function purchaseOrderTaxRateToDecimal(percent: unknown): number {
  const n = Number(percent);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return n / 100;
}

/** 采购入库单列表/取单金额：与后端 settlement_gross / purchase_receipt_settlement_gross 同源 */
export function resolvePurchaseReceiptDisplayAmount(receipt: {
  settlement_gross?: number | null;
  settlementGross?: number | null;
  net_amount?: number | null;
  netAmount?: number | null;
  total_amount?: number | null;
  totalAmount?: number | null;
  tax_amount?: number | null;
  taxAmount?: number | null;
  tax_rate?: number | null;
  taxRate?: number | null;
}): number {
  const settlement = Number(receipt.settlement_gross ?? receipt.settlementGross);
  if (Number.isFinite(settlement) && settlement > 0) return settlement;

  const net = Number(receipt.net_amount ?? receipt.netAmount);
  if (Number.isFinite(net) && net > 0) return net;

  const excl = Number(receipt.total_amount ?? receipt.totalAmount) || 0;
  const tax = Number(receipt.tax_amount ?? receipt.taxAmount);
  if (Number.isFinite(tax) && tax >= 0 && (excl > 0 || tax > 0)) {
    return excl + tax;
  }
  const pct = purchaseOrderTaxRateToPercent(receipt.tax_rate ?? receipt.taxRate);
  if (excl > 0 || pct > 0) {
    return calcDocumentLineAmountsFromExclTotal(excl, pct).incl;
  }
  return calcDocumentLineAmounts(1, excl, pct, 'tax_exclusive').incl;
}

/** 列表/详情订单金额：优先头表税额汇总（支持行级多税率），再回退单税率重算 */
/** 列表/详情订单金额：优先 net_amount（价税合计） */
export function resolvePurchaseOrderDisplayAmount(order: {
  net_amount?: number | null;
  total_amount?: number | null;
  tax_amount?: number | null;
  tax_rate?: number | null;
}): number {
  const excl = Number(order.total_amount) || 0;
  const tax = Number(order.tax_amount);
  if (Number.isFinite(tax) && tax >= 0 && (excl > 0 || tax > 0)) {
    return excl + tax;
  }
  const net = Number(order.net_amount);
  if (Number.isFinite(net) && net > 0) return net;
  const pct = purchaseOrderTaxRateToPercent(order.tax_rate);
  if (excl > 0 || pct > 0) {
    return calcDocumentLineAmountsFromExclTotal(excl, pct).incl;
  }
  return calcDocumentLineAmounts(1, excl, pct, 'tax_exclusive').incl;
}

/** 编辑回填：库内未税单价 → 含税表单单价 */
export function purchaseOrderStoredUnitPriceToForm(
  storedUnitPrice: number,
  taxRatePercent: number,
  priceType: 'tax_inclusive' | 'tax_exclusive',
): number {
  if (!(storedUnitPrice > 0)) return storedUnitPrice || 0;
  if (priceType !== 'tax_inclusive' || !(taxRatePercent > 0)) return storedUnitPrice;
  return calcDocumentLineAmounts(1, storedUnitPrice, taxRatePercent, 'tax_exclusive').incl;
}
