/** 仓储报表 API 台账主/副数量与 material_totals 解析 */

export type MaterialTotalBucket = {
  primary_quantity?: number;
  secondary_quantity?: number;
};

export function readMaterialTotalPrimary(value: number | MaterialTotalBucket | undefined): number {
  if (value == null) return 0;
  if (typeof value === 'number') return Number(value) || 0;
  return Number(value.primary_quantity ?? 0) || 0;
}

export function parseMaterialTotalsPrimary(
  totals: Record<string, number | MaterialTotalBucket> | undefined,
): Record<number, number> {
  const result: Record<number, number> = {};
  for (const [k, v] of Object.entries(totals ?? {})) {
    const id = parseInt(k, 10);
    if (!Number.isNaN(id)) result[id] = readMaterialTotalPrimary(v);
  }
  return result;
}

export function readInventoryRowPrimary(row: {
  primary_quantity?: number;
  quantity?: number;
}): number {
  if (row.primary_quantity != null) return Number(row.primary_quantity) || 0;
  return Number(row.quantity ?? 0) || 0;
}

export function readInventoryRowSecondary(row: {
  secondary_quantity?: number;
}): number {
  return Number(row.secondary_quantity ?? 0) || 0;
}
