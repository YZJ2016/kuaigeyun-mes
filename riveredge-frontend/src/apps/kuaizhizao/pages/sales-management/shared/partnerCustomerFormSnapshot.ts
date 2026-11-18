/**
 * 客户主数据 → 销售单据头联系人/收货地址（联系人明细 + 地址明细真源）
 */

import type { PartnerAddress, PartnerContact } from '../../../../master-data/types/supply-chain';
import type { CustomerLike } from './applyCustomerFormFields';

function pickText(row: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const raw = row[key];
    if (raw == null) continue;
    const text = String(raw).trim();
    if (text) return text;
  }
  return undefined;
}

function normalizeContactRows(customer: CustomerLike): PartnerContact[] {
  const raw = customer.contacts;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((row) => row && typeof row === 'object')
    .map((row) => row as PartnerContact);
}

function normalizeAddressRows(customer: CustomerLike): PartnerAddress[] {
  const raw = customer.addresses;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((row) => row && typeof row === 'object')
    .map((row) => row as PartnerAddress);
}

function pickAddressRow(
  rows: PartnerAddress[],
  type: string,
): PartnerAddress | undefined {
  return rows.find((row) => {
    const code = pickText(row as Record<string, unknown>, 'addressType', 'address_type');
    return code === type;
  });
}

export function resolveCustomerContactFieldsFromPartner(
  customer: CustomerLike,
): { customer_contact?: string; customer_phone?: string } {
  const contacts = normalizeContactRows(customer);
  const deliveryAddress = pickAddressRow(normalizeAddressRows(customer), 'delivery');

  let contact: string | undefined;
  let phone: string | undefined;

  if (contacts.length > 0) {
    const first = contacts[0] as Record<string, unknown>;
    contact = pickText(first, 'contactPerson', 'contact_person');
    phone = pickText(first, 'phone');
  }

  if (deliveryAddress) {
    const row = deliveryAddress as Record<string, unknown>;
    contact = pickText(row, 'contactName', 'contact_name') ?? contact;
  phone = pickText(row, 'contactPhone', 'contact_phone') ?? phone;
  }

  contact =
    contact ??
    pickText(customer, 'contactPerson', 'contact_person', 'contact', 'customer_contact');
  phone = phone ?? pickText(customer, 'phone', 'customer_phone');

  return {
    ...(contact != null ? { customer_contact: contact } : {}),
    ...(phone != null ? { customer_phone: phone } : {}),
  };
}

export function resolveCustomerShippingAddressFromPartner(customer: CustomerLike): string | undefined {
  const addresses = normalizeAddressRows(customer);
  if (addresses.length > 0) {
    const delivery = pickAddressRow(addresses, 'delivery');
    const defaultRow = addresses.find((row) => Boolean(row.isDefault ?? (row as Record<string, unknown>).is_default));
    const registered = pickAddressRow(addresses, 'registered');
    const picked = delivery ?? defaultRow ?? registered ?? addresses[0];
    const line = pickText(picked as Record<string, unknown>, 'address');
    if (line) return line;
  }

  return (
    pickText(customer, 'deliveryAddress', 'delivery_address', 'address', 'shipping_address') ??
    undefined
  );
}
