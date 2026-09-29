/**
 * 导入表格中的日期单元格 → YYYY-MM-DD（业务日期）。
 * 兼容 Excel 序列号、ISO、斜杠/点分隔、YYYYMMDD。
 */

import { spreadsheetCellToPlainString } from './spreadsheetCellPlainString';

const EXCEL_EPOCH_UTC_MS = Date.UTC(1899, 11, 30);

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

function toIsoDateParts(year: number, month: number, day: number): string | null {
  if (
    !Number.isInteger(year) ||
    !Number.isInteger(month) ||
    !Number.isInteger(day) ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > 31
  ) {
    return null;
  }
  const probe = new Date(Date.UTC(year, month - 1, day));
  if (
    probe.getUTCFullYear() !== year ||
    probe.getUTCMonth() !== month - 1 ||
    probe.getUTCDate() !== day
  ) {
    return null;
  }
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

function excelSerialToIsoDate(serial: number): string | null {
  if (!Number.isFinite(serial) || serial < 0 || serial > 1_000_000) {
    return null;
  }
  const ms = EXCEL_EPOCH_UTC_MS + Math.round(serial) * 86_400_000;
  const d = new Date(ms);
  return toIsoDateParts(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
}

/**
 * 将单元格原文转为 YYYY-MM-DD；无法识别时返回 null。
 */
export function normalizeImportSpreadsheetDate(raw: unknown): string | null {
  if (raw instanceof Date && Number.isFinite(raw.getTime())) {
    return toIsoDateParts(raw.getFullYear(), raw.getMonth() + 1, raw.getDate());
  }

  const text = spreadsheetCellToPlainString(raw).trim();
  if (!text) return null;

  let head = text;
  const spaceIdx = head.search(/\s|T/);
  if (spaceIdx > 0) {
    head = head.slice(0, spaceIdx).trim();
  }

  const isoLead = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(head);
  if (isoLead) {
    return toIsoDateParts(Number(isoLead[1]), Number(isoLead[2]), Number(isoLead[3]));
  }

  const slashLead = /^(\d{4})[/\.](\d{1,2})[/\.](\d{1,2})$/.exec(head);
  if (slashLead) {
    return toIsoDateParts(Number(slashLead[1]), Number(slashLead[2]), Number(slashLead[3]));
  }

  if (/^\d{8}$/.test(head)) {
    return toIsoDateParts(
      Number(head.slice(0, 4)),
      Number(head.slice(4, 6)),
      Number(head.slice(6, 8)),
    );
  }

  if (/^\d+(\.\d+)?$/.test(head)) {
    return excelSerialToIsoDate(Number(head));
  }

  return null;
}
