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
  resolvePaymentTermsDaysFromCustomer,
  resolveSettlementTermsFromCustomer,
} from '../../sales-management/shared/applyCustomerFormFields';

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

/** 从供应商主数据解析需回填的表单字段 */
export function resolveSupplierFormFieldValues(
  supplier: SupplierLike,
  users: UserLike[] = [],
  orgPayableDefault = 'on_receipt',
): Record<string, unknown> {
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
  const settlementTerms = resolveSettlementTermsFromCustomer(supplier);
  const contactFromList =
    Array.isArray(supplier.contacts) && (supplier.contacts as Array<Record<string, unknown>>)[0]
      ? ((supplier.contacts as Array<Record<string, unknown>>)[0].contactPerson ??
        (supplier.contacts as Array<Record<string, unknown>>)[0].contact_person)
      : undefined;
  const phoneFromList =
    Array.isArray(supplier.contacts) && (supplier.contacts as Array<Record<string, unknown>>)[0]
      ? (supplier.contacts as Array<Record<string, unknown>>)[0].phone
      : undefined;
  return {
    supplier_name: supplier.name ?? supplier.supplier_name,
    supplier_contact:
      supplier.contactPerson ??
      supplier.contact_person ??
      supplier.contact ??
      supplier.supplier_contact ??
      contactFromList,
    supplier_phone: supplier.phone ?? supplier.supplier_phone ?? phoneFromList,
    ...(bId != null ? { buyer_id: bId, buyer_name: bName } : {}),
    ...(paymentMethod != null
      ? { payment_method_code: paymentMethod }
      : { payment_method_code: undefined }),
    ...(settlementTerms != null
      ? { settlement_terms_code: settlementTerms }
      : { settlement_terms_code: undefined }),
    ...(paymentTermsDays != null
      ? { payment_terms_days: paymentTermsDays }
      : { payment_terms_days: undefined }),
    payable_recognition: resolvePayableRecognitionFromPartner(supplier, orgPayableDefault),
  };
}

const CLEAR_SUPPLIER_FORM_FIELDS: Record<string, undefined> = {
  supplier_name: undefined,
  supplier_contact: undefined,
  supplier_phone: undefined,
  payment_method_code: undefined,
  settlement_terms_code: undefined,
  payment_terms_days: undefined,
  payable_recognition: undefined,
};

export function applySupplierFormFields(
  formRef: React.RefObject<ProFormInstance | undefined | null> | { current?: ProFormInstance | null },
  supplier: SupplierLike | null,
  options: {
    users?: UserLike[];
    supplierList?: SupplierLike[];
    includeSupplierId?: boolean;
    orgPayableDefault?: string;
  } = {},
): void {
  if (!supplier) {
    formRef.current?.setFieldsValue({
      ...CLEAR_SUPPLIER_FORM_FIELDS,
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
