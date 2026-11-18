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

/** @deprecated 拆分前合并码表，仅用于旧 Excel 导入列「结算方式」解析 */
const LEGACY_SETTLEMENT_KEYS: Record<string, string> = {
  ...PAYMENT_METHOD_KEYS,
  ...SETTLEMENT_TERMS_KEYS,
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

/** @deprecated 请用 buildPartnerDefaultPaymentMethodImportOptions(t) */
export const PARTNER_SETTLEMENT_METHOD_IMPORT_OPTIONS = Object.keys(LEGACY_SETTLEMENT_KEYS);

export function buildPartnerInvoiceTypeImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, INVOICE_TYPE_KEYS);
}

export function buildPartnerTaxpayerTypeImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, TAXPAYER_TYPE_KEYS);
}

export function buildPartnerEnterpriseTypeImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, ENTERPRISE_TYPE_KEYS);
}

export function buildPartnerDefaultPaymentMethodImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, PAYMENT_METHOD_KEYS);
}

export function buildPartnerSettlementTermsImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, SETTLEMENT_TERMS_KEYS);
}

/** @deprecated 旧模板单列「结算方式」 */
export function buildPartnerSettlementMethodImportOptions(t: TFunction): string[] {
  return buildImportOptions(t, LEGACY_SETTLEMENT_KEYS);
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

/** 旧导入列：解析为 { defaultPaymentMethodCode?, settlementTermsCode? } */
export function splitLegacyPartnerSettlementMethodImport(
  raw?: string | null,
  t?: TFunction,
): { defaultPaymentMethodCode?: string; settlementTermsCode?: string } {
  const code = parsePartnerSettlementMethodImport(raw, t);
  if (!code) return {};
  if (code in SETTLEMENT_TERMS_KEYS) {
    return { settlementTermsCode: code };
  }
  if (code in PAYMENT_METHOD_KEYS) {
    return { defaultPaymentMethodCode: code };
  }
  return {};
}

/** @deprecated 旧单列解析，优先匹配付款方式再匹配结算条款 */
export function parsePartnerSettlementMethodImport(raw?: string | null, t?: TFunction): string | undefined {
  if (!t) {
    const v = String(raw ?? '').trim();
    return v || undefined;
  }
  return parseStaticImport(raw, t, LEGACY_SETTLEMENT_KEYS);
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

/** 苍穹客户 type：伙伴类型 1–5（与 enterpriseTypeCode「企业类型」不同） */
const CUSTOMER_PARTNER_TYPE_KEYS: Record<string, string> = {
  '1': 'field.customer.partnerType.legalEntity',
  '2': 'field.customer.partnerType.nonLegalEntity',
  '3': 'field.customer.partnerType.nonEnterprise',
  '4': 'field.customer.partnerType.individual',
  '5': 'field.customer.partnerType.soleTrader',
};

/** 苍穹客户 bizfunction：业务职能 1–4 */
const CUSTOMER_BIZ_FUNCTION_KEYS: Record<string, string> = {
  '1': 'field.customer.bizFunction.sales',
  '2': 'field.customer.bizFunction.settlement',
  '3': 'field.customer.bizFunction.payment',
  '4': 'field.customer.bizFunction.receiving',
};

export function customerPartnerTypeLabel(t: TFunction, code?: string | null): string {
  if (code == null || String(code).trim() === '') return '—';
  return mapLabel(t, CUSTOMER_PARTNER_TYPE_KEYS, String(code).trim());
}

/** bizfunction 可能为单码或组合串（如 12、1234）；按出现的 1–4 数字展示标签 */
export function customerBizFunctionLabel(t: TFunction, raw?: string | null): string {
  if (raw == null || String(raw).trim() === '') return '—';
  const text = String(raw).trim();
  const seen = new Set<string>();
  const labels: string[] = [];
  for (const ch of text) {
    if (!CUSTOMER_BIZ_FUNCTION_KEYS[ch] || seen.has(ch)) continue;
    seen.add(ch);
    labels.push(mapLabel(t, CUSTOMER_BIZ_FUNCTION_KEYS, ch));
  }
  if (labels.length > 0) return labels.join('、');
  return text;
}

export function partnerDefaultPaymentMethodLabel(t: TFunction, code?: string | null): string {
  return mapLabel(t, PAYMENT_METHOD_KEYS, code);
}

/** 单据头付款方式下拉（与客商默认付款方式同码表） */
export function partnerPaymentMethodSelectOptions(
  t: TFunction,
): Array<{ label: string; value: string }> {
  return Object.keys(PAYMENT_METHOD_KEYS).map((value) => ({
    value,
    label: mapLabel(t, PAYMENT_METHOD_KEYS, value),
  }));
}

/** 单据头结算方式下拉（与客商结算方式同码表；不含历史 monthly 等） */
export function partnerSettlementTermsSelectOptions(
  t: TFunction,
): Array<{ label: string; value: string }> {
  const current = [
    'prepaid',
    'pay_before_ship',
    'spot',
    'cod',
    'net_terms',
    'installment',
    'progress',
    'pay_on_invoice',
  ];
  return current.map((value) => ({
    value,
    label: mapLabel(t, SETTLEMENT_TERMS_KEYS, value),
  }));
}

export function partnerSettlementTermsLabel(t: TFunction, code?: string | null): string {
  return mapLabel(t, SETTLEMENT_TERMS_KEYS, code);
}

const PARTNER_ADDRESS_TYPE_KEYS: Record<string, string> = {
  registered: 'field.partner.addressType.registered',
  delivery: 'field.partner.addressType.delivery',
  invoice: 'field.partner.addressType.invoice',
  other: 'field.partner.addressType.other',
};

export function partnerAddressTypeLabel(t: TFunction, code?: string | null): string {
  if (code == null || code === '') return '—';
  const key = PARTNER_ADDRESS_TYPE_KEYS[code];
  return key ? t(key) : String(code);
}

/** @deprecated 使用 partnerDefaultPaymentMethodLabel / partnerSettlementTermsLabel */
export function partnerSettlementMethodLabel(t: TFunction, code?: string | null): string {
  if (code == null || code === '') return '—';
  if (code in SETTLEMENT_TERMS_KEYS) return partnerSettlementTermsLabel(t, code);
  return partnerDefaultPaymentMethodLabel(t, code);
}

/** 客户主数据 — 应收确认覆盖（空=跟随组织） */
export function partnerRevenueRecognitionOverrideLabel(t: TFunction, code?: string | null): string {
  if (code == null || code === '') return t('field.partner.recognitionOverrideInherit');
  if (code === 'on_shipment') return t('pages.system.configCenter.param.finance_revenue_recognition_opt_on_shipment');
  if (code === 'on_invoice') return t('pages.system.configCenter.param.finance_revenue_recognition_opt_on_invoice');
  if (code === 'manual') return t('pages.system.configCenter.param.finance_revenue_recognition_opt_manual');
  if (code === 'on_partner_statement') {
    return t('pages.system.configCenter.param.finance_revenue_recognition_opt_on_partner_statement');
  }
  if (code === 'on_milestone') {
    return t('pages.system.configCenter.param.finance_revenue_recognition_opt_on_milestone');
  }
  if (code === 'mixed') return t('pages.system.configCenter.param.finance_revenue_recognition_opt_mixed');
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
  if (code === 'on_partner_statement') {
    return t('pages.system.configCenter.param.finance_payable_recognition_opt_on_partner_statement');
  }
  return code;
}
