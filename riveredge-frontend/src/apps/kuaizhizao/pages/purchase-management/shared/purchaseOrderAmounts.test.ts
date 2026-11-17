import { describe, expect, it } from 'vitest';
import {
  computePurchaseReceiptFormLineAmounts,
  computePurchaseOrderHeaderAmountsForSave,
  computePurchaseReceiptFormLineAmounts,
  purchaseOrderFormLineToStored,
  readPurchaseOrderEnteredUnitPrice,
  resolvePurchaseOrderDisplayAmount,
} from './purchaseOrderAmounts';

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
      { receipt_quantity: 1, unit_price: 60, tax_rate: 13 },
      13,
      'tax_inclusive',
      null,
    );
    expect(line.incl).toBe(60);
    expect(line.excl).toBeCloseTo(53.1, 2);
    expect(line.tax).toBeCloseTo(6.9, 2);
  });

  it('purchase receipt PO line uses proportional gross not qty×rate tail', () => {
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
      },
      0.13,
      'tax_exclusive',
      poCtx,
    );
    expect(line.excl).toBe(8849.56);
    expect(line.incl).toBe(10000);
  });
});
