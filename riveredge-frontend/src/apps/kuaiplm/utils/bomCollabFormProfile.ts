/**
 * BOM 协同 form-profile：双轨分区 + 动态明细列 + extension_payload。
 */

import type { TFunction } from 'i18next';
import type { ColumnsType } from 'antd/es/table';
import type { BomCollabFormProfile, BomCollabLine } from '../services/bom-collaboration';

export type BomCollabProfileColumn = {
  key: string;
  label: string;
  sort?: number;
  required?: boolean;
  width?: number;
  type?: string;
};

export const BOM_LINE_DIRECT_KEYS = new Set([
  'material_id',
  'material_code',
  'material_name',
  'qty',
  'unit',
  'remarks',
]);

const DEFAULT_LINE_COLUMNS: BomCollabProfileColumn[] = [
  { key: 'material_code', label: '物料编码', sort: 10, required: true, width: 140 },
  { key: 'material_name', label: '物料名称', sort: 20, required: true, width: 160 },
  { key: 'qty', label: '用量', sort: 30, width: 100, type: 'decimal' },
  { key: 'unit', label: '单位', sort: 40, width: 80 },
];

export function isDecimalLineColumn(col: BomCollabProfileColumn): boolean {
  return col.type === 'decimal' || col.key === 'qty';
}

export function buildEmptyLineRecord(columns: BomCollabProfileColumn[]): Record<string, unknown> {
  const line: Record<string, unknown> = {};
  for (const col of columns) {
    line[col.key] = isDecimalLineColumn(col) ? null : '';
  }
  return line;
}

export function sortedLineColumns(profile: BomCollabFormProfile | null): BomCollabProfileColumn[] {
  const raw = profile?.line_columns?.length ? profile.line_columns : DEFAULT_LINE_COLUMNS;
  return [...raw]
    .filter((c) => c?.key)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    .map((c) => ({
      key: String(c.key),
      label: String(c.label || c.key),
      sort: c.sort,
      required: c.required,
      width: c.width,
      type: c.type,
    }));
}

export function getLineCellValue(
  line: BomCollabLine | Record<string, unknown>,
  columnKey: string,
): unknown {
  const record = line as Record<string, unknown>;
  if (
    record[columnKey] !== undefined &&
    record[columnKey] !== null &&
    record[columnKey] !== ''
  ) {
    return record[columnKey];
  }
  const payload = record.extension_payload as Record<string, unknown> | undefined;
  return payload?.[columnKey];
}

export function flattenLineForForm(line: BomCollabLine | Record<string, unknown>): Record<string, unknown> {
  const base: Record<string, unknown> = { ...(line as Record<string, unknown>) };
  const payload = (base.extension_payload as Record<string, unknown> | undefined) || {};
  for (const [key, value] of Object.entries(payload)) {
    if (base[key] === undefined || base[key] === null || base[key] === '') {
      base[key] = value;
    }
  }
  return base;
}

export function prepareLineForApi(
  line: Record<string, unknown>,
  columns: BomCollabProfileColumn[],
): BomCollabLine {
  const columnKeys = new Set(columns.map((c) => c.key));
  const direct: Record<string, unknown> = {};
  const overflow: Record<string, unknown> = {};

  for (const col of columns) {
    const value = line[col.key];
    if (value === undefined || value === '') continue;
    if (BOM_LINE_DIRECT_KEYS.has(col.key)) {
      direct[col.key] = value;
    } else if (columnKeys.has(col.key)) {
      overflow[col.key] = value;
    }
  }

  for (const key of BOM_LINE_DIRECT_KEYS) {
    if (line[key] !== undefined && line[key] !== '' && direct[key] === undefined) {
      direct[key] = line[key];
    }
  }

  return {
    material_id: (direct.material_id as number | null | undefined) ?? null,
    material_code: String(direct.material_code || '').trim(),
    material_name: String(direct.material_name || '').trim(),
    qty: direct.qty as BomCollabLine['qty'],
    unit: (direct.unit as string | null | undefined) ?? null,
    remarks: (direct.remarks as string | null | undefined) ?? null,
    extension_payload: Object.keys(overflow).length ? overflow : null,
  } as BomCollabLine;
}

export function buildLineDetailColumns(
  profile: BomCollabFormProfile | null,
  t: TFunction,
): Array<{ title: string; dataIndex: string; width?: number; render?: (_: unknown, row: BomCollabLine) => string }> {
  return sortedLineColumns(profile).map((col) => ({
    title: col.label,
    dataIndex: col.key,
    width: col.width,
    render: (_: unknown, row: BomCollabLine) => {
      const value = getLineCellValue(row, col.key);
      if (value === undefined || value === null || value === '') return '-';
      return String(value);
    },
  }));
}

export type BomLineColumnRender = (
  col: BomCollabProfileColumn,
  index: number,
  t: TFunction,
) => ColumnsType[number]['render'];
