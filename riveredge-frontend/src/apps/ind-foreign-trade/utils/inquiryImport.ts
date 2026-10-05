import type { InquiryImportRow } from '../services/foreignTradeApi';

/** 询盘模板第一行，与 SpreadsheetML 文件表头一致。 */
export const INQUIRY_FILE_HEADERS = [
  'created_time',
  'campaign_name',
  'your_packaging_materials?example:_salt__25kg/bag',
  'what_is_your_required_production_capacity?example:_600_bags/hour',
  'phone_number',
  'email',
  'full_name',
  'company_name',
  'job_title',
] as const;

const HEADER_TO_FIELD: Record<(typeof INQUIRY_FILE_HEADERS)[number], keyof InquiryImportRow> = {
  created_time: 'created_time',
  campaign_name: 'campaign_name',
  'your_packaging_materials?example:_salt__25kg/bag': 'your_packaging_materials',
  'what_is_your_required_production_capacity?example:_600_bags/hour': 'required_production_capacity',
  phone_number: 'phone_number',
  email: 'email',
  full_name: 'full_name',
  company_name: 'company_name',
  job_title: 'job_title',
};

const SS_NS = 'urn:schemas-microsoft-com:office:spreadsheet';

export type InquiryParseResult =
  | { ok: true; rows: InquiryImportRow[] }
  | { ok: false; reason: 'empty' | 'header' | 'notSpreadsheet' };

function headersMatch(header: string[]): boolean {
  if (header.length < INQUIRY_FILE_HEADERS.length) return false;
  return INQUIRY_FILE_HEADERS.every((expected, index) => header[index] === expected);
}

export function rowsFromInquiryMatrix(header: string[], dataRows: string[][]): InquiryParseResult {
  const normalized = header.map((cell) => cell.trim());
  if (!headersMatch(normalized)) {
    return { ok: false, reason: 'header' };
  }
  const rows = dataRows
    .filter((line) => line.some((cell) => String(cell ?? '').trim() !== ''))
    .map((line) => {
      const row: InquiryImportRow = {};
      INQUIRY_FILE_HEADERS.forEach((headerName, index) => {
        const field = HEADER_TO_FIELD[headerName];
        const value = String(line[index] ?? '').trim();
        row[field] = value || undefined;
      });
      return row;
    });
  if (rows.length === 0) return { ok: false, reason: 'empty' };
  return { ok: true, rows };
}

export function parseInquiryTsv(text: string): InquiryParseResult {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return { ok: false, reason: 'empty' };
  const sep = lines[0].includes('\t') ? '\t' : ',';
  const matrix = lines.map((line) => line.split(sep).map((cell) => cell.trim()));
  return rowsFromInquiryMatrix(matrix[0], matrix.slice(1));
}

function spreadsheetCells(row: Element): string[] {
  const cells: string[] = [];
  let col = 0;
  const cellNodes = row.getElementsByTagNameNS(SS_NS, 'Cell');
  for (let i = 0; i < cellNodes.length; i += 1) {
    const cell = cellNodes.item(i);
    if (!cell) continue;
    const indexAttr = cell.getAttributeNS(SS_NS, 'Index');
    if (indexAttr) {
      const idx = Number(indexAttr) - 1;
      if (Number.isFinite(idx) && idx >= 0) col = idx;
    }
    const data = cell.getElementsByTagNameNS(SS_NS, 'Data').item(0);
    cells[col] = (data?.textContent || '').trim();
    col += 1;
  }
  return cells;
}

export function parseInquirySpreadsheetMl(xml: string): InquiryParseResult {
  const trimmed = xml.trim();
  if (!trimmed.startsWith('<') || !trimmed.includes('urn:schemas-microsoft-com:office:spreadsheet')) {
    return { ok: false, reason: 'notSpreadsheet' };
  }
  const doc = new DOMParser().parseFromString(trimmed, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length > 0) {
    return { ok: false, reason: 'notSpreadsheet' };
  }
  const rowNodes = doc.getElementsByTagNameNS(SS_NS, 'Row');
  if (rowNodes.length === 0) return { ok: false, reason: 'empty' };
  const matrix: string[][] = [];
  for (let i = 0; i < rowNodes.length; i += 1) {
    const row = rowNodes.item(i);
    if (row) matrix.push(spreadsheetCells(row));
  }
  return rowsFromInquiryMatrix(matrix[0] || [], matrix.slice(1));
}
