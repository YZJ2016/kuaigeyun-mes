/**
 * 供应商主数据 → 采购单据头联系人/电话（联系人明细真源）
 */
import type { PartnerAddress, PartnerContact } from '../../../../master-data/types/supply-chain';
import type { SupplierLike } from './applySupplierFormFields';

function pickText(row: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const raw = row[key];
    if (raw == null) continue;
    const text = String(raw).trim();
    if (text) return text;
  }
  return undefined;
}

function normalizeContactRows(supplier: SupplierLike): PartnerContact[] {
  const raw = supplier.contacts;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((row) => row && typeof row === 'object')
    .map((row) => row as PartnerContact);
}

function normalizeAddressRows(supplier: SupplierLike): PartnerAddress[] {
  const raw = supplier.addresses;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((row) => row && typeof row === 'object')
    .map((row) => row as PartnerAddress);
}

export type SupplierContactPickOption = {
  value: string;
  label: string;
  phone?: string;
};

export function buildSupplierContactPickOptions(supplier: SupplierLike): SupplierContactPickOption[] {
  const seen = new Set<string>();
  const out: SupplierContactPickOption[] = [];
  const push = (name?: string, phone?: string) => {
    const contact = name?.trim();
    if (!contact) return;
    const key = `${contact}\u0000${phone ?? ''}`;
    if (seen.has(key)) return;
    seen.add(key);
    const phoneText = phone?.trim();
    const label = phoneText ? `${contact} ${phoneText}` : contact;
    out.push({ value: contact, label, phone: phoneText });
  };

  for (const row of normalizeContactRows(supplier)) {
    const r = row as Record<string, unknown>;
    push(
      pickText(r, 'contactPerson', 'contact_person'),
      pickText(r, 'phone'),
    );
  }
  for (const row of normalizeAddressRows(supplier)) {
    const r = row as Record<string, unknown>;
    push(
      pickText(r, 'contactName', 'contact_name'),
      pickText(r, 'contactPhone', 'contact_phone'),
    );
  }
  push(
    pickText(supplier, 'contactPerson', 'contact_person', 'contact', 'supplier_contact'),
    pickText(supplier, 'phone', 'supplier_phone'),
  );
  return out;
}