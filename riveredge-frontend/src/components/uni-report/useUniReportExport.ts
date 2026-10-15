import { useCallback } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import type { ProColumns } from '@ant-design/pro-components';
import { exportDomainReport, type ReportParams } from '../../apps/kuaizhizao/services/reports';
import type { UniReportExportConfig } from './types';
import { todaySiteDateString } from '../../utils/format';
import { downloadFile } from '../../utils/fileDownload';
import { downloadRecordsAsXlsx } from '../../utils/exportRecordsXlsx';
import { buildReportCsv, buildReportHtml, selectReportExportRows } from './reportExportData';

function downloadCsv(filename: string, headers: string[], rows: Record<string, unknown>[], keys: string[]) {
  downloadFile(new Blob([buildReportCsv(headers, keys, rows)], { type: 'text/csv;charset=utf-8' }), filename);
}

export type UseUniReportExportOptions = {
  title: string;
  exportConfig?: UniReportExportConfig;
  columns: ProColumns[];
  getFilters: () => ReportParams;
  rowKey?: string;
  getAllRows?: () => Promise<Record<string, unknown>[]>;
  exportAllExcel?: (filters: Record<string, unknown>) => Promise<void>;
};

export function useUniReportExport(options: UseUniReportExportOptions) {
  const { message } = App.useApp();
  const { t } = useTranslation();
  const { title, exportConfig, columns, getFilters, rowKey = 'id', getAllRows, exportAllExcel } = options;

  const exportableKeys = columns
    .filter((c) => c.dataIndex && !c.hideInTable)
    .map((c) => String(c.dataIndex));

  const exportableTitles = columns
    .filter((c) => c.dataIndex && !c.hideInTable)
    .map((c) => String(c.title ?? c.dataIndex));

  return useCallback(
    async (
      type: 'selected' | 'currentPage' | 'all',
      selectedRowKeys?: React.Key[],
      currentPageData?: Record<string, unknown>[],
      format: 'csv' | 'excel' | 'html' = 'csv',
    ) => {
      const dateStr = todaySiteDateString();
      const baseName = `${title}-${dateStr}.csv`;

      if (getAllRows || (format === 'excel' && exportAllExcel)) {
        const hide = message.loading(t('components.uniReport.exporting'), 0);
        try {
          if (format === 'excel' && type === 'all' && exportAllExcel) {
            await exportAllExcel({ ...getFilters() });
          } else {
            const rows = type === 'all'
              ? await getAllRows!()
              : selectReportExportRows(type, selectedRowKeys, currentPageData, rowKey);
            if (!rows.length) {
              message.warning(t('components.uniReport.exportEmpty'));
              return;
            }
            if (format === 'html') {
              downloadFile(new Blob([buildReportHtml(title, exportableTitles, exportableKeys, rows)], { type: 'text/html;charset=utf-8' }), `${title}-${dateStr}.html`);
            } else if (format === 'excel') {
              await downloadRecordsAsXlsx(rows, exportableKeys.map((key, index) => ({ key, title: exportableTitles[index] })), `${title}-${dateStr}.xlsx`);
            } else {
              downloadFile(new Blob([buildReportCsv(exportableTitles, exportableKeys, rows)], { type: 'text/csv;charset=utf-8' }), baseName);
            }
          }
          message.success(t('components.uniReport.exportSuccess', { title }));
        } catch (error) {
          message.error(t('components.uniReport.exportFailed', { message: (error as Error).message }));
        } finally {
          hide();
        }
        return;
      }

      if (type === 'all') {
        if (!exportConfig?.domain || !exportConfig?.reportType) {
          message.warning(t('components.uniReport.exportNotConfigured'));
          return;
        }
        const hide = message.loading(t('components.uniReport.exporting'), 0);
        try {
          await exportDomainReport(exportConfig.domain, {
            report_type: exportConfig.reportType,
            ...getFilters(),
          });
          hide();
          message.success(t('components.uniReport.exportSuccess', { title }));
        } catch (e) {
          hide();
          message.error(t('components.uniReport.exportFailed', { message: (e as Error).message }));
        }
        return;
      }

      const rows = selectReportExportRows(type, selectedRowKeys, currentPageData, rowKey);
      if (!rows.length) {
        message.warning(t('components.uniReport.exportEmpty'));
        return;
      }
      downloadCsv(baseName, exportableTitles, rows, exportableKeys);
      message.success(t('components.uniReport.exportSuccess', { title }));
    },
    [columns, exportConfig, exportableKeys, exportableTitles, getFilters, getAllRows, exportAllExcel, rowKey, message, t, title],
  );
}

export default useUniReportExport;
