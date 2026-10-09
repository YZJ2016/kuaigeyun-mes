/**
 * BOM 协同明细：Excel 模板列与解析（按 form-profile line_columns）。
 */

import type { ExportXlsxColumn } from '../../../utils/exportRecordsXlsx';
import {
  buildEmptyLineRecord,
  isDecimalLineColumn,
  type BomCollabProfileColumn,
} from './bomCollabFormProfile';

const MATERIAL_CODE_ALIASES = [
  '物料编码',
  '物料编码/12位代码',
  '料号',
  '12位代码',
  'material_code',
  'MaterialCode',
];

const MATERIAL_NAME_ALIASES = [
  '物料名称',
  '物料名称/描述',
  '描述',
  'material_name',
  'MaterialName',
];

function cellRaw(row: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(row, key)) {
      return row[key];
    }
  }
  const lowered = new Map(
    Object.keys(row).map((k) => [k.trim().toLowerCase(), k] as const),
  );
  for (const key of keys) {
    const hit = lowered.get(key.trim().toLowerCase());
    if (hit != null) return row[hit];
  }
  return undefined;
}

function cellText(row: Record<string, unknown>, keys: string[]): string {
  const raw = cellRaw(row, keys);
  if (raw == null) return '';
  return String(raw).trim();
}

function parseQty(raw: unknown): number | null {
  if (raw == null || raw === '') return null;
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  const text = String(raw).trim().replace(/,/g, '');
  if (!text) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

export function buildBomLineTemplateColumns(
  columns: BomCollabProfileColumn[],
): ExportXlsxColumn[] {
  return columns.map((c) => ({ key: c.key, title: c.label }));
}

export function buildBomLineTemplateSample(
  columns: BomCollabProfileColumn[],
): Record<string, unknown> {
  const row = buildEmptyLineRecord(columns);
  for (const col of columns) {
    if (col.key === 'material_code') {
      row[col.key] = 'MAT-001';
    } else if (col.key === 'material_name') {
      row[col.key] = '示例物料';
    } else if (isDecimalLineColumn(col)) {
      row[col.key] = 1;
    } else if (col.key === 'unit') {
      row[col.key] = 'PCS';
    }
  }
  return row;
}

export type ParseBomLinesResult =
  | { ok: true; lines: Record<string, unknown>[] }
  | { ok: false; error: 'empty' | 'row_invalid'; code?: string };

export function parseBomCollabLinesFromRows(
  rows: Record<string, unknown>[],
  columns: BomCollabProfileColumn[],
): ParseBomLinesResult {
  const lines: Record<string, unknown>[] = [];
  for (const row of rows) {
    const line = buildEmptyLineRecord(columns);
    for (const col of columns) {
      const aliases =
        col.key === 'material_code'
          ? [col.label, col.key, ...MATERIAL_CODE_ALIASES]
          : col.key === 'material_name'
            ? [col.label, col.key, ...MATERIAL_NAME_ALIASES]
            : [col.label, col.key];
      if (isDecimalLineColumn(col)) {
        line[col.key] = parseQty(cellRaw(row, aliases));
      } else {
        line[col.key] = cellText(row, aliases);
      }
    }
    const code = String(line.material_code ?? '').trim();
    const name = String(line.material_name ?? '').trim();
    if (!code && !name) continue;
    if (!code || !name) {
      return { ok: false, error: 'row_invalid', code: code || '-' };
    }
    lines.push(line);
  }
  if (!lines.length) {
    return { ok: false, error: 'empty' };
  }
  return { ok: true, lines };
}
