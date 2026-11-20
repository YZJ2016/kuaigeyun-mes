/**
 * 字段权限掩码（与后端 PermissionPolicyService 两大类 + 列展开一致）
 */

export type FieldMaskLevel = 'full' | 'masked' | 'hidden';

export type UserFieldMaskMap = Record<string, Record<string, FieldMaskLevel>>;

const FIELD_KIND_AMOUNT = 'amount';
const FIELD_KIND_PARTY_NAME = 'party_name';

const AMOUNT_COLUMNS = new Set([
  'amount',
  'total_amount',
  'tax_amount',
  'untaxed_amount',
  'unit_price',
  'price',
  'amount_with_tax',
  'amount_without_tax',
]);

const PARTY_COLUMNS = new Set([
  'customer_name',
  'supplier_name',
  'default_supplier_id',
  'default_supplier_name',
]);

const FIELD_CANONICAL_ALIAS: Record<string, string> = {
  amountwithtax: 'amount_with_tax',
  amount_with_tax: 'amount_with_tax',
  amountwithouttax: 'amount_without_tax',
  amount_without_tax: 'amount_without_tax',
  untaxed_amount: 'amount_without_tax',
  taxamount: 'tax_amount',
  tax_amount: 'tax_amount',
  totalamount: 'total_amount',
  total_amount: 'total_amount',
  unitprice: 'unit_price',
  unit_price: 'unit_price',
  customername: 'customer_name',
  customer_name: 'customer_name',
  clientname: 'customer_name',
  client_name: 'customer_name',
  suppliername: 'supplier_name',
  supplier_name: 'supplier_name',
  defaultsupplierid: 'default_supplier_id',
  default_supplier_id: 'default_supplier_id',
  defaultsuppliername: 'default_supplier_name',
  default_supplier_name: 'default_supplier_name',
  partyname: FIELD_KIND_PARTY_NAME,
  party_name: FIELD_KIND_PARTY_NAME,
};

export function canonicalizeFieldName(raw: string): string {
  const snake = String(raw ?? '')
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[-\s]+/g, '_')
    .toLowerCase()
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
  const compact = snake.replace(/_/g, '');
  return FIELD_CANONICAL_ALIAS[snake] || FIELD_CANONICAL_ALIAS[compact] || snake;
}

export function resolvePolicyKind(fieldOrKind: string | undefined): string | undefined {
  const key = canonicalizeFieldName(fieldOrKind || '');
  if (!key) return undefined;
  if (key === FIELD_KIND_AMOUNT || key === FIELD_KIND_PARTY_NAME) return key;
  if (AMOUNT_COLUMNS.has(key)) return FIELD_KIND_AMOUNT;
  if (PARTY_COLUMNS.has(key)) return FIELD_KIND_PARTY_NAME;
  return undefined;
}

export function normalizeFieldMaskResource(resource: string): string {
  return String(resource ?? '').trim().toLowerCase();
}

function pickStricter(a: FieldMaskLevel | undefined, b: FieldMaskLevel | undefined): FieldMaskLevel | undefined {
  const priority: Record<FieldMaskLevel, number> = { full: 0, masked: 1, hidden: 2 };
  if (!a) return b;
  if (!b) return a;
  return priority[a] >= priority[b] ? a : b;
}

/** 解析用户对某资源某字段的有效掩码；无策略时返回 undefined */
export function resolveFieldMaskLevel(
  masks: UserFieldMaskMap | undefined,
  resource: string | undefined,
  fieldName: string | undefined,
): FieldMaskLevel | undefined {
  if (!masks || !resource?.trim() || !fieldName?.trim()) return undefined;
  const resKey = normalizeFieldMaskResource(resource);
  const fieldKey = canonicalizeFieldName(fieldName);
  const byColumn = masks[resKey]?.[fieldKey];
  const kind = resolvePolicyKind(fieldKey);
  const byKind = kind ? masks[resKey]?.[kind] : undefined;
  return pickStricter(byColumn, byKind);
}

export type AmountFieldVisibility = 'show' | 'mask' | 'hide';

/** AmountDisplay 与表单只读金额展示共用 */
export function resolveAmountFieldVisibility(
  masks: UserFieldMaskMap | undefined,
  resource: string | undefined,
  fieldName: string | undefined,
  legacyPricingAllowed: boolean,
): AmountFieldVisibility {
  const fieldMask = resolveFieldMaskLevel(masks, resource, fieldName || FIELD_KIND_AMOUNT);
  if (fieldMask === 'full') return 'show';
  if (fieldMask === 'masked') return 'mask';
  if (fieldMask === 'hidden') return 'hide';
  return legacyPricingAllowed ? 'show' : 'mask';
}
