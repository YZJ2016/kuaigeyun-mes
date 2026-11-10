/**
 * 表格单元格 → 纯文本。
 * 字符串默认原样保留（含编码/名称中的逗号）；仅千分位数字去逗号。
 */

import { spreadsheetNumericCompareText, spreadsheetPlainCellText } from './spreadsheetPreserveText';

export function spreadsheetNumberToPlainString(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') {
    return spreadsheetPlainCellText(value);
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '';
    const direct = value.toString();
    if (!direct.includes('e') && !direct.includes('E')) {
      return direct;
    }
    return value.toFixed(20).replace(/\.?0+$/, '') || '0';
  }
  if (typeof value === 'bigint') {
    return value.toString();
  }
  return spreadsheetPlainCellText(value);
}

/** 解析 Univer / xlsx 单元格对象：字符串 v 优先于数值 */
export function spreadsheetCellToPlainString(cell: unknown): string {
  if (cell === null || cell === undefined) return '';
  if (typeof cell === 'object') {
    const obj = cell as { v?: unknown; m?: unknown; value?: unknown; t?: unknown };
    // FORCE_STRING / 文本：v 为字符串时原样保全，禁止再 Number()
    if (typeof obj.v === 'string') {
      return spreadsheetPlainCellText(obj.v);
    }
    if (obj.v !== undefined && obj.v !== null && obj.v !== '') {
      return spreadsheetNumberToPlainString(obj.v);
    }
    if (typeof obj.m === 'string' && obj.m.trim() !== '') {
      return spreadsheetPlainCellText(obj.m);
    }
    if (obj.value !== undefined && obj.value !== null && obj.value !== '') {
      return spreadsheetNumberToPlainString(obj.value);
    }
    if (obj.m !== undefined && obj.m !== null && obj.m !== '') {
      return spreadsheetNumberToPlainString(obj.m);
    }
    return '';
  }
  return spreadsheetNumberToPlainString(cell);
}

/** xlsx SheetJS 单元格：数值型只用 v，不用 w */
export function xlsxCellToPlainString(cell: { t?: string; v?: unknown; w?: string } | undefined): string {
  if (!cell) return '';
  if (cell.t === 'n') {
    return spreadsheetNumberToPlainString(cell.v);
  }
  if (cell.v !== null && cell.v !== undefined && cell.v !== '') {
    return spreadsheetNumberToPlainString(cell.v);
  }
  if (cell.w != null && String(cell.w).trim() !== '') {
    return spreadsheetPlainCellText(cell.w);
  }
  return '';
}

/** 兼容旧调用：XML 原文优先 */
export function resolveXlsxNumericPlainString(
  cell: { t?: string; v?: unknown; w?: string } | undefined,
  rawXmlValue?: string | null,
): string {
  if (rawXmlValue != null && String(rawXmlValue).trim() !== '') {
    // 数值 XML 原文可能带千分位；编码列不应走到此分支
    return spreadsheetNumericCompareText(rawXmlValue);
  }
  return xlsxCellToPlainString(cell);
}
