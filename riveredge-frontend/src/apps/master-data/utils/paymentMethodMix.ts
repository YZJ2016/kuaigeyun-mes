/** 与后端 partner_settlement_codes / payment_method_mix 对齐 */

export const PARTNER_MIXED_PAYMENT_METHOD = 'bank_transfer_and_acceptance';

/** 与后端 partner_settlement_codes.PARTNER_EMPLOYEE_ADVANCE_PAYMENT_METHOD 一致 */
export const PARTNER_EMPLOYEE_ADVANCE_PAYMENT_METHOD = 'employee_advance';

export function isPartnerEmployeeAdvancePaymentMethod(code?: string | null): boolean {
  return String(code ?? '').trim() === PARTNER_EMPLOYEE_ADVANCE_PAYMENT_METHOD;
}

export function isMixedPaymentMethodCode(code?: string | null): boolean {
  return String(code ?? '').trim() === PARTNER_MIXED_PAYMENT_METHOD;
}

export function validatePaymentMethodMix(
  code: string | undefined | null,
  wire?: number | null,
  acceptance?: number | null,
): string | null {
  if (!isMixedPaymentMethodCode(code)) {
    if (wire != null || acceptance != null) {
      return '非组合付款方式不得填写比例';
    }
    return null;
  }
  const w = Number(wire);
  const a = Number(acceptance);
  if (!Number.isFinite(w) || !Number.isFinite(a)) {
    return '请填写电汇与承兑比例';
  }
  if (w < 0 || w > 100 || a < 0 || a > 100) {
    return '比例须在 0～100 之间';
  }
  if (Math.abs(w + a - 100) > 0.01) {
    return '电汇与承兑比例合计须为 100%';
  }
  return null;
}

export function formatPaymentMethodMixLabel(
  wire?: number | string | null,
  acceptance?: number | string | null,
): string | undefined {
  const w = Number(wire);
  const a = Number(acceptance);
  if (!Number.isFinite(w) || !Number.isFinite(a)) return undefined;
  const fmt = (n: number) => {
    const s = n.toFixed(2).replace(/\.?0+$/, '');
    return s;
  };
  return `电汇${fmt(w)}% 承兑${fmt(a)}%`;
}