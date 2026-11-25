import type { MaterialUnit } from '../types/material';
import {
  CONVERSION_TYPE_FIXED,
  normalizeMaterialConversionType,
} from './materialConversionType';

function gcdInt(a: number, b: number): number {
  let x = Math.abs(Math.trunc(a));
  let y = Math.abs(Math.trunc(b));
  while (y !== 0) {
    const t = y;
    y = x % y;
    x = t;
  }
  return x || 1;
}

function decimalPlaces(n: number): number {
  if (!Number.isFinite(n)) return 0;
  const s = String(n);
  if (s.includes('e') || s.includes('E')) {
    const [mantissa, expPart] = s.toLowerCase().split('e');
    const exp = Number(expPart ?? 0);
    const frac = mantissa.includes('.') ? mantissa.split('.')[1].length : 0;
    return Math.max(0, frac - exp);
  }
  if (!s.includes('.')) return 0;
  return s.split('.')[1].replace(/0+$/, '').length;
}

function pickPositiveNumber(row: MaterialUnit, camel: keyof MaterialUnit, snake: string): number | undefined {
  const direct = row[camel];
  if (typeof direct === 'number' && direct > 0) return direct;
  const legacy = (row as Record<string, unknown>)[snake];
  if (typeof legacy === 'number' && legacy > 0) return legacy;
  return undefined;
}

/**
 * 将可能含小数的分子/分母转为正整数对（与后端 int 存储一致），例如 1/9.5 → 2/19。
 */
export function rationalizeMaterialConversionPair(
  numerator: number,
  denominator: number,
): { numerator: number; denominator: number } {
  if (
    !Number.isFinite(numerator) ||
    !Number.isFinite(denominator) ||
    numerator <= 0 ||
    denominator <= 0
  ) {
    return { numerator: 1, denominator: 1 };
  }
  const places = Math.min(Math.max(decimalPlaces(numerator), decimalPlaces(denominator)), 8);
  const scale = 10 ** places;
  let n = Math.round(numerator * scale);
  let d = Math.round(denominator * scale);
  const g = gcdInt(n, d);
  n = Math.trunc(n / g);
  d = Math.trunc(d / g);
  if (n <= 0) n = 1;
  if (d <= 0) d = 1;
  return { numerator: n, denominator: d };
}

/** 界面展示用分子/分母（优先用户保存的 numeratorInput / denominatorInput） */
export function resolveMaterialConversionDisplayPair(row: MaterialUnit): {
  numerator: number;
  denominator: number;
} {
  const numIn = pickPositiveNumber(row, 'numeratorInput', 'numerator_input');
  const denIn = pickPositiveNumber(row, 'denominatorInput', 'denominator_input');
  if (numIn != null && denIn != null) {
    return { numerator: numIn, denominator: denIn };
  }
  return {
    numerator: Number(row.numerator ?? 1),
    denominator: Number(row.denominator ?? 1),
  };
}

function shouldPersistConversionInput(displayNum: number, displayDen: number, intNum: number, intDen: number): boolean {
  return (
    displayNum !== intNum ||
    displayDen !== intDen ||
    !Number.isInteger(displayNum) ||
    !Number.isInteger(displayDen)
  );
}

/** 提交前：整数比写入 numerator/denominator，小数展示写入 *Input（可与约分结果不同） */
export function prepareMaterialUnitConversionForSubmit(row: MaterialUnit): MaterialUnit {
  if (normalizeMaterialConversionType(row.conversionType) !== CONVERSION_TYPE_FIXED) {
    const {
      numerator,
      denominator,
      numeratorInput,
      denominatorInput,
      ...rest
    } = row;
    return rest as MaterialUnit;
  }
  const display = resolveMaterialConversionDisplayPair(row);
  const { numerator, denominator } = rationalizeMaterialConversionPair(
    display.numerator,
    display.denominator,
  );
  const next: MaterialUnit = {
    ...row,
    numerator,
    denominator,
  };
  if (shouldPersistConversionInput(display.numerator, display.denominator, numerator, denominator)) {
    next.numeratorInput = display.numerator;
    next.denominatorInput = display.denominator;
  } else {
    delete next.numeratorInput;
    delete next.denominatorInput;
  }
  return next;
}

/** 编辑态：同步展示字段与整数比，不在失焦时改写用户输入 */
export function syncMaterialUnitConversionFromDisplay(
  row: MaterialUnit,
  displayNumerator: number,
  displayDenominator: number,
): MaterialUnit {
  const num = displayNumerator > 0 ? displayNumerator : 1;
  const den = displayDenominator > 0 ? displayDenominator : 1;
  const { numerator, denominator } = rationalizeMaterialConversionPair(num, den);
  const next: MaterialUnit = { ...row, numerator, denominator };
  if (shouldPersistConversionInput(num, den, numerator, denominator)) {
    next.numeratorInput = num;
    next.denominatorInput = den;
  } else {
    delete next.numeratorInput;
    delete next.denominatorInput;
  }
  return next;
}

export function normalizeMaterialUnitsForSubmit(units: MaterialUnit[] | undefined): MaterialUnit[] {
  if (!units?.length) return units ?? [];
  return units.map(prepareMaterialUnitConversionForSubmit);
}