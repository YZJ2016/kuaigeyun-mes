/**
 * 系统报表预览。config 模式交给 UniReport（内部调用 executeReport，打印走 useUniReportPrint）。
 * 全量 Excel 另请求星报表后端生成工作簿。
 * 通过 datasetExecute 透传同一 executeReport，并记录最近一次筛选用于导出。
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Space } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { UniReport } from '../../../../components/uni-report';
import { downloadFile } from '../../../../utils/fileDownload';
import { executeReport } from '../../services/kuaireport';
import { downloadFullExcel, getReport, type ReportCenterRow } from './api';

export default function ReportPreviewPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const params = useParams();
  const reportId = Number(params.reportId);
  const [report, setReport] = useState<ReportCenterRow | null>(null);
  const [loadError, setLoadError] = useState('');
  const [exporting, setExporting] = useState(false);
  const filtersRef = useRef<Record<string, unknown>>({});

  useEffect(() => {
    if (!Number.isInteger(reportId) || reportId <= 0) {
      setLoadError('报表 ID 无效');
      return;
    }
    let cancelled = false;
    getReport(reportId)
      .then((row) => {
        if (!cancelled) setReport(row);
      })
      .catch((err: Error) => {
        if (!cancelled) setLoadError(err.message || '报表加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  // UniReport config 模式不向外暴露筛选值；经 datasetExecute 记录最近一次执行筛选，
  // 导出全量 Excel 时原样转发（后端忽略 limit/offset）。
  const recordFiltersExecute = useCallback(
    async (filters: Record<string, unknown>) => {
      filtersRef.current = filters || {};
      const res = await executeReport(reportId, filtersRef.current);
      return { ...res, data: (res.data ?? []) as Record<string, unknown>[] };
    },
    [reportId],
  );

  const onExport = async () => {
    if (!report) return;
    setExporting(true);
    try {
      const { limit: _limit, offset: _offset, ...rest } = filtersRef.current;
      const blob = await downloadFullExcel(report.id, rest);
      downloadFile(blob, `${report.code}.xlsx`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '全量 Excel 导出失败');
    } finally {
      setExporting(false);
    }
  };

  if (loadError) {
    return (
      <div style={{ padding: 16 }}>
        <Alert
          type="error"
          message={loadError}
          action={
            <Button size="small" onClick={() => navigate('/apps/kuaireport/reports')}>
              返回报表中心
            </Button>
          }
        />
      </div>
    );
  }
  if (!report) {
    return null;
  }

  return (
    <UniReport
      mode="config"
      title={report.name}
      columnPersistenceId={`kuaireport.reports.${report.code}`}
      reportId={report.id}
      reportConfig={report.report_config}
      datasetExecute={recordFiltersExecute}
      showPrintButton
      showExportButton={false}
      headerLeft={
        <Space>
          <Button onClick={() => navigate('/apps/kuaireport/reports')}>返回</Button>
          <Button type="primary" loading={exporting} onClick={() => void onExport()}>
            全量 Excel
          </Button>
        </Space>
      }
    />
  );
}
