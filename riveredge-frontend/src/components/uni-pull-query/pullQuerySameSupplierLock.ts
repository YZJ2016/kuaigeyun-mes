/** 多选取单：已选一行后，锁定同往来单位（供应商/客户），其它单位行不可再勾选。 */

export type PullQueryPartnerRow = {
  supplierId?: number;
  supplier_id?: number;
  customerId?: number;
  customer_id?: number;
  partnerName?: string;
  partner_name?: string;
  /** 轻财务候选常见字段；与 partnerName 等价作名称锚点 */
  supplier_name?: string;
  supplierName?: string;
  customer_name?: string;
  customerName?: string;
};

export function resolvePullQueryPartnerKey(row: PullQueryPartnerRow): string {
  const sid = Number(
    row.supplierId ?? row.supplier_id ?? row.customerId ?? row.customer_id ?? 0,
  );
  if (sid > 0) return `id:${sid}`;
  const name = String(
    row.partnerName
      ?? row.partner_name
      ?? row.supplierName
      ?? row.supplier_name
      ?? row.customerName
      ?? row.customer_name
      ?? '',
  ).trim();
  return name ? `name:${name}` : '';
}

export function resolvePullQueryAnchorPartnerKey<T extends PullQueryPartnerRow>(
  selectedRows: T[],
): string | null {
  if (!selectedRows.length) return null;
  const key = resolvePullQueryPartnerKey(selectedRows[0]);
  return key || null;
}

export function isPullRowBlockedByPartnerLock<T extends PullQueryPartnerRow>(
  row: T,
  anchorKey: string | null,
): boolean {
  if (!anchorKey) return false;
  const key = resolvePullQueryPartnerKey(row);
  if (!key) return false;
  return key !== anchorKey;
}

export function composePullRowDisabled<T extends PullQueryPartnerRow>(
  row: T,
  options: {
    baseDisabled?: (row: T) => boolean;
    selectedRows: T[];
  },
): boolean {
  if (options.baseDisabled?.(row)) return true;
  const anchor = resolvePullQueryAnchorPartnerKey(options.selectedRows);
  return isPullRowBlockedByPartnerLock(row, anchor);
}
