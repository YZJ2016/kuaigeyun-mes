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

/** 列表/详情订单金额：优先 net_amount（价税合计） */
export function resolvePurchaseOrderDisplayAmount(order: {
  net_amount?: number | null;
  total_amount?: number | null;
  tax_amount?: number | null;
  tax_rate?: number | null;
}): number {
  const net = Number(order.net_amount);
  if (Number.isFinite(net) && net > 0) return net;
  const excl = Number(order.total_amount) || 0;
  const tax = Number(order.tax_amount);
  if (Number.isFinite(tax) && tax >= 0 && (excl > 0 || tax > 0)) return excl + tax;
  const pct = purchaseOrderTaxRateToPercent(order.tax_rate);
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
