/**
 * 轻办公列表批量导入：复用工厂模板解析 + chunkedBulkImport，不另起 UI。
 */
import type { TFunction } from 'i18next';
import { List, Typography } from 'antd';
import { importInChunksViaPerItemCreate } from '../../../utils/chunkedBulkImport';
import { getAntdModal } from '../../../utils/antdAppApis';
import { resolveFactoryImportHeaderIndexMap } from '../../master-data/utils/factoryImportTemplate';

export type OaImportMessageApi = {
  warning: (msg: string) => void;
  error: (msg: string) => void;
  success: (msg: string) => void;
};

export type OaImportRowError = { row: number; message: string };

export function collectOaImportNonEmptyRows(data: unknown[][]): {
  headers: string[];
  rows: unknown[][];
} | null {
  if (!data || data.length === 0) return null;
  const headers = (data[0] || []).map((h) => String(h ?? '').trim());
  const rows = data.slice(2).filter((row) => {
    if (!Array.isArray(row) || row.length === 0) return false;
    return row.some((cell) => String(cell ?? '').trim() !== '');
  });
  return { headers, rows };
}

export function buildOaImportCellReader(
  headers: string[],
  importHeaderMap: Record<string, string>,
): (row: unknown[], field: string) => string {
  const headerIndexMap = resolveFactoryImportHeaderIndexMap(headers, importHeaderMap);
  return (row, field) => {
    const idx = headerIndexMap[field];
    if (idx === undefined || !Array.isArray(row)) return '';
    return String(row[idx] ?? '').trim();
  };
}

export function resolveOaOptionValue(
  raw: string,
  options: Array<{ label: string; value: string }>,
): string | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  const byValue = options.find((o) => o.value === trimmed);
  if (byValue) return byValue.value;
  const byLabel = options.find((o) => o.label === trimmed);
  return byLabel?.value;
}

/** 按员工编号或姓名精确匹配（编号优先）。 */
export function resolveOaEmployeeId(
  employeeCode: string,
  employeeName: string,
  employees: Array<{ id: number; employee_code?: string | null; full_name?: string | null }>,
): number | undefined {
  const code = employeeCode.trim();
  if (code) {
    const byCode = employees.find(
      (e) => String(e.employee_code || '').trim().toUpperCase() === code.toUpperCase(),
    );
    if (byCode) return Number(byCode.id);
  }
  const name = employeeName.trim();
  if (!name) return undefined;
  const matches = employees.filter((e) => String(e.full_name || '').trim() === name);
  if (matches.length === 1) return Number(matches[0].id);
  return undefined;
}

export async function runOaChunkedCreateImport(options: {
  t: TFunction;
  messageApi: OaImportMessageApi;
  items: Record<string, unknown>[];
  createOne: (item: Record<string, unknown>) => Promise<unknown>;
  title: string;
  successKey?: string;
}): Promise<boolean> {
  const { t, messageApi, items, createOne, title, successKey } = options;
  if (items.length === 0) {
    messageApi.warning(t('app.kuaioa.import.noRows'));
    return false;
  }
  try {
    const result = await importInChunksViaPerItemCreate({
      items,
      createOne,
      title,
      chunkSize: 50,
      concurrency: 4,
      rowNumberForIndex: (i) => i + 3,
      showResultModal: false,
    });
    if (result.failureCount > 0) {
      getAntdModal().warning({
        title: t('app.kuaioa.import.partialTitle'),
        width: 600,
        content: (
          <div>
            <p>
              <strong>
                {t('app.kuaioa.import.partialIntro', {
                  success: result.successCount,
                  failure: result.failureCount,
                })}
              </strong>
            </p>
            <List
              size="small"
              dataSource={result.errors}
              renderItem={(item) => (
                <List.Item>
                  <Typography.Text type="danger">
                    {t('app.kuaioa.import.rowError', {
                      row: item.row,
                      message: item.error,
                    })}
                  </Typography.Text>
                </List.Item>
              )}
            />
          </div>
        ),
      });
    } else {
      messageApi.success(
        t(successKey || 'app.kuaioa.import.success', { count: result.successCount }),
      );
    }
    return result.failureCount === 0;
  } catch (error: unknown) {
    const err = error as { message?: string };
    messageApi.error(err?.message || t('common.importFailed'));
    return false;
  }
}

export function showOaImportValidationErrors(
  t: TFunction,
  errors: OaImportRowError[],
): void {
  getAntdModal().warning({
    title: t('app.kuaioa.import.validationTitle'),
    width: 600,
    content: (
      <div>
        <p>{t('app.kuaioa.import.validationIntro')}</p>
        <List
          size="small"
          dataSource={errors}
          renderItem={(item) => (
            <List.Item>
              <Typography.Text type="danger">
                {t('app.kuaioa.import.rowError', {
                  row: item.row,
                  message: item.message,
                })}
              </Typography.Text>
            </List.Item>
          )}
        />
      </div>
    ),
  });
}
