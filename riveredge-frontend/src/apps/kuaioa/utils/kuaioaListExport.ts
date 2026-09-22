import type { Key } from 'react';
import {
  downloadRecordsAsXlsx,
  type ExportXlsxColumn,
} from '../../../utils/exportRecordsXlsx';
import type { UniExportScope } from '../../../components/uni-export/UniExportMenuButton';

type ListResult = { items: Record<string, unknown>[]; total: number };

export async function runKuaioaListExport(options: {
  type: UniExportScope;
  keys?: Key[];
  pageData?: Record<string, unknown>[];
  listFn: (params?: Record<string, unknown>) => Promise<ListResult>;
  columns: ExportXlsxColumn[];
  filename: string;
  messageApi: { warning: (msg: string) => void };
  noDataText: string;
}): Promise<void> {
  const { type, keys, pageData, listFn, columns, filename, messageApi, noDataText } = options;
  let items: Record<string, unknown>[] =
    type === 'currentPage' && pageData?.length ? pageData : (await listFn()).items;
  if (type === 'selected' && keys?.length) {
    items = items.filter((row) => keys.includes(Number(row.id)));
  }
  if (items.length === 0) {
    messageApi.warning(noDataText);
    return;
  }
  await downloadRecordsAsXlsx(items, columns, filename);
}
