import { describe, expect, it } from 'vitest';
import {
  calcDocumentLineAmounts,
  documentLineExclMatchesDerived,
  documentLineInclMatchesDerived,
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
});
