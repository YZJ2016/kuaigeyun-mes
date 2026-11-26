/** 单元格是否有可见内容 */
export function isImportCellNonEmpty(cell: unknown): boolean {
  return cell !== null && cell !== undefined && String(cell).trim() !== '';
}

/**
 * 是否视为有效导入数据行。
 * - 完全空白：否
 * - 仅一格有值且不在首列：否（常见粘贴残留 / 幽灵行，不进预检）
 * - 首列有值，或至少两格有值：是
 */
export function isMeaningfulImportRow(row: unknown[] | null | undefined): boolean {
  if (!Array.isArray(row) || row.length === 0) return false;
  let nonEmptyCount = 0;
  for (let i = 0; i < row.length; i += 1) {
    if (isImportCellNonEmpty(row[i])) nonEmptyCount += 1;
  }
  if (nonEmptyCount === 0) return false;
  if (isImportCellNonEmpty(row[0])) return true;
  return nonEmptyCount >= 2;
}

export type ImportDataRowEntry = {
  /** 1-based 表行号（与表格行号一致） */
  sheetRow: number;
  cells: any[];
};

/** 从完整导入二维表中取出数据行（默认跳过表头 + 示例行），并保留真实表行号 */
export function getImportDataRowEntries(
  data: any[][],
  dataStartRow = 2,
): ImportDataRowEntry[] {
  const out: ImportDataRowEntry[] = [];
  for (let i = dataStartRow; i < data.length; i += 1) {
    const row = data[i];
    if (!isMeaningfulImportRow(row)) continue;
    out.push({ sheetRow: i + 1, cells: row as any[] });
  }
  return out;
}

/** 从完整导入二维表中取出数据行（默认跳过表头 + 示例行） */
export function getImportDataRows(data: any[][], dataStartRow = 2): any[][] {
  return getImportDataRowEntries(data, dataStartRow).map((e) => e.cells);
}

/** 去掉尾部全空列，便于预览展示 */
export function trimImportTableColumns(
  headers: any[],
  rows: any[][],
): { headers: string[]; rows: string[][] } {
  const headerCells = headers.map((h) => String(h ?? ''));
  let maxCol = Math.max(
    headerCells.length - 1,
    ...rows.map((r) => (Array.isArray(r) ? r.length - 1 : -1)),
  );
  while (maxCol >= 0) {
    const headerEmpty = !headerCells[maxCol]?.trim();
    const colEmpty = rows.every((r) => !String(r?.[maxCol] ?? '').trim());
    if (!headerEmpty || !colEmpty) break;
    maxCol -= 1;
  }
  const count = Math.max(0, maxCol + 1);
  return {
    headers: headerCells.slice(0, count),
    rows: rows.map((r) =>
      Array.from({ length: count }, (_, i) =>
        r?.[i] === null || r?.[i] === undefined ? '' : String(r[i]),
      ),
    ),
  };
}

export function buildImportPreviewTableSource(options: {
  data: any[][];
  dataStartRow?: number;
  maxPreviewRows?: number;
}): {
  headers: string[];
  previewRows: string[][];
  /** 与 previewRows 一一对应的 1-based 表行号 */
  previewSheetRows: number[];
  totalDataRows: number;
  previewCount: number;
} {
  const { data, dataStartRow = 2, maxPreviewRows = 10 } = options;
  const headerRow = data[0] ?? [];
  const entries = getImportDataRowEntries(data, dataStartRow);
  const { headers, rows } = trimImportTableColumns(
    headerRow,
    entries.map((e) => e.cells),
  );
  const previewRows = rows.slice(0, maxPreviewRows);
  const previewSheetRows = entries.slice(0, maxPreviewRows).map((e) => e.sheetRow);
  return {
    headers,
    previewRows,
    previewSheetRows,
    totalDataRows: rows.length,
    previewCount: previewRows.length,
  };
}
