import type { PaginationProps } from 'antd';

import { useConfigStore } from '../../stores/configStore';
import { useUserPreferenceStore } from '../../stores/userPreferenceStore';

/** 报表「全部」分页：与后端 REPORT_LIST_MAX_LIMIT 一致 */
export const UNI_REPORT_PAGE_SIZE_ALL = 10_000;

export const UNI_REPORT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100, UNI_REPORT_PAGE_SIZE_ALL] as const;

/** 与 UniTable 一致：用户偏好 > 站点配置 > 20 */
export function resolveDefaultTablePageSize(override?: number): number {
  if (override != null && override > 0) {
    return override;
  }
  const getPreference = useUserPreferenceStore.getState().getPreference;
  const getConfig = useConfigStore.getState().getConfig;
  return getPreference('ui.default_page_size', getConfig('ui.default_page_size', 20));
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
