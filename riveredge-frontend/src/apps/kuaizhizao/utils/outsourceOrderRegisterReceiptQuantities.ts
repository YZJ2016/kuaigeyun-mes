import type { OutsourceReceiptLine } from '../components/OutsourceReceiptFormContent';
import { applyOutsourceReceiptQuantityChange, isOutsourceReceiptQuantityBalanced } from './outsourceReceiptLineQuantities';

export type OutsourceRegisterReceiptFormQty = {
  received_quantity: number;
  qualified_quantity: number;
  unqualified_quantity: number;
};

export type OutsourceRegisterReceiptQtyField = keyof OutsourceRegisterReceiptFormQty;

function emptyReceiptLine(pendingQuantity: number, values: OutsourceRegisterReceiptFormQty): OutsourceReceiptLine {
  return {
    key: 0,
    productCode: '',
    productName: '',
    unit: '',
    orderedQuantity: 0,
    receivedQuantity: 0,
    pendingQuantity,
    receiptQuantity: Number(values.received_quantity ?? 0),
    qualifiedQuantity: Number(values.qualified_quantity ?? 0),
    unqualifiedQuantity: Number(values.unqualified_quantity ?? 0),
  };
}

const FIELD_TO_LINE: Record<
  OutsourceRegisterReceiptQtyField,
  'receiptQuantity' | 'qualifiedQuantity' | 'unqualifiedQuantity'
> = {
  received_quantity: 'receiptQuantity',
  qualified_quantity: 'qualifiedQuantity',
  unqualified_quantity: 'unqualifiedQuantity',
};

function roundQty(value: number, decimals: number): number {
  return Number(value.toFixed(decimals));
}

/** 登记委外收货弹窗：不合格 = 本批完成数量 − 合格数量（不可手改）。 */
export function applyOutsourceRegisterReceiptQuantityChange(
  pendingQuantity: number,
  current: OutsourceRegisterReceiptFormQty,
  field: OutsourceRegisterReceiptQtyField,
  rawValue: number,
  quantityDecimals: number,
): OutsourceRegisterReceiptFormQty {
  if (field === 'unqualified_quantity') {
    const recv = Number(current.received_quantity ?? 0);
    const qual = Number(current.qualified_quantity ?? 0);
    return {
      received_quantity: recv,
      qualified_quantity: qual,
      unqualified_quantity: roundQty(Math.max(0, recv - qual), quantityDecimals),
    };
  }
  const line = applyOutsourceReceiptQuantityChange(
    emptyReceiptLine(pendingQuantity, current),
    FIELD_TO_LINE[field],
    rawValue,
    quantityDecimals,
  );
  const recv = line.receiptQuantity;
  const qual = Math.min(line.qualifiedQuantity, recv);
  return {
    received_quantity: recv,
    qualified_quantity: qual,
    unqualified_quantity: roundQty(Math.max(0, recv - qual), quantityDecimals),
  };
}

export function isOutsourceRegisterReceiptQuantityBalanced(values: OutsourceRegisterReceiptFormQty): boolean {
  return isOutsourceReceiptQuantityBalanced({
    key: 0,
    productCode: '',
    productName: '',
    unit: '',
    orderedQuantity: 0,
    receivedQuantity: 0,
    pendingQuantity: 0,
    receiptQuantity: Number(values.received_quantity ?? 0),
    qualifiedQuantity: Number(values.qualified_quantity ?? 0),
    unqualifiedQuantity: Number(values.unqualified_quantity ?? 0),
  });
}