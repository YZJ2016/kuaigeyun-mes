import type { ColumnType } from 'antd/es/table';

export function pullQueryColumnDataIndex(col: {
  dataIndex?: unknown;
  key?: string | number;
}): string | undefined {
  const di = col.dataIndex;
  if (typeof di === 'string') return di;
  if (Array.isArray(di) && di.length) return String(di[di.length - 1]);
  if (col.key != null) return String(col.key);
  return undefined;
}

/** 物料组：编码 → 名称 → 规格 → 当前库存（壳自动插库存时用） */
export function resolvePullCurrentStockInsertIndex(
  columns: ColumnType<unknown>[],
): number {
  const find = (name: string) =>
    columns.findIndex((col) => pullQueryColumnDataIndex(col) === name);
  const specIdx = find('material_spec');
  if (specIdx >= 0) return specIdx + 1;
  const nameIdx = find('material_name');
  if (nameIdx >= 0) return nameIdx + 1;
  const codeIdx = find('material_code');
  if (codeIdx >= 0) return codeIdx + 1;
  return columns.length;
}

export function columnsHavePullMaterialFields(columns: ColumnType<unknown>[]): boolean {
  return columns.some((col) => {
    const di = pullQueryColumnDataIndex(col);
    return di === 'material_code' || di === 'material_name' || di === 'material_spec';
  });
}