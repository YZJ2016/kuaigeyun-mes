/** 采购入库编辑表单读取录入单价。头表价税合计不在此计算。 */

export function readPurchaseReceiptFormUnitPrice(line: Record<string, unknown>): number {
  const display = line.display_unit_price ?? line.displayUnitPrice;
  if (display != null && Number(display) > 0) return Number(display);
  return Number(line.unit_price) || 0;
}
