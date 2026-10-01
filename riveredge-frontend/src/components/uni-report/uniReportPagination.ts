import type { PaginationProps } from 'antd';

import { resolveDefaultTablePageSize as resolveDefaultTablePageSizeShared } from '../../utils/resolveDefaultTablePageSize';

/** 报表「全部」分页：与后端 REPORT_LIST_MAX_LIMIT 一致 */
export const UNI_REPORT_PAGE_SIZE_ALL = 10_000;

export const UNI_REPORT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100, UNI_REPORT_PAGE_SIZE_ALL] as const;

/** 与 UniTable 一致：显式偏好 > 站点配置 > 20（真源 utils/resolveDefaultTablePageSize） */
export function resolveDefaultTablePageSize(override?: number): number {
  return resolveDefaultTablePageSizeShared(override);
}

export function buildUniReportTablePagination(
  t: (key: string, options?: Record<string, unknown>) => string,
  defaultPageSize?: number,
): PaginationProps {
  const resolvedDefaultPageSize = resolveDefaultTablePageSize(defaultPageSize);
  return {
    defaultPageSize: resolvedDefaultPageSize,
    showSizeChanger: {
      options: UNI_REPORT_PAGE_SIZE_OPTIONS.map((size) => ({
        value: size,
        label:
          size === UNI_REPORT_PAGE_SIZE_ALL
            ? t('components.uniReport.pageSizeAll')
            : t('components.uniReport.pageSizePerPage', { size }),
      })),
    },
    showQuickJumper: true,
    showTotal: (total: number, range: [number, number]) =>
      t('components.uniTable.paginationTotal', { total, start: range[0], end: range[1] }),
  };
}
