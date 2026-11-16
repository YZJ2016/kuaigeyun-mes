import { describe, expect, it } from 'vitest';
import {
  computePurchaseOrderHeaderAmountsForSave,
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
});
