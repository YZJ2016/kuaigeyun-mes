import { describe, expect, it } from 'vitest';
import {
  computePurchaseOrderHeaderAmountsForSave,
  computePurchaseReceiptFormLineAmounts,
  purchaseOrderFormLineToStored,
  purchaseOrderTaxRateToPercent,
  readPurchaseOrderEnteredUnitPrice,
  resolvePurchaseOrderDisplayAmount,
  resolvePurchaseOrderLineAmounts,
} from './purchaseOrderAmounts';

describe('purchaseOrderTaxRateToPercent', () => {
  it('keeps percent 1 as 1% and converts header decimal 0.01 to 1', () => {
    expect(purchaseOrderTaxRateToPercent(1)).toBe(1);
    expect(purchaseOrderTaxRateToPercent(0.01)).toBe(1);
    expect(purchaseOrderTaxRateToPercent(0.13)).toBe(13);
    expect(purchaseOrderTaxRateToPercent(13)).toBe(13);
  });

  it('1% exclusive line tax is 1% of excl not 100%', () => {
    const line = resolvePurchaseOrderLineAmounts(
      { ordered_quantity: 1, unit_price: 100, tax_rate: 1 },
      'tax_exclusive',
    );
    expect(line.taxPct).toBe(1);
    expect(line.excl).toBe(100);
    expect(line.tax).toBe(1);
    expect(line.incl).toBe(101);
  });
});

describe('purchaseOrderAmounts unified with documentLineAmounts', () => {
  it('tax_inclusive unit 800 qty 1: header net equals form goodsIncl', () => {
    const stored = purchaseOrderFormLineToStored(800, 1, 13, 'tax_inclusive', 2);
    expect(stored.incl).toBe(800);
    const header = computePurchaseOrderHeaderAmountsForSave(
      [{ ordered_quantity: 1, unit_price: 800, tax_rate: 13 }],
      'tax_inclusive',
    );
    expect(header.net_amount).toBe(800);
    expect(resolvePurchaseOrderDisplayAmount({ net_amount: header.net_amount })).toBe(800);
  });

  it('tax_inclusive unit 600 reloads the entered price', () => {
    const stored = purchaseOrderFormLineToStored(600, 1, 13, 'tax_inclusive', 4);
    expect(stored.display_unit_price).toBe(600);
    expect(stored.incl).toBe(600);
    expect(
      readPurchaseOrderEnteredUnitPrice(
        {
          display_unit_price: stored.display_unit_price,
          unit_price: stored.unit_price,
        },
        'tax_inclusive',
      ),
    ).toBe(600);
  });

  it('legacy inclusive line without display price is not rebuilt from exclusive unit', () => {
    expect(
      readPurchaseOrderEnteredUnitPrice({ unit_price: 530.9735 }, 'tax_inclusive'),
    ).toBeNull();
  });

  it('purchase receipt standalone line tax_inclusive matches purchase order logic', () => {
    const line = computePurchaseReceiptFormLineAmounts(
      { receipt_quantity: 1, display_unit_price: 60, unit_price: 53.1, tax_rate: 13 },
      13,
      'tax_inclusive',
      null,
    );
    expect(line.incl).toBe(60);
    expect(line.excl).toBeCloseTo(53.1, 2);
    expect(line.tax).toBeCloseTo(6.9, 2);
  });

  it('purchase receipt API row uses display_unit_price not stored excl unit', () => {
    const line = computePurchaseReceiptFormLineAmounts(
      {
        receipt_quantity: 2,
        display_unit_price: 55,
        unit_price: 48.6725,
        tax_rate: 13,
      },
      13,
      'tax_inclusive',
      null,
    );
    expect(line.incl).toBe(110);
    expect(line.excl).toBeCloseTo(97.35, 2);
    expect(line.tax).toBeCloseTo(12.65, 2);
  });

  it('purchase receipt PO tax_inclusive uses display price for gross not excl total_price', () => {
    const poCtx = {
      priceType: 'tax_inclusive' as const,
      headerTaxRate: 13,
      poiById: {
        101: {
          ordered_quantity: 2,
          total_price: 97.35,
          unit_price: 48.6725,
          display_unit_price: 55,
          tax_rate: 13,
        },
      },
    };
    const line = computePurchaseReceiptFormLineAmounts(
      {
        receipt_quantity: 2,
        display_unit_price: 55,
        unit_price: 48.6725,
        tax_rate: 13,
        purchase_order_item_id: 101,
      },
      13,
      'tax_inclusive',
      poCtx,
    );
    expect(line.excl).toBeCloseTo(97.35, 2);
    expect(line.incl).toBe(110);
    expect(line.tax).toBeCloseTo(12.65, 2);
  });

  it('purchase receipt uses qty times entered price even when PO total differs by a cent', () => {
    const poCtx = {
      priceType: 'tax_exclusive' as const,
      headerTaxRate: 0.13,
      poiById: {
        101: {
          ordered_quantity: 1000,
          total_price: 8849.56,
          unit_price: 8.84956,
          tax_rate: 13,
        },
      },
    };
    const line = computePurchaseReceiptFormLineAmounts(
      {
        receipt_quantity: 1000,
        unit_price: 8.8496,
        tax_rate: 13,
        purchase_order_item_id: 101,
        total_amount: 8849.56,
      },
      0.13,
      'tax_exclusive',
      poCtx,
    );
    expect(line.excl).toBe(8849.6);
    expect(line.incl).toBe(10000.05);
    expect(line.tax).toBe(1150.45);
  });
});
