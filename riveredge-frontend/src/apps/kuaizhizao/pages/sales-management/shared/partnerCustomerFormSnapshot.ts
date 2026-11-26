/**
 * 客户主数据 → 销售单据头联系人 / 收货地址。
 * 真源仅：`contacts` 明细、`addresses` 明细。禁止读头字段 / 地址行联系人 / legacy 拼装。
 */

import type { PartnerAddress, PartnerContact } from '../../../../master-data/types/supply-chain';
import type { CustomerLike } from './applyCustomerFormFields';

function asRecord(row: object): Record<string, unknown> {
  return row as Record<string, unknown>;
}

function textOf(row: Record<string, unknown>, key: string): string | undefined {
  const raw = row[key];
  if (raw == null) return undefined;
  const text = String(raw).trim();
  return text || undefined;
}

function contactRows(customer: CustomerLike): PartnerContact[] {
  const raw = customer.contacts;
  if (!Array.isArray(raw)) return [];
  return raw.filter((row): row is PartnerContact => row != null && typeof row === 'object');
}

function addressRows(customer: CustomerLike): PartnerAddress[] {
  const raw = customer.addresses;
  if (!Array.isArray(raw)) return [];
  return raw.filter((row): row is PartnerAddress => row != null && typeof row === 'object');
}

function addressTypeOf(row: PartnerAddress): string {
  return textOf(asRecord(row), 'addressType') || 'other';
}

function addressLineOf(row: PartnerAddress): string | undefined {
  return textOf(asRecord(row), 'address');
}

/** 引用详情优先；未返回前用列表缓存。禁止把两边明细拼成第三套。 */
export function preferPartnerCustomerDetail(
  listCustomer: CustomerLike | null,
  fetched: CustomerLike | null,
): CustomerLike | null {
  return fetched ?? listCustomer;
}

function contactPickValue(contact: string, phone?: string): string {
  return `${contact}\u0000${String(phone ?? '').trim()}`;
}

function contactPersonOf(row: Record<string, unknown>): string | undefined {
  return textOf(row, 'contactPerson') ?? textOf(row, 'contact_person');
}

/** 选客户后默认带出：联系人明细第一条。 */
export function resolveCustomerContactFieldsFromPartner(
  customer: CustomerLike,
): { customer_contact?: string; customer_phone?: string } {
  const row = contactRows(customer)[0];
  if (!row) return {};
  const r = asRecord(row);
  const contact = contactPersonOf(r);
  const phone = textOf(r, 'phone');
  return {
    ...(contact != null ? { customer_contact: contact } : {}),
    ...(phone != null ? { customer_phone: phone } : {}),
  };
}

export type CustomerContactPickOption = {
  /** 表单内唯一键（姓名与电话组合；写入单据时仍用 contact 姓名） */
  value: string;
  contact: string;
  label: string;
  phone?: string;
};

export type CustomerAddressPickOption = {
  value: string;
  label: string;
  addressType?: string;
};

/** 下拉选项 = contacts 明细原样。 */
export function buildCustomerContactPickOptions(customer: CustomerLike): CustomerContactPickOption[] {
  const out: CustomerContactPickOption[] = [];
  for (const row of contactRows(customer)) {
    const r = asRecord(row);
    const contact = contactPersonOf(r);
    if (!contact) continue;
    const phone = textOf(r, 'phone');
    out.push({
      value: contactPickValue(contact, phone),
      contact,
      /** 下拉与选中态仅展示姓名；电话由独立的「联系电话」字段展示（对齐采购） */
      label: contact,
      phone,
    });
  }
  return out;
}

const ADDRESS_TYPE_RANK: Record<string, number> = {
  delivery: 0,
  registered: 1,
  invoice: 2,
  other: 3,
};

/** 下拉选项 = addresses 明细原样。 */
export function buildCustomerShippingAddressPickOptions(
  customer: CustomerLike,
  formatTypeLabel?: (type: string) => string,
): CustomerAddressPickOption[] {
  const addresses = addressRows(customer).filter((row) => Boolean(addressLineOf(row)));
  const typeCounts = new Map<string, number>();
  for (const row of addresses) {
    const t = addressTypeOf(row);
    typeCounts.set(t, (typeCounts.get(t) ?? 0) + 1);
  }
  const ranked = [...addresses].sort(
    (a, b) => (ADDRESS_TYPE_RANK[addressTypeOf(a)] ?? 9) - (ADDRESS_TYPE_RANK[addressTypeOf(b)] ?? 9),
  );
  return ranked.map((row) => {
    const line = addressLineOf(row)!;
    const addressType = addressTypeOf(row);
    const typeLabel = formatTypeLabel?.(addressType);
    const contactHint = textOf(asRecord(row), 'contactName');
    const multiSameType = (typeCounts.get(addressType) ?? 0) > 1;
    const label = typeLabel
      ? multiSameType && contactHint
        ? `${typeLabel}（${contactHint}）：${line}`
        : `${typeLabel}：${line}`
      : line;
    return { value: line, label, addressType };
  });
}

/** 选客户后默认收货地址：默认收货行 → 首条收货 → 默认行 → 首条地址。 */
export function resolveCustomerShippingAddressFromPartner(customer: CustomerLike): string | undefined {
  const addresses = addressRows(customer);
  if (!addresses.length) return undefined;

  const deliveries = addresses.filter((row) => addressTypeOf(row) === 'delivery');
  if (deliveries.length > 0) {
    const defaultDelivery = deliveries.find((row) => Boolean(row.isDefault));
    const line = addressLineOf(defaultDelivery ?? deliveries[0]);
    if (line) return line;
  }

  const defaultRow = addresses.find((row) => Boolean(row.isDefault));
  return addressLineOf(defaultRow ?? addresses[0]);
}
