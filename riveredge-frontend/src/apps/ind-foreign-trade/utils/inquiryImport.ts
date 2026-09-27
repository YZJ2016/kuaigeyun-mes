import type { InquiryImportRow } from '../services/foreignTradeApi';

export const INQUIRY_IMPORT_HEADERS = [
  'created_time',
  'campaign_name',
  'your_packaging_materials',
  'required_production_capacity',
  'phone_number',
  'email',
  'full_name',
  'company_name',
  'job_title',
] as const;

export function parseInquiryTsv(text: string): InquiryImportRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];
  const first = lines[0].split(/\t|,/);
  const hasHeader = INQUIRY_IMPORT_HEADERS.some((h) =>
    first.map((c) => c.trim().toLowerCase()).includes(h),
  );
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const sep = lines[0].includes('\t') ? '\t' : ',';
  return dataLines.map((line) => {
    const cells = line.split(sep).map((c) => c.trim());
    const row: InquiryImportRow = {};
    INQUIRY_IMPORT_HEADERS.forEach((key, i) => {
      row[key] = cells[i] || undefined;
    });
    return row;
  });
}
