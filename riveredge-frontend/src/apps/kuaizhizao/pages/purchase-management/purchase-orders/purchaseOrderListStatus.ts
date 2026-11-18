import type { TFunction } from 'i18next';

import type { PurchaseOrder } from '../../../services/purchase';

export const PURCHASE_ORDER_PAYMENT_SETTLEMENT_VALUES = ['unpaid', 'partial', 'paid'] as const;

export type PurchaseOrderPaymentSettlement =
  (typeof PURCHASE_ORDER_PAYMENT_SETTLEMENT_VALUES)[number];

const SETTLEMENT_I18N: Record<PurchaseOrderPaymentSettlement, string> = {
  unpaid: 'app.kuaizhizao.paymentApplication.settlement.unpaid',
  partial: 'app.kuaizhizao.paymentApplication.settlement.partial',
  paid: 'app.kuaizhizao.paymentApplication.settlement.paid',
};

export function resolvePurchaseOrderPaymentSettlementDisplay(
  record: PurchaseOrder,
  t: TFunction,
): { label: string; raw: string } | null {
  const key = String(record.payment_settlement ?? '').trim().toLowerCase();
  if (!key || !(PURCHASE_ORDER_PAYMENT_SETTLEMENT_VALUES as readonly string[]).includes(key)) {
    return null;
  }
  const i18nKey = SETTLEMENT_I18N[key as PurchaseOrderPaymentSettlement];
  const label = t(i18nKey);
  return { label, raw: label };
}

export function buildPurchaseOrderPaymentSettlementEnum(t: TFunction) {
  return {
    unpaid: { text: t(SETTLEMENT_I18N.unpaid) },
    partial: { text: t(SETTLEMENT_I18N.partial) },
    paid: { text: t(SETTLEMENT_I18N.paid) },
  } as const;
}
