import { describe, expect, it } from 'vitest';
import {
  calcDocumentLineAmounts,
  documentLineExclMatchesDerived,
  documentLineInclMatchesDerived,
  syncFormListLineItemAmountAfterQuantityChange,
} from './documentLineAmounts';

describe('documentLine derive guards', () => {
  it('excl matches derived for tax_inclusive unit 600 qty 1', () => {
    const line = calcDocumentLineAmounts(1, 600, 13, 'tax_inclusive');
    expect(
      documentLineExclMatchesDerived(line.excl, 1, 600, 13, 'tax_inclusive'),
    ).toBe(true);
    expect(
      documentLineInclMatchesDerived(
        line.incl,
        { qty: 1, unit_price: 600, tax_rate: 13 },
        'tax_inclusive',
      ),
    ).toBe(true);
  });

  it('incl does not match when user changed total', () => {
    expect(
      documentLineInclMatchesDerived(
        601,
        { qty: 1, unit_price: 600, tax_rate: 13 },
        'tax_inclusive',
      ),
    ).toBe(false);
  });

  it('syncs stale item_amount when primary qty changes', () => {
    let items = [
      {
        quote_quantity: 2,
        unit_price: 6,
        tax_rate: 13,
        item_amount: 6,
      },
    ];
    const form = {
      getFieldValue: (name: string | (string | number)[]) => {
        if (name === 'items' || (Array.isArray(name) && name[0] === 'items')) return items;
        if (name === 'price_type') return 'tax_inclusive';
        return undefined;
      },
      setFieldsValue: (values: Record<string, unknown>) => {
        if (Array.isArray(values.items)) items = values.items as typeof items;
      },
    };
    expect(
      syncFormListLineItemAmountAfterQuantityChange(form, 0, 'quote_quantity', 2),
    ).toBe(true);
    expect(items[0].item_amount).toBe(12);
  });
});
