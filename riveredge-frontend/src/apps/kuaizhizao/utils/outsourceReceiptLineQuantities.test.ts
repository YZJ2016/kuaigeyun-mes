import { describe, expect, it } from 'vitest';

import type { OutsourceReceiptLine } from '../components/OutsourceReceiptFormContent';
import {
  applyOutsourceReceiptQuantityChange,
  isOutsourceReceiptQuantityBalanced,
} from './outsourceReceiptLineQuantities';

function baseLine(overrides: Partial<OutsourceReceiptLine> = {}): OutsourceReceiptLine {
  return {
    key: 1,
    productCode: 'P001',
    productName: '产品',
    unit: '件',
    orderedQuantity: 100,
    receivedQuantity: 0,
    pendingQuantity: 100,
    receiptQuantity: 100,
    qualifiedQuantity: 100,
    unqualifiedQuantity: 0,
    processWasteQty: 0,
    materialWasteQty: 0,
    ...overrides,
  };
}

describe('applyOutsourceReceiptQuantityChange', () => {
  it('keeps receipt when qualified changes', () => {
    const line = applyOutsourceReceiptQuantityChange(
      baseLine({ receiptQuantity: 18, qualifiedQuantity: 18, unqualifiedQuantity: 0 }),
      'qualifiedQuantity',
      8,
      2,
    );
    expect(line.receiptQuantity).toBe(18);
    expect(line.qualifiedQuantity).toBe(8);
    expect(line.unqualifiedQuantity).toBe(10);
  });

  it('keeps receipt when unqualified changes', () => {
    const line = applyOutsourceReceiptQuantityChange(
      baseLine({ receiptQuantity: 18, qualifiedQuantity: 18, unqualifiedQuantity: 0 }),
      'unqualifiedQuantity',
      10,
      2,
    );
    expect(line.receiptQuantity).toBe(18);
    expect(line.qualifiedQuantity).toBe(8);
    expect(line.unqualifiedQuantity).toBe(10);
  });

  it('syncs waste breakdown into unqualified without changing receipt', () => {
    const line = applyOutsourceReceiptQuantityChange(
      applyOutsourceReceiptQuantityChange(
        baseLine({ receiptQuantity: 18, qualifiedQuantity: 18, unqualifiedQuantity: 0 }),
        'qualifiedQuantity',
        8,
        2,
      ),
      'processWasteQty',
      5,
      2,
    );
    const finalLine = applyOutsourceReceiptQuantityChange(line, 'materialWasteQty', 5, 2);
    expect(finalLine.receiptQuantity).toBe(18);
    expect(finalLine.qualifiedQuantity).toBe(8);
    expect(finalLine.unqualifiedQuantity).toBe(10);
    expect(finalLine.processWasteQty).toBe(5);
    expect(finalLine.materialWasteQty).toBe(5);
  });

  it('caps receipt by pending quantity', () => {
    const line = applyOutsourceReceiptQuantityChange(baseLine(), 'receiptQuantity', 120, 2);
    expect(line.receiptQuantity).toBe(100);
    expect(line.qualifiedQuantity).toBe(100);
  });
});

describe('isOutsourceReceiptQuantityBalanced', () => {
  it('detects balanced quantities', () => {
    expect(
      isOutsourceReceiptQuantityBalanced(
        baseLine({ receiptQuantity: 18, qualifiedQuantity: 8, unqualifiedQuantity: 10 }),
      ),
    ).toBe(true);
  });
});
