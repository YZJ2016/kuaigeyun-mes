/**
 * 供应商选中后回填采购单据头字段（结算/付款/立账；对齐销售订单 applyCustomerFormFields）。
 */
import type { ProFormInstance } from '@ant-design/pro-components';
import {
  orgFinancePayableDefault,
  resolvePayableRecognitionFromPartner,
} from '../../../../../utils/documentLedgerRecognition';
import { formatUserDisplayLabel, normalizeUserDisplayName } from '../../../../../utils/userDisplay';
import {
  resolvePaymentMethodFromCustomer,
  resolvePaymentMixPercentsFromCustomer,
  resolvePaymentTermsDaysFromCustomer,
  resolveSettlementTermsFromCustomer,
} from '../../sales-management/shared/applyCustomerFormFields';
import { resolveSupplierContactFieldsFromPartner } from './partnerSupplierFormSnapshot';

export type SupplierLike = Record<string, unknown>;

export type UserLike = { id: number | string; [key: string]: unknown };

export function resolveFullSupplierFromList(
  supplier: SupplierLike,
  supplierList: SupplierLike[],
): SupplierLike {
  const id = Number(supplier.id ?? supplier.supplier_id);
  if (!Number.isFinite(id)) return supplier;
  const found = supplierList.find((x) => Number(x.id ?? x.supplier_id) === id);
  if (!found) return supplier;
  return { ...found, ...supplier };
}

function normalizeDocumentCurrencyCode(raw: unknown, fallback = 'CNY'): string {
  if (typeof raw === 'string' && raw.trim()) {
    return raw.trim().toUpperCase();
  }
  return fallback.trim().toUpperCase() || 'CNY';
}

/** 从供应商主数据解析需回填的表单字段 */
export function resolveSupplierFormFieldValues(
  supplier: SupplierLike,
  users: UserLike[] = [],
  orgPayableDefault = 'on_receipt',
  /** 供应商未维护默认币种时的单据本币（站点 default_currency，缺省 CNY） */
  defaultCurrency = 'CNY',
): Record<string, unknown> {
  const documentCurrency = normalizeDocumentCurrencyCode(defaultCurrency);
  const bIdRaw = supplier.buyerId ?? supplier.buyer_id;
  const bId =
    bIdRaw != null && bIdRaw !== '' && Number.isFinite(Number(bIdRaw)) ? Number(bIdRaw) : undefined;
  const buyer = bId != null ? users.find((u) => Number(u.id) === bId) : undefined;
  const bName = normalizeUserDisplayName(
    supplier.buyerName ??
      supplier.buyer_name ??
      (buyer ? formatUserDisplayLabel(buyer) : ''),
  );
  const paymentTermsDays = resolvePaymentTermsDaysFromCustomer(supplier);
  const paymentMethod = resolvePaymentMethodFromCustomer(supplier);
  const paymentMix = resolvePaymentMixPercentsFromCustomer(supplier);
  const settlementTerms = resolveSettlementTermsFromCustomer(supplier);
  const currencyRaw =
    supplier.defaultCurrencyCode ??
    supplier.default_currency_code ??
    supplier.currency ??
    supplier.currency_code;
  // 客商未维护默认币种 → 单据本币（禁止写 undefined 冲掉表单已有 CNY）
  const currency = normalizeDocumentCurrencyCode(currencyRaw, documentCurrency);
  const rateRaw = supplier.defaultExchangeRate ?? supplier.default_exchange_rate;
  const rateNum = rateRaw != null && rateRaw !== '' ? Number(rateRaw) : undefined;
  const exchangeRate =
    rateNum != null && Number.isFinite(rateNum) && rateNum > 0 ? rateNum : 1;
  const { supplier_contact, supplier_phone } = resolveSupplierContactFieldsFromPartner(supplier);
  return {
    supplier_name: supplier.name ?? supplier.supplier_name,
    supplier_contact,
    supplier_phone,
    ...(bId != null ? { buyer_id: bId, buyer_name: bName } : {}),
    ...(paymentMethod != null
      ? { payment_method_code: paymentMethod, ...paymentMix }
      : {
          payment_method_code: undefined,
          payment_wire_percent: undefined,
          payment_acceptance_percent: undefined,
        }),
    ...(settlementTerms != null
      ? { settlement_terms_code: settlementTerms }
      : { settlement_terms_code: undefined }),
    ...(paymentTermsDays != null
      ? { payment_terms_days: paymentTermsDays }
      : { payment_terms_days: undefined }),
    currency,
    exchange_rate: exchangeRate,
    payable_recognition: resolvePayableRecognitionFromPartner(supplier, orgPayableDefault),
  };
}

function buildClearSupplierFormFields(defaultCurrency = 'CNY'): Record<string, unknown> {
  const currency = normalizeDocumentCurrencyCode(defaultCurrency);
  return {
    supplier_name: undefined,
    supplier_contact: undefined,
    supplier_phone: undefined,
    payment_method_code: undefined,
    payment_wire_percent: undefined,
    payment_acceptance_percent: undefined,
    settlement_terms_code: undefined,
    payment_terms_days: undefined,
    currency,
    exchange_rate: 1,
    payable_recognition: undefined,
  };
}

export function applySupplierFormFields(
  formRef: React.RefObject<ProFormInstance | undefined | null> | { current?: ProFormInstance | null },
  supplier: SupplierLike | null,
  options: {
    users?: UserLike[];
    supplierList?: SupplierLike[];
    includeSupplierId?: boolean;
    orgPayableDefault?: string;
    /** 供应商未维护币种时回落；清空供应商时恢复为本币 */
    defaultCurrency?: string;
  } = {},
): void {
  const defaultCurrency = normalizeDocumentCurrencyCode(options.defaultCurrency);
  if (!supplier) {
    formRef.current?.setFieldsValue({
      ...buildClearSupplierFormFields(defaultCurrency),
      ...(options.includeSupplierId ? { supplier_id: undefined } : {}),
    });
    return;
  }
  const full = options.supplierList
    ? resolveFullSupplierFromList(supplier, options.supplierList)
    : supplier;
  const next = resolveSupplierFormFieldValues(
    full,
    options.users,
    options.orgPayableDefault ?? 'on_receipt',
    defaultCurrency,
  );
  if (next.buyer_id == null) {
    const currentId = formRef.current?.getFieldValue('buyer_id');
    const currentName = formRef.current?.getFieldValue('buyer_name');
    if (currentId != null && currentId !== '' && Number.isFinite(Number(currentId))) {
      next.buyer_id = Number(currentId);
      next.buyer_name = currentName;
    }
  }
  formRef.current?.setFieldsValue({
    ...(options.includeSupplierId ? { supplier_id: full.id ?? full.supplier_id } : {}),
    ...next,
  });
}

/** @deprecated 请用 applySupplierFormFields；保留给仅需立账回填的调用方 */
export function applySupplierLedgerRecognition(
  formRef: React.RefObject<ProFormInstance | undefined | null> | { current?: ProFormInstance | null },
  supplier: SupplierLike | null,
  orgPayableDefault = 'on_receipt',
): void {
  if (!supplier) {
    formRef.current?.setFieldsValue({ payable_recognition: undefined });
    return;
  }
  formRef.current?.setFieldsValue({
    payable_recognition: resolvePayableRecognitionFromPartner(supplier, orgPayableDefault),
  });
}

export function resolveOrgPayableDefaultFromBusinessConfig(
  businessConfig: { parameters?: { finance?: Record<string, unknown> } } | undefined,
): string {
  return orgFinancePayableDefault(businessConfig);
}
