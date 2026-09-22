import type { OutsourceReceiptLine } from '../components/OutsourceReceiptFormContent';

export type OutsourceReceiptQtyField =
  | 'receiptQuantity'
  | 'qualifiedQuantity'
  | 'unqualifiedQuantity'
  | 'processWasteQty'
  | 'materialWasteQty';

function roundQty(value: number, decimals: number): number {
  return Number(value.toFixed(decimals));
}

function capWasteToUnqualified(
  processWaste: number,
  materialWaste: number,
  unqualified: number,
): { processWaste: number; materialWaste: number } {
  let process = Math.max(0, processWaste);
  let material = Math.max(0, materialWaste);
  if (process + material <= unqualified) {
    return { processWaste: process, materialWaste: material };
  }
  process = Math.min(process, unqualified);
  material = Math.min(material, Math.max(0, unqualified - process));
  return { processWaste: process, materialWaste: material };
}

/**
 * 委外收货明细数量联动：
 * - 本次收货为总量真源；合格 + 不合格 = 本次收货
 * - 改合格/不合格/工废/料废时不改写本次收货
 * - 填写工废/料废时，不合格 = 工废 + 料废，合格 = 本次收货 - 不合格
 */
export function applyOutsourceReceiptQuantityChange(
  line: OutsourceReceiptLine,
  field: OutsourceReceiptQtyField,
  rawValue: number,
  quantityDecimals: number,
): OutsourceReceiptLine {
  const pending = Math.max(0, Number(line.pendingQuantity || 0));
  let receipt = Math.max(0, Number(line.receiptQuantity || 0));
  let qualified = Math.max(0, Number(line.qualifiedQuantity || 0));
  let unqualified = Math.max(0, Number(line.unqualifiedQuantity || 0));
  let processWaste = Math.max(0, Number(line.processWasteQty || 0));
  let materialWaste = Math.max(0, Number(line.materialWasteQty || 0));
  const value = Math.max(0, Number(rawValue || 0));

  switch (field) {
    case 'receiptQuantity': {
      receipt = pending > 0 ? Math.min(value, pending) : value;
      unqualified = Math.min(unqualified, receipt);
      qualified = Math.max(0, receipt - unqualified);
      const capped = capWasteToUnqualified(processWaste, materialWaste, unqualified);
      processWaste = capped.processWaste;
      materialWaste = capped.materialWaste;
      break;
    }
    case 'qualifiedQuantity': {
      qualified = Math.min(value, receipt);
      unqualified = Math.max(0, receipt - qualified);
      const capped = capWasteToUnqualified(processWaste, materialWaste, unqualified);
      processWaste = capped.processWaste;
      materialWaste = capped.materialWaste;
      break;
    }
    case 'unqualifiedQuantity': {
      unqualified = Math.min(value, receipt);
      qualified = Math.max(0, receipt - unqualified);
      const capped = capWasteToUnqualified(processWaste, materialWaste, unqualified);
      processWaste = capped.processWaste;
      materialWaste = capped.materialWaste;
      break;
    }
    case 'processWasteQty': {
      processWaste = value;
      unqualified = processWaste + materialWaste;
      if (unqualified > receipt) {
        materialWaste = Math.max(0, receipt - processWaste);
        unqualified = processWaste + materialWaste;
      }
      qualified = Math.max(0, receipt - unqualified);
      break;
    }
    case 'materialWasteQty': {
      materialWaste = value;
      unqualified = processWaste + materialWaste;
      if (unqualified > receipt) {
        processWaste = Math.max(0, receipt - materialWaste);
        unqualified = processWaste + materialWaste;
      }
      qualified = Math.max(0, receipt - unqualified);
      break;
    }
    default:
      break;
  }

  return {
    ...line,
    receiptQuantity: roundQty(receipt, quantityDecimals),
    qualifiedQuantity: roundQty(qualified, quantityDecimals),
    unqualifiedQuantity: roundQty(unqualified, quantityDecimals),
    processWasteQty: roundQty(processWaste, quantityDecimals),
    materialWasteQty: roundQty(materialWaste, quantityDecimals),
  };
}

export function isOutsourceReceiptQuantityBalanced(line: OutsourceReceiptLine, epsilon = 1e-9): boolean {
  const receipt = Number(line.receiptQuantity || 0);
  const qualified = Number(line.qualifiedQuantity || 0);
  const unqualified = Number(line.unqualifiedQuantity || 0);
  return Math.abs(qualified + unqualified - receipt) <= epsilon;
}
