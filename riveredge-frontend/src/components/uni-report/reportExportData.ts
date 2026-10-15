type Row = Record<string, unknown>;

/** 分页读取完整报表，避免以当前页或接口单页上限冒充全量。 */
export async function fetchAllReportRows(
  execute: (filters: Row) => Promise<{ data?: unknown[]; total?: number; success?: boolean }>,
  filters: Row,
  pageSize = 1000,
): Promise<Row[]> {
  const rows: Row[] = [];
  for (;;) {
    const result = await execute({ ...filters, limit: pageSize, offset: rows.length });
    if (result.success === false) throw new Error('报表导出失败');
    const page = (result.data ?? []) as Row[];
    rows.push(...page);
    if (result.total != null && rows.length >= result.total) return rows;
    if (!page.length) {
      if (result.total != null && rows.length < result.total) throw new Error('报表数据不完整，请刷新后重试');
      return rows;
    }
    if (result.total == null && page.length < pageSize) return rows;
  }
}

export function selectReportExportRows(
  scope: 'selected' | 'currentPage' | 'all',
  keys: (string | number | bigint)[] = [],
  rows: Row[] = [],
  rowKey = 'id',
): Row[] {
  if (scope !== 'selected') return rows;
  const selected = new Set(keys.map(String));
  return rows.filter((row) => selected.has(String(row[rowKey] ?? '')));
}

export function buildReportCsv(headers: string[], keys: string[], rows: Row[]): string {
  const cell = (value: unknown) => {
    const text = String(value ?? '');
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return '\ufeff' + [headers.map(cell).join(','), ...rows.map((row) => keys.map((key) => cell(row[key])).join(','))].join('\r\n');
}

export function buildReportHtml(title: string, headers: string[], keys: string[], rows: Row[]): string {
  const escape = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escape(title)}</title><style>body{font-family:sans-serif;padding:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:6px;text-align:left}@media print{body{padding:0}}</style></head><body><h1>${escape(title)}</h1><table><thead><tr>${headers.map((h) => `<th>${escape(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${keys.map((key) => `<td>${escape(row[key])}</td>`).join('')}</tr>`).join('')}</tbody></table></body></html>`;
}
