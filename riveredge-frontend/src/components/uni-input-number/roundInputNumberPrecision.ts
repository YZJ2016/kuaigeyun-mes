/** 失焦时按业务 precision 量化（聚焦期间不格式化，避免输入闪动与强塞 .00）。 */
export function roundInputNumberPrecision(value: number, precision: number): number {
  if (!Number.isFinite(value)) {
    return value;
  }
  if (precision <= 0) {
    return Math.round(value);
  }
  const factor = 10 ** precision;
  return Math.round(value * factor + Number.EPSILON) / factor;
}
