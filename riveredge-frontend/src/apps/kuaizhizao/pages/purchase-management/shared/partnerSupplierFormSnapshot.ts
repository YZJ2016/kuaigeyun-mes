/**
 * 供应商主数据 → 采购单据头联系人 / 电话。
 * 真源仅：`contacts` 明细。禁止读头字段 / 地址行联系人 / legacy 拼装。
 */
import type { PartnerContact } from '../../../../master-data/types/supply-chain';
import type { SupplierLike } from './applySupplierFormFields';

function asRecord(row: object): Record<string, unknown> {
  return row as Record<string, unknown>;
}

function textOf(row: Record<string, unknown>, key: string): string | undefined {
  const raw = row[key];
  if (raw == null) return undefined;
  const text = String(raw).trim();
  return text || undefined;
}

function contactRows(supplier: SupplierLike): PartnerContact[] {
  const raw = supplier.contacts;
  if (!Array.isArray(raw)) return [];
  return raw.filter((row): row is PartnerContact => {
    if (row == null || typeof row !== 'object') return false;
    const r = asRecord(row);
    // 仅联系人明细：必须有联系人姓名，排除误混入的地址行（含 address / contactName 等）
    if (!contactPersonOf(r)) return false;
    if (
      textOf(r, 'address') ||
      textOf(r, 'addressType') ||
      textOf(r, 'address_type') ||
      (textOf(r, 'contactName') ?? textOf(r, 'contact_name'))
    ) {
      return false;
    }
    return true;
  });
}

/** 引用详情优先；未返回前用列表缓存。禁止把两边明细拼成第三套。 */
export function preferPartnerSupplierDetail(
  listSupplier: SupplierLike | null,
  fetched: SupplierLike | null,
): SupplierLike | null {
  return fetched ?? listSupplier;
}

function contactPickValue(contact: string, phone?: string): string {
  return `${contact}\u0000${String(phone ?? '').trim()}`;
}

/** 选供应商后默认带出：联系人明细第一条。 */
function contactPersonOf(row: Record<string, unknown>): string | undefined {
  return textOf(row, 'contactPerson') ?? textOf(row, 'contact_person');
}

export function resolveSupplierContactFieldsFromPartner(
  supplier: SupplierLike,
): { supplier_contact?: string; supplier_phone?: string } {
  const row = contactRows(supplier)[0];
  if (!row) return {};
  const r = asRecord(row);
  const contact = contactPersonOf(r);
  const phone = textOf(r, 'phone');
  return {
    ...(contact != null ? { supplier_contact: contact } : {}),
    ...(phone != null ? { supplier_phone: phone } : {}),
  };
}

export type SupplierContactPickOption = {
  /** 表单内唯一键（姓名与电话组合；写入单据时仍用 contact 姓名） */
  value: string;
  contact: string;
  label: string;
  phone?: string;
};

/** 下拉选项 = contacts 明细原样。 */
export function buildSupplierContactPickOptions(supplier: SupplierLike): SupplierContactPickOption[] {
  const out: SupplierContactPickOption[] = [];
  for (const row of contactRows(supplier)) {
    const r = asRecord(row);
    const contact = contactPersonOf(r);
    if (!contact) continue;
    const phone = textOf(r, 'phone');
    out.push({
      value: contactPickValue(contact, phone),
      contact,
      /** 下拉与选中态仅展示姓名；电话由独立的「联系电话」字段展示 */
      label: contact,
      phone,
    });
  }
  return out;
}
