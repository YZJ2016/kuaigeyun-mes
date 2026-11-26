import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../hooks/useNumericPrecision', () => ({
  getCachedNumericPrecisionPlaces: vi.fn(() => 4),
}));

import {
  convertUnitPriceByPriceType,
  formUnitPriceFromExclusiveBook,
  toFormUnitPriceFromExclusive,
} from './resolve-partner-material-price';
import { getCachedNumericPrecisionPlaces } from '../../../hooks/useNumericPrecision';

describe('toFormUnitPriceFromExclusive', () => {
  beforeEach(() => {
    vi.mocked(getCachedNumericPrecisionPlaces).mockReturnValue(4);
  });

  it('未税乘回含税后按单价小数位量化（0.389381@13% 不得显示 0.440001）', () => {
    const exclusive = 0.389381;
    expect(convertUnitPriceByPriceType(exclusive, 13, 'tax_exclusive', 'tax_inclusive')).toBe(0.440001);
    expect(toFormUnitPriceFromExclusive(exclusive, 'tax_inclusive', 13)).toBe(0.44);
  });
});

describe('convertUnitPriceByPriceType', () => {
  it('含税 800 @13% 剥未税再乘回仍为 800（禁止分位中间舍入变成 799.99）', () => {
    const exclusive = convertUnitPriceByPriceType(800, 13, 'tax_inclusive', 'tax_exclusive');
    const back = convertUnitPriceByPriceType(exclusive, 13, 'tax_exclusive', 'tax_inclusive');
    expect(Math.round(back * 100) / 100).toBe(800);
    expect(toFormUnitPriceFromExclusive(exclusive, 'tax_inclusive', 13)).toBeCloseTo(800, 6);
  });
});

describe('formUnitPriceFromExclusiveBook', () => {
  it('价本无税率字段时含税表单仍按行税率乘回（0.57 @13% → 0.6441）', () => {
    expect(formUnitPriceFromExclusiveBook(0.57, 'tax_inclusive', null, 13, true)).toBeCloseTo(0.6441, 4);
  });

  it('非价本回落价禁止用行税率再乘（避免物料含税默认价双乘）', () => {
    expect(formUnitPriceFromExclusiveBook(800, 'tax_inclusive', null, 13, false)).toBe(800);
  });
});
