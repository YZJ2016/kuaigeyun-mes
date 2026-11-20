/**
 * 引用资源展示（下拉搜索 / 回显），与资源 read 权限解耦。
 */

import { requestDisplayResolve, requestDisplaySearch, ReferenceDisplayAccessError } from '../services/displayContract';
import type { CurrentUser } from '../types/api';
import { hasPermission } from './permission';

export interface ReferenceDisplayItem {
  id?: number | null;
  uuid?: string | null;
  code?: string | null;
  name?: string | null;
  label: string;
  extra?: Record<string, unknown>;
}

export interface ReferenceDisplayListResponse {
  items: ReferenceDisplayItem[];
  total: number;
  page: number;
  page_size: number;
}

export { ReferenceDisplayAccessError };

/** 与后端 display-search page_size 上限一致 */
export const REFERENCE_DISPLAY_MAX_PAGE_SIZE = 200;

function displayPermissionCodes(resourceKey: string): [string, string] {
  const key = resourceKey.trim().toLowerCase();
  return [`${key}:read`, `${key}:display`];
}

/** 统一策略：前端不做 display 显式权限直判，交由后端统一裁决。 */
export function canPickReferenceDisplayExplicit(
  user: CurrentUser | undefined,
  _resourceKey: string,
): boolean {
  return Boolean(user);
}

export function formatReferenceDisplayLabel(item: ReferenceDisplayItem): string {
  if (item.label?.trim()) return item.label.trim();
  const code = (item.code || '').trim();
  const name = (item.name || '').trim();
  if (code && name) return `${code} - ${name}`;
  if (name) return name;
  if (code) return code;
  if (item.id != null) return String(item.id);
  return '';
}

export async function searchReferenceDisplay(args: {
  resource: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  isActive?: boolean;
  hostResource?: string;
  groupId?: number;
  sourceType?: string;
  /** 销售单据：按该客户编号映射检索伙伴料号/品名 */
  customerId?: number;
  /** 采购单据：按该供应商编号映射检索伙伴料号/品名 */
  supplierId?: number;
}): Promise<ReferenceDisplayListResponse> {
  return requestDisplaySearch<ReferenceDisplayListResponse>(
    '/core/reference/display-search',
    {
      resource: args.resource,
      keyword: args.keyword,
      page: args.page ?? 1,
      page_size: args.pageSize ?? 50,
      is_active: args.isActive ?? true,
      host_resource: args.hostResource,
      group_id: args.groupId,
      source_type: args.sourceType,
      customer_id: args.customerId,
      supplier_id: args.supplierId,
    },
  );
}

/** 分页拉取引用展示列表（突破单页 200 条上限） */
export async function searchReferenceDisplayAll(
  args: Omit<Parameters<typeof searchReferenceDisplay>[0], 'page' | 'pageSize'>,
  maxItems = 2000,
): Promise<ReferenceDisplayItem[]> {
  const pageSize = REFERENCE_DISPLAY_MAX_PAGE_SIZE;
  const items: ReferenceDisplayItem[] = [];
  let page = 1;
  while (items.length < maxItems) {
    const res = await searchReferenceDisplay({ ...args, page, pageSize });
    items.push(...(res.items ?? []));
    const batchLen = res.items?.length ?? 0;
    if (batchLen < pageSize || items.length >= (res.total ?? items.length)) {
      break;
    }
    page += 1;
  }
  return items.slice(0, maxItems);
}

export async function resolveReferenceDisplay(args: {
  resource: string;
  recordIds?: number[];
  recordUuids?: string[];
  hostResource?: string;
}): Promise<ReferenceDisplayItem[]> {
  const res = await requestDisplayResolve<{ items: ReferenceDisplayItem[] }>(
    '/core/reference/display-resolve',
    {
      resource: args.resource,
      record_ids: args.recordIds ?? [],
      record_uuids: args.recordUuids ?? [],
      host_resource: args.hostResource,
    },
  );
  return res.items ?? [];
}

/** 将引用展示项转为 id 下拉选项 */
export function referenceDisplayToIdOptions(
  items: ReferenceDisplayItem[],
): { label: string; value: number }[] {
  return items
    .filter((i) => i.id != null)
    .map((i) => ({ label: formatReferenceDisplayLabel(i), value: i.id as number }));
}

function extraStr(extra: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const raw = extra[key];
    if (raw == null) continue;
    const text = String(raw).trim();
    if (text) return text;
  }
  return undefined;
}

function mapPartnerContactsFromExtra(
  extra: Record<string, unknown>,
): { contactPerson?: string; contactTitle?: string; phone?: string; email?: string }[] | undefined {
  const raw = extra.contacts;
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const rows = raw
    .map((row) => {
      if (!row || typeof row !== 'object') return null;
      const r = row as Record<string, unknown>;
      const contactPerson = extraStr(r, 'contact_person', 'contactPerson');
      const phone = extraStr(r, 'phone');
      const email = extraStr(r, 'email');
      const contactTitle = extraStr(r, 'contact_title', 'contactTitle');
      if (!contactPerson && !phone) return null;
      return { contactPerson, contactTitle, phone, email };
    })
    .filter(Boolean) as {
    contactPerson?: string;
    contactTitle?: string;
    phone?: string;
    email?: string;
  }[];
  return rows.length ? rows : undefined;
}

function mapPartnerAddressesFromExtra(
  extra: Record<string, unknown>,
):
  | {
      addressType?: string;
      address?: string;
      contactName?: string;
      contactPhone?: string;
      isDefault?: boolean;
    }[]
  | undefined {
  const raw = extra.addresses;
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const rows = raw
    .map((row) => {
      if (!row || typeof row !== 'object') return null;
      const r = row as Record<string, unknown>;
      const address = extraStr(r, 'address');
      if (!address) return null;
      const addressType = extraStr(r, 'address_type', 'addressType');
      return {
        addressType,
        address,
        contactName: extraStr(r, 'contact_name', 'contactName'),
        contactPhone: extraStr(r, 'contact_phone', 'contactPhone'),
        isDefault: Boolean(r.is_default ?? r.isDefault),
      };
    })
    .filter(Boolean) as {
    addressType?: string;
    address?: string;
    contactName?: string;
    contactPhone?: string;
    isDefault?: boolean;
  }[];
  return rows.length ? rows : undefined;
}

function extraNum(extra: Record<string, unknown>, ...keys: string[]): number | undefined {
  for (const key of keys) {
    const raw = extra[key];
    if (raw == null || raw === '') continue;
    const n = Number(raw);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

/** 客商引用展示 → 下拉实体（含联系人快照等 extra，供单据表单自动带出） */
export function mapPartnerReferenceDisplayItem(item: ReferenceDisplayItem): {
  id: number;
  uuid?: string;
  code?: string;
  name?: string;
  contactPerson?: string;
  phone?: string;
  address?: string;
  deliveryAddress?: string;
  salesmanId?: number;
  salesmanName?: string;
  paymentTermsDays?: number;
  defaultPaymentMethodCode?: string;
  settlementTermsCode?: string;
  defaultCurrencyCode?: string;
  defaultExchangeRate?: number;
  revenueRecognitionOverride?: string;
  payableRecognitionOverride?: string;
  buyerId?: number;
  buyerName?: string;
} {
  const extra = (item.extra && typeof item.extra === 'object' ? item.extra : {}) as Record<
    string,
    unknown
  >;
  return {
    id: Number(item.id),
    uuid: item.uuid ?? undefined,
    code: item.code ?? undefined,
    name: item.name ?? undefined,
    contactPerson: extraStr(extra, 'contact_person', 'contactPerson'),
    phone: extraStr(extra, 'phone'),
    address: extraStr(extra, 'address'),
    deliveryAddress: extraStr(extra, 'delivery_address', 'deliveryAddress'),
    salesmanId: extraNum(extra, 'salesman_id', 'salesmanId'),
    salesmanName: extraStr(extra, 'salesman_name', 'salesmanName'),
    paymentTermsDays: extraNum(extra, 'payment_terms_days', 'paymentTermsDays'),
    defaultPaymentMethodCode: extraStr(
      extra,
      'default_payment_method_code',
      'defaultPaymentMethodCode',
    ),
    settlementTermsCode: extraStr(extra, 'settlement_terms_code', 'settlementTermsCode'),
    defaultCurrencyCode: extraStr(extra, 'default_currency_code', 'defaultCurrencyCode'),
    defaultExchangeRate: extraNum(extra, 'default_exchange_rate', 'defaultExchangeRate'),
    revenueRecognitionOverride: extraStr(
      extra,
      'revenue_recognition_override',
      'revenueRecognitionOverride',
    ),
    payableRecognitionOverride: extraStr(
      extra,
      'payable_recognition_override',
      'payableRecognitionOverride',
    ),
    buyerId: extraNum(extra, 'buyer_id', 'buyerId'),
    buyerName: extraStr(extra, 'buyer_name', 'buyerName'),
    contacts: mapPartnerContactsFromExtra(extra),
    addresses: mapPartnerAddressesFromExtra(extra),
  };
}

/** 宿主模块 resource（{app}:{module}） */
export function buildHostResource(app: string, module: string): string {
  return `${app.trim()}:${module.trim()}`.toLowerCase();
}

/** 是否具备资源 read（管理页） */
export function canReadReferenceResource(user: CurrentUser | undefined, resourceKey: string): boolean {
  const [read] = displayPermissionCodes(resourceKey);
  return hasPermission(user, read);
}
