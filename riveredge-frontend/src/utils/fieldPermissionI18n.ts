/**
 * 字段权限策略类展示名 i18n（与后端两大类 amount / party_name 对齐）
 */

/** 角色字段权限可配置的策略类 + 历史细字段（用于标签回退） */
export const FIELD_PERMISSION_CANONICAL_NAMES = new Set<string>([
  'amount',
  'party_name',
  'total_amount',
  'tax_amount',
  'untaxed_amount',
  'amount_with_tax',
  'amount_without_tax',
  'unit_price',
  'price',
  'customer_name',
  'supplier_name',
  'default_supplier_id',
  'default_supplier_name',
]);

/** 角色页策略类选项（两大类） */
export const FIELD_PERMISSION_KIND_OPTIONS = [
  { value: 'amount', labelKey: 'permission.fieldName.amount', defaultLabel: '金额' },
  {
    value: 'party_name',
    labelKey: 'permission.fieldName.party_name',
    defaultLabel: '客户/供应商名称',
  },
] as const;

export function resolveFieldPermissionLabel(
  fieldName: string | undefined,
  backendLabel: string | undefined | null,
  t: (key: string, opts?: { defaultValue?: string }) => string,
): string {
  const canonical = (fieldName || '').trim().toLowerCase();
  if (!canonical) {
    const label = (backendLabel || '').trim();
    return label || '—';
  }

  const i18nKey = `permission.fieldName.${canonical}`;
  const translated = t(i18nKey, { defaultValue: '' });
  if (translated && translated !== i18nKey) return translated;

  const label = (backendLabel || '').trim();
  return label || canonical;
}
