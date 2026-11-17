/**
 * 客户选中后回填销售单据头字段（逻辑与销售订单 onCustomerPick 一致，供报价单等同等级页面复用）。
 */
import type { ProFormInstance } from '@ant-design/pro-components';
import { resolveRevenueRecognitionFromPartner } from '../../../../../utils/documentLedgerRecognition';
import { formatUserDisplayLabel, normalizeUserDisplayName } from '../../../../../utils/userDisplay';

export type CustomerLike = Record<string, unknown>;

export type UserLike = { id: number | string; [key: string]: unknown };

export type DictOption = { label: string; value: string };

/** @deprecated 报价/合同等仍用 PAYMENT_TERMS 时过滤阶段方式；销售订单已改天数字段 */
const PAYMENT_CYCLE_STAGE_VALUE_RE = /^(PREPAID|COD)(_|$)/i;
const PAYMENT_CYCLE_STAGE_LABEL_RE = /预付|货到付款|货到付|款到发货|现款|先款/;

export function isPaymentCycleDictionaryOption(o: DictOption): boolean {
  if (PAYMENT_CYCLE_STAGE_VALUE_RE.test(String(o.value ?? ''))) return false;
  if (PAYMENT_CYCLE_STAGE_LABEL_RE.test(String(o.label ?? ''))) return false;
  return true;
}

export function filterPaymentCycleOptions(options: DictOption[]): DictOption[] {
  return options.filter(isPaymentCycleDictionaryOption);
}

export function resolveFullCustomerFromList(
  customer: CustomerLike,
  customerList: CustomerLike[],
): CustomerLike {
  const id = Number(customer.id ?? customer.customer_id);
  if (!Number.isFinite(id)) return customer;
  const found = customerList.find((x) => Number(x.id ?? x.customer_id) === id);
  if (!found) return customer;
  return { ...found, ...customer };
}

/** 从客户「付款账期（天）」解析销售订单付款周期天数 */
export function resolvePaymentTermsDaysFromCustomer(customer: CustomerLike): number | undefined {
  const daysRaw = customer.paymentTermsDays ?? customer.payment_terms_days;
  if (daysRaw == null || daysRaw === '') return undefined;
  const days = Number(daysRaw);
  if (!Number.isFinite(days) || days < 0) return undefined;
  return Math.trunc(days);
}

/**
 * @deprecated 报价/合同等仍映射 PAYMENT_TERMS；销售订单请用 resolvePaymentTermsDaysFromCustomer
 */
export function resolvePaymentTermsFromCustomer(
  customer: CustomerLike,
  paymentTermsOptions: DictOption[] = [],
): string | undefined {
  const cycleOptions = filterPaymentCycleOptions(paymentTermsOptions);

  const directRaw = customer.payment_terms ?? customer.paymentTerms;
  if (typeof directRaw === 'string' && directRaw.trim()) {
    const direct = directRaw.trim();
    if (!cycleOptions.length) {
      if (isPaymentCycleDictionaryOption({ label: direct, value: direct })) return direct;
    } else if (cycleOptions.some((o) => o.value === direct)) {
      return direct;
    } else {
      const byLabel = cycleOptions.find((o) => o.label === direct);
      if (byLabel) return byLabel.value;
    }
  }

  const days = resolvePaymentTermsDaysFromCustomer(customer);
  if (days == null || days === 0) return undefined;

  const netCode = `NET${days}`;
  const creditCode = `CREDIT_${days}`;
  if (!cycleOptions.length) {
    if (days === 30 || days === 60) return netCode;
    return undefined;
  }
  if (cycleOptions.some((o) => o.value === netCode)) return netCode;
  if (cycleOptions.some((o) => o.value === creditCode)) return creditCode;

  const byLabelDays = cycleOptions.find((o) => {
    const m = String(o.label).match(/(\d+)/);
    return m != null && Number(m[1]) === days;
  });
  if (byLabelDays) return byLabelDays.value;

  const byValueDigits = cycleOptions.find(
    (o) => o.value.replace(/\D/g, '') === String(days),
  );
  if (byValueDigits) return byValueDigits.value;

  return undefined;
}

export function resolvePaymentMethodFromCustomer(customer: CustomerLike): string | undefined {
  const raw = customer.defaultPaymentMethodCode ?? customer.default_payment_method_code;
  if (typeof raw !== 'string') return undefined;
  const code = raw.trim();
  return code || undefined;
}

export function resolveSettlementTermsFromCustomer(customer: CustomerLike): string | undefined {
  const raw = customer.settlementTermsCode ?? customer.settlement_terms_code;
  if (typeof raw !== 'string') return undefined;
  const code = raw.trim().toLowerCase();
  if (!code) return undefined;
  if (code === 'monthly' || code === 'bimonthly' || code === 'quarterly') return 'net_terms';
  return code;
}

/** 从客户主数据解析需回填的表单字段 */
export function resolveCustomerFormFieldValues(
  customer: CustomerLike,
  users: UserLike[] = [],
  paymentTermsOptions: DictOption[] = [],
  orgRevenueRecognitionDefault = 'on_shipment',
): Record<string, unknown> {
  const sIdRaw = customer.salesmanId ?? customer.salesman_id;
  const sId =
    sIdRaw != null && sIdRaw !== '' && Number.isFinite(Number(sIdRaw)) ? Number(sIdRaw) : undefined;
  const salesman = sId != null ? users.find((u) => Number(u.id) === sId) : undefined;
  const sName = normalizeUserDisplayName(
    customer.salesmanName ??
      customer.salesman_name ??
      (salesman ? formatUserDisplayLabel(salesman) : ''),
  );
  const paymentTermsDays = resolvePaymentTermsDaysFromCustomer(customer);
  const paymentMethod = resolvePaymentMethodFromCustomer(customer);
  const settlementTerms = resolveSettlementTermsFromCustomer(customer);
  const currencyRaw =
    customer.defaultCurrencyCode ??
    customer.default_currency_code ??
    customer.currency ??
    customer.currency_code;
  const currency =
    typeof currencyRaw === 'string' && currencyRaw.trim()
      ? currencyRaw.trim().toUpperCase()
      : undefined;
  const rateRaw = customer.defaultExchangeRate ?? customer.default_exchange_rate;
  const rateNum = rateRaw != null && rateRaw !== '' ? Number(rateRaw) : undefined;
  const exchangeRate =
    rateNum != null && Number.isFinite(rateNum) && rateNum > 0
      ? rateNum
      : currency
        ? 1
        : undefined;
  /** 报价/合同仍传字典选项时回填 payment_terms；销售订单只认天数 */
  const legacyPaymentTerms =
    paymentTermsOptions.length > 0
      ? resolvePaymentTermsFromCustomer(customer, paymentTermsOptions)
      : undefined;
  return {
    customer_name: customer.name ?? customer.customer_name,
    customer_contact:
      customer.contactPerson ??
      customer.contact_person ??
      customer.contact ??
      customer.customer_contact,
    customer_phone: customer.phone ?? customer.customer_phone,
    salesman_id: sId,
    salesman_name: sName,
    shipping_address:
      customer.deliveryAddress ??
      customer.delivery_address ??
      customer.address ??
      customer.shipping_address ??
      '',
    ...(paymentMethod != null
      ? { payment_method_code: paymentMethod }
      : { payment_method_code: undefined }),
    ...(settlementTerms != null
      ? { settlement_terms_code: settlementTerms }
      : { settlement_terms_code: undefined }),
    ...(paymentTermsDays != null
      ? { payment_terms_days: paymentTermsDays }
      : { payment_terms_days: undefined }),
    ...(currency != null ? { currency } : { currency: undefined }),
    ...(exchangeRate != null
      ? { exchange_rate: exchangeRate }
      : { exchange_rate: undefined }),
    ...(paymentTermsOptions.length > 0
      ? legacyPaymentTerms != null
        ? { payment_terms: legacyPaymentTerms }
        : { payment_terms: undefined }
      : {}),
    revenue_recognition: resolveRevenueRecognitionFromPartner(customer, orgRevenueRecognitionDefault),
  };
}

const CLEAR_CUSTOMER_FORM_FIELDS: Record<string, undefined> = {
  customer_name: undefined,
  customer_contact: undefined,
  customer_phone: undefined,
  salesman_id: undefined,
  salesman_name: undefined,
  shipping_address: undefined,
  payment_method_code: undefined,
  settlement_terms_code: undefined,
  payment_terms_days: undefined,
  currency: undefined,
  exchange_rate: undefined,
  payment_terms: undefined,
  revenue_recognition: undefined,
};

export function applyCustomerFormFields(
  formRef: React.RefObject<ProFormInstance | undefined | null> | { current?: ProFormInstance | null },
  customer: CustomerLike | null,
  options: {
    users?: UserLike[];
    customerList?: CustomerLike[];
    includeCustomerId?: boolean;
    paymentTermsOptions?: DictOption[];
    orgRevenueRecognitionDefault?: string;
  } = {},
): void {
  if (!customer) {
    formRef.current?.setFieldsValue({
      ...CLEAR_CUSTOMER_FORM_FIELDS,
      ...(options.includeCustomerId ? { customer_id: undefined } : {}),
    });
    return;
  }
  const full = options.customerList
    ? resolveFullCustomerFromList(customer, options.customerList)
    : customer;
  const next = resolveCustomerFormFieldValues(
    full,
    options.users,
    options.paymentTermsOptions ?? [],
    options.orgRevenueRecognitionDefault ?? 'on_shipment',
  );
  if (next.salesman_id == null) {
    const currentId = formRef.current?.getFieldValue('salesman_id');
    const currentName = formRef.current?.getFieldValue('salesman_name');
    if (currentId != null && currentId !== '' && Number.isFinite(Number(currentId))) {
      next.salesman_id = Number(currentId);
      next.salesman_name = currentName;
    }
  }
  formRef.current?.setFieldsValue({
    ...(options.includeCustomerId ? { customer_id: full.id ?? full.customer_id } : {}),
    ...next,
  });
}
