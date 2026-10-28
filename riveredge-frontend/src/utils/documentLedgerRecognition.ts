import type { TFunction } from 'i18next';

export const REVENUE_LEDGER_RECOGNITION_VALUES = [
  'on_shipment',
  'on_invoice',
  'on_milestone',
  'mixed',
  'on_partner_statement',
  'manual',
] as const;

export const PAYABLE_LEDGER_RECOGNITION_VALUES = [
  'on_receipt',
  'on_purchase_invoice',
  'on_partner_statement',
  'manual',
] as const;

export type RevenueLedgerRecognition = (typeof REVENUE_LEDGER_RECOGNITION_VALUES)[number];
export type PayableLedgerRecognition = (typeof PAYABLE_LEDGER_RECOGNITION_VALUES)[number];

const REVENUE_LABEL_KEYS: Record<RevenueLedgerRecognition, string> = {
  on_shipment: 'pages.system.configCenter.param.finance_revenue_recognition_opt_on_shipment',
  on_invoice: 'pages.system.configCenter.param.finance_revenue_recognition_opt_on_invoice',
  on_milestone: 'pages.system.configCenter.param.finance_revenue_recognition_opt_on_milestone',
  mixed: 'pages.system.configCenter.param.finance_revenue_recognition_opt_mixed',
  on_partner_statement:
    'pages.system.configCenter.param.finance_revenue_recognition_opt_on_partner_statement',
  manual: 'pages.system.configCenter.param.finance_revenue_recognition_opt_manual',
};

const PAYABLE_LABEL_KEYS: Record<PayableLedgerRecognition, string> = {
  on_receipt: 'pages.system.configCenter.param.finance_payable_recognition_opt_on_receipt',
  on_purchase_invoice:
    'pages.system.configCenter.param.finance_payable_recognition_opt_on_purchase_invoice',
  on_partner_statement:
    'pages.system.configCenter.param.finance_payable_recognition_opt_on_partner_statement',
  manual: 'pages.system.configCenter.param.finance_payable_recognition_opt_manual',
};

export function buildRevenueLedgerRecognitionOptions(t: TFunction) {
  return REVENUE_LEDGER_RECOGNITION_VALUES.map((value) => ({
    value,
    label: t(REVENUE_LABEL_KEYS[value]),
  }));
}

export function buildPayableLedgerRecognitionOptions(t: TFunction) {
  return PAYABLE_LEDGER_RECOGNITION_VALUES.map((value) => ({
    value,
    label: t(PAYABLE_LABEL_KEYS[value]),
  }));
}

export function revenueLedgerRecognitionLabel(t: TFunction, code?: string | null): string {
  const key = code as RevenueLedgerRecognition | undefined;
  if (key && key in REVENUE_LABEL_KEYS) return t(REVENUE_LABEL_KEYS[key]);
  return code ? String(code) : '—';
}

export function payableLedgerRecognitionLabel(t: TFunction, code?: string | null): string {
  const key = code as PayableLedgerRecognition | undefined;
  if (key && key in PAYABLE_LABEL_KEYS) return t(PAYABLE_LABEL_KEYS[key]);
  return code ? String(code) : '—';
}

type PartnerLike = Record<string, unknown>;

export function resolveRevenueRecognitionFromPartner(
  partner: PartnerLike | null | undefined,
  orgDefault: string,
): string {
  if (!partner) return orgDefault;
  const ov =
    partner.revenueRecognitionOverride ??
    partner.revenue_recognition_override ??
    partner.revenueRecognition ??
    partner.revenue_recognition;
  if (typeof ov === 'string' && ov.trim()) return ov.trim();
  return orgDefault;
}

export function resolvePayableRecognitionFromPartner(
  partner: PartnerLike | null | undefined,
  orgDefault: string,
): string {
  if (!partner) return orgDefault;
  const ov =
    partner.payableRecognitionOverride ??
    partner.payable_recognition_override ??
    partner.payableRecognition ??
    partner.payable_recognition;
  if (typeof ov === 'string' && ov.trim()) return ov.trim();
  return orgDefault;
}

export function orgFinanceRevenueDefault(businessConfig: { parameters?: { finance?: Record<string, unknown> } } | undefined): string {
  const raw = businessConfig?.parameters?.finance?.revenue_recognition;
  return typeof raw === 'string' && raw.trim() ? raw.trim() : 'on_shipment';
}

export function orgFinancePayableDefault(businessConfig: { parameters?: { finance?: Record<string, unknown> } } | undefined): string {
  const raw = businessConfig?.parameters?.finance?.payable_recognition;
  return typeof raw === 'string' && raw.trim() ? raw.trim() : 'on_receipt';
}
