/**
 * 列表导出统一为 XLSX（禁止 JSON Blob 下载）。
 * 编码/名称/电话等身份列强制文本，避免 Excel 吞前导零或把特殊字符当公式。
 */

export type ExportXlsxColumn = {
  /** 记录字段名；支持 a.b 点路径 */
  key: string;
  title: string;
  /** 强制按文本写出（默认对 code/name/phone 等键自动开启） */
  text?: boolean;
};

function getByPath(record: Record<string, unknown>, key: string): unknown {
  if (!key.includes('.')) return record[key];
  let cur: unknown = record;
  for (const part of key.split('.')) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function cellValue(value: unknown): string | number | boolean {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value;
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? '' : value.toISOString();
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '';
    if (value.every((v) => v == null || ['string', 'number', 'boolean'].includes(typeof v))) {
      return value.map((v) => (v == null ? '' : String(v))).join(', ');
    }
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** 身份/文案列：默认按文本导出，避免 SheetJS/Excel 类型推断破坏编码 */
export function isExportTextColumnKey(key: string): boolean {
  const k = key.trim().toLowerCase().replace(/\./g, '_');
  if (!k) return false;
  if (
    /(^|_)(code|name|phone|mobile|tel|fax|address|spec|sku|barcode|notes?|remark|email|uuid|id_?card|contact)(_|$)/.test(
      k,
    )
  ) {
    return true;
  }
  return /(code|name|phone|address|spec|notes|remark|email)$/.test(k);
}

function inferColumns(records: Record<string, unknown>[]): ExportXlsxColumn[] {
  const keySet = new Set<string>();
  for (const record of records.slice(0, 80)) {
    for (const [key, value] of Object.entries(record)) {
      if (value != null && typeof value === 'object' && !(value instanceof Date) && !Array.isArray(value)) {
        continue;
      }
      if (
        Array.isArray(value) &&
        value.some((item) => item != null && typeof item === 'object' && !(item instanceof Date))
      ) {
        continue;
      }
      keySet.add(key);
    }
  }
  const preferred = [
    'code',
    'name',
    'status',
    'type',
    'category',
    'created_at',
    'updated_at',
  ];
  const keys = [...keySet];
  keys.sort((a, b) => {
    const ia = preferred.indexOf(a);
    const ib = preferred.indexOf(b);
    if (ia >= 0 || ib >= 0) {
      if (ia < 0) return 1;
      if (ib < 0) return -1;
      return ia - ib;
    }
    return a.localeCompare(b);
  });
  return keys.map((key) => ({ key, title: key }));
}

/**
 * 将对象数组导出为 XLSX 并触发下载。
 * 调用约定：`downloadRecordsAsXlsx(rows, columns, fileName)`。
 */
export async function downloadRecordsAsXlsx(
  records: Array<Record<string, unknown>>,
  columnsOrFileName: ExportXlsxColumn[] | string,
  fileNameOrOptions?: string | { columns?: ExportXlsxColumn[]; sheetName?: string; textKeys?: string[] },
): Promise<void> {
  if (!records.length) {
    throw new Error('没有可导出的数据');
  }
  let columns: ExportXlsxColumn[];
  let fileName: string;
  let sheetName = '导出数据';
  let extraTextKeys: string[] = [];
  if (Array.isArray(columnsOrFileName)) {
    columns = columnsOrFileName;
    fileName = typeof fileNameOrOptions === 'string' ? fileNameOrOptions : 'export';
  } else {
    fileName = columnsOrFileName;
    const options =
      fileNameOrOptions && typeof fileNameOrOptions === 'object' ? fileNameOrOptions : undefined;
    columns = options?.columns?.length ? options.columns : inferColumns(records);
    if (options?.sheetName) sheetName = options.sheetName;
    if (options?.textKeys?.length) extraTextKeys = options.textKeys;
  }

  const textKeySet = new Set([
    ...columns
      .filter((c) => c.text === true || (c.text !== false && isExportTextColumnKey(c.key)))
      .map((c) => c.key),
    ...extraTextKeys,
  ]);

  const XLSX = await import('xlsx');
  const header = columns.map((c) => c.title);
  const body = records.map((record) =>
    columns.map((col) => {
      const raw = cellValue(getByPath(record, col.key));
      if (textKeySet.has(col.key)) {
        return raw == null || raw === '' ? '' : String(raw);
      }
      return raw;
    }),
  );
  const aoa = [header, ...body];
  const sheet = XLSX.utils.aoa_to_sheet(aoa);

  const textColIndexes = columns
    .map((col, idx) => (textKeySet.has(col.key) ? idx : -1))
    .filter((idx) => idx >= 0);

  for (let r = 1; r < aoa.length; r += 1) {
    for (const c of textColIndexes) {
      const addr = XLSX.utils.encode_cell({ r, c });
      const cell = sheet[addr] as { t?: string; v?: unknown; z?: string } | undefined;
      if (!cell) continue;
      const s = cell.v == null || cell.v === '' ? '' : String(cell.v);
      sheet[addr] = { t: 's', v: s, z: '@' };
    }
  }

  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, sheetName);
  const safeName = fileName.endsWith('.xlsx') ? fileName : `${fileName}.xlsx`;
  XLSX.writeFile(workbook, safeName);
}
