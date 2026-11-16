/**
 * 客户/供应商详情中静态编码字段的展示（非数据字典）
 */

import type { TFunction } from 'i18next';

import {
  buildImportDictionaryOptionPack,
  parseImportCodedCell,
  type ImportCodeLabelMap,
} from '../../../utils/loadImportDictionaryValues';

const INVOICE_TYPE_KEYS: Record<string, string> = {
  digital_vat_special: 'field.partner.invoiceType.digitalSpecial',
  digital_vat_ordinary: 'field.partner.invoiceType.digitalOrdinary',
  /** 历史存档数据（纸质 / 旧版电子票编码） */
  vat_ordinary: 'field.partner.invoiceType.legacyVatOrdinary',
  vat_special: 'field.partner.invoiceType.legacyVatSpecial',
  vat_e_special: 'field.partner.invoiceType.legacyVatESpecial',
  vat_e_ordinary: 'field.partner.invoiceType.legacyVatEOrdinary',
};

const TAXPAYER_TYPE_KEYS: Record<string, string> = {
  general: 'field.partner.taxpayerType.general',
  small_scale: 'field.partner.taxpayerType.smallScale',
  non_enterprise: 'field.partner.taxpayerType.nonEnterprise',
};

const ENTERPRISE_TYPE_KEYS: Record<string, string> = {
  limited_liability: 'field.partner.enterpriseType.limitedLiability',
  company_limited_by_shares: 'field.partner.enterpriseType.companyLimitedByShares',
  sole_proprietorship: 'field.partner.enterpriseType.soleProprietorship',
  partnership: 'field.partner.enterpriseType.partnership',
  individual_business: 'field.partner.enterpriseType.individualBusiness',
  other: 'field.partner.enterpriseType.other',
};

const SETTLEMENT_KEYS: Record<string, string> = {
  cash: 'field.partner.settlementMethod.cash',
  bank_transfer: 'field.partner.settlementMethod.bankTransfer',
  bank_acceptance: 'field.partner.settlementMethod.bankAcceptance',
  commercial_acceptance: 'field.partner.settlementMethod.commercialAcceptance',
  monthly: 'field.partner.settlementMethod.monthly',
  prepaid: 'field.partner.settlementMethod.prepaid',
  other: 'field.partner.settlementMethod.other',
};

const PAYMENT_METHOD_KEYS: Record<string, string> = {
  cash: 'field.partner.settlementMethod.cash',
  bank_transfer: 'field.partner.settlementMethod.bankTransfer',
  bank_acceptance: 'field.partner.settlementMethod.bankAcceptance',
  commercial_acceptance: 'field.partner.settlementMethod.commercialAcceptance',
  other: 'field.partner.settlementMethod.other',
};

const SETTLEMENT_TERMS_KEYS: Record<string, string> = {
  prepaid: 'field.partner.settlementMethod.prepaid',
  pay_before_ship: 'field.partner.settlementMethod.payBeforeShip',
  spot: 'field.partner.settlementMethod.spot',
  cod: 'field.partner.settlementMethod.cod',
  net_terms: 'field.partner.settlementMethod.netTerms',
  /** @deprecated 库内历史值，展示仍可读 */
  monthly: 'field.partner.settlementMethod.monthly',
  bimonthly: 'field.partner.settlementMethod.bimonthly',
  quarterly: 'field.partner.settlementMethod.quarterly',
  installment: 'field.partner.settlementMethod.installment',
  progress: 'field.partner.settlementMethod.progress',
  pay_on_invoice: 'field.partner.settlementMethod.payOnInvoice',
};

const SETTLEMENT_TERMS_CN_ALIASES: Record<string, string> = {
  月结: 'net_terms',
  双月结: 'net_terms',
  季结: 'net_terms',
  季度结: 'net_terms',
  预付款: 'prepaid',
  预付: 'prepaid',
  款到发货: 'pay_before_ship',
  先款后货: 'pay_before_ship',
  现款现货: 'spot',
  货到付款: 'cod',
  账期结算: 'net_terms',
  账期: 'net_terms',
  分期付款: 'installment',
  分期: 'installment',
  进度款: 'progress',
  按进度: 'progress',
  票到付款: 'pay_on_invoice',
  见票付款: 'pay_on_invoice',
  票到付: 'pay_on_invoice',
};

function mapLabel(t: TFunction, map: Record<string, string>, code?: string | null): string {
  if (code == null || code === '') return '—';
  const key = map[code];
  if (!key) return code;
  const text = t(key);
  return text === key ? code : text;
}

function buildCodeLabelMap(t: TFunction, i18nKeys: Record<string, string>): ImportCodeLabelMap {
  const labelByCode: ImportCodeLabelMap = {};
  for (const code of Object.keys(i18nKeys)) {
    labelByCode[code] = mapLabel(t, i18nKeys, code);
  }
  return labelByCode;
}

function buildImportOptions(t: TFunction, i18nKeys: Record<string, string>): string[] {
  return buildImportDictionaryOptionPack(buildCodeLabelMap(t, i18nKeys)).options;
}

function parseStaticImport(
  raw: string | null | undefined,
  t: TFunction,
  i18nKeys: Record<string, string>,
): string | undefined {
  return parseImportCodedCell(raw, buildCodeLabelMap(t, i18nKeys));
}

/** @deprecated 请用 buildPartnerInvoiceTypeImportOptions(t)；保留仅为兼容未传 t 的旧引用 */
export const PARTNER_INVOICE_TYPE_IMPORT_OPTIONS = Object.keys(INVOICE_TYPE_KEYS);

/** @deprecated 请用 buildPartnerTaxpayerTypeImportOptions(t) */
export const PARTNER_TAXPAYER_TYPE_IMPORT_OPTIONS = Object.keys(TAXPAYER_TYPE_KEYS);

/** @deprecated 请用 buildPartnerEnterpriseTypeImportOptions(t) */
export const PARTNER_ENTERPRISE_TYPE_IMPORT_OPTIONS = Object.keys(ENTERPRISE_TYPE_KEYS);

/** @deprecated 请用 buildPartnerSettlementMethodImportOptions(t) */
export const PARTNER_SETTLEMENT_METHOD_IMPORT_OPTIONS = Object.keys(SETTLEMENT_KEYS);

export function buildPartnerInvoiceTypeImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, INVOICE_TYPE_KEYS);
}

export function buildPartnerTaxpayerTypeImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, TAXPAYER_TYPE_KEYS);
}

export function buildPartnerEnterpriseTypeImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, ENTERPRISE_TYPE_KEYS);
}

export function buildPartnerSettlementMethodImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, SETTLEMENT_KEYS);
}

export function buildPartnerDefaultPaymentMethodImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, PAYMENT_METHOD_KEYS);
}

export function buildPartnerSettlementTermsImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, SETTLEMENT_TERMS_KEYS);
}

export function parsePartnerInvoiceTypeImport(raw?: string | null, t?: TFunction): string | undefined {
  if (!t) {
    const v = String(raw ?? '').trim();
    return v || undefined;
  }
  return parseStaticImport(raw, t, INVOICE_TYPE_KEYS);
}

export function parsePartnerTaxpayerTypeImport(raw?: string | null, t?: TFunction): string | undefined {
  if (!t) {
    const v = String(raw ?? '').trim();
    return v || undefined;
  }
  return parseStaticImport(raw, t, TAXPAYER_TYPE_KEYS);
}

export function parsePartnerEnterpriseTypeImport(raw?: string | null, t?: TFunction): string | undefined {
  if (!t) {
    const v = String(raw ?? '').trim();
    return v || undefined;
  }
  return parseStaticImport(raw, t, ENTERPRISE_TYPE_KEYS);
}

export function parsePartnerSettlementMethodImport(raw?: string | null, t?: TFunction): string | undefined {
  if (!t) {
    const v = String(raw ?? '').trim();
    return v || undefined;
  }
  return parseStaticImport(raw, t, SETTLEMENT_KEYS);
}

export function parsePartnerDefaultPaymentMethodImport(raw?: string | null, t?: TFunction): string | undefined {
  if (!t) {
    const v = String(raw ?? '').trim();
    return v && v in PAYMENT_METHOD_KEYS ? v : undefined;
  }
  return parseStaticImport(raw, t, PAYMENT_METHOD_KEYS);
}

export function parsePartnerSettlementTermsImport(raw?: string | null, t?: TFunction): string | undefined {
  const trimmed = String(raw ?? '').trim();
  if (!trimmed) return undefined;
  const fromCn = SETTLEMENT_TERMS_CN_ALIASES[trimmed];
  if (fromCn) return fromCn;
  const lowered = trimmed.toLowerCase();
  if (lowered in SETTLEMENT_TERMS_KEYS) return lowered;
  if (!t) return undefined;
  return parseStaticImport(raw, t, SETTLEMENT_TERMS_KEYS);
}

export function partnerInvoiceTypeLabel(t: TFunction, code?: string | null): string {
  return mapLabel(t, INVOICE_TYPE_KEYS, code);
}

export function partnerTaxpayerTypeLabel(t: TFunction, code?: string | null): string {
  return mapLabel(t, TAXPAYER_TYPE_KEYS, code);
}

export function partnerEnterpriseTypeLabel(t: TFunction, code?: string | null): string {
  return mapLabel(t, ENTERPRISE_TYPE_KEYS, code);
}

export function partnerSettlementMethodLabel(t: TFunction, code?: string | null): string {
  return mapLabel(t, SETTLEMENT_KEYS, code);
}

/** 客户主数据 — 应收确认覆盖（空=跟随组织） */
export function partnerRevenueRecognitionOverrideLabel(t: TFunction, code?: string | null): string {
  if (code == null || code === '') return t('field.partner.recognitionOverrideInherit');
  if (code === 'on_shipment') return t('pages.system.configCenter.param.finance_revenue_recognition_opt_on_shipment');
  if (code === 'on_invoice') return t('pages.system.configCenter.param.finance_revenue_recognition_opt_on_invoice');
  if (code === 'manual') return t('pages.system.configCenter.param.finance_revenue_recognition_opt_manual');
  return code;
}

/** 供应商主数据 — 应付确认覆盖（空=跟随组织） */
export function partnerPayableRecognitionOverrideLabel(t: TFunction, code?: string | null): string {
  if (code == null || code === '') return t('field.partner.recognitionOverrideInherit');
  if (code === 'on_receipt') return t('pages.system.configCenter.param.finance_payable_recognition_opt_on_receipt');
  if (code === 'on_purchase_invoice') {
    return t('pages.system.configCenter.param.finance_payable_recognition_opt_on_purchase_invoice');
  }
  if (code === 'manual') return t('pages.system.configCenter.param.finance_payable_recognition_opt_manual');
  return code;
}
