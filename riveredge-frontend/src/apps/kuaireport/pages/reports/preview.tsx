/**
 * 系统报表预览。config 模式交给 UniReport（内部调用 executeReport，打印走 useUniReportPrint）。
 * 全量 Excel 另请求星报表后端生成工作簿。
 * 通过 datasetExecute 透传同一 executeReport，并记录最近一次筛选用于导出。
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Space, Spin } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { UniReport } from '../../../../components/uni-report';
import { downloadFile } from '../../../../utils/fileDownload';
import { executeReport } from '../../services/kuaireport';
import { ChartCanvas, DrillDrawer, QueryPanel } from './ChartPanel';
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

  if (report.report_config?.chart_type && report.report_config.dataset_uuid) {
    return (
      <DatasetChartView
        report={report}
        onExport={onExport}
        exporting={exporting}
        onFilters={(next) => {
          filtersRef.current = next;
        }}
      />
    );
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

function DatasetChartView({
  report,
  onExport,
  exporting,
  onFilters,
}: {
  report: ReportCenterRow;
  onExport: () => Promise<void>;
  exporting: boolean;
  onFilters: (filters: Record<string, unknown>) => void;
}) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const config = report.report_config;
  const fields = config.fields || [];
  const xField = fields.find((field) => field.x_axis)?.field;
  const yField = fields.find((field) => field.y_axis)?.field;
  const drill = config.interaction?.drilldown;
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [drillValue, setDrillValue] = useState<string | null>(null);
  const [drillRows, setDrillRows] = useState<Record<string, unknown>[]>([]);

  const load = useCallback(
    async (next: Record<string, unknown>) => {
      setLoading(true);
      try {
        const res = await executeReport(report.id, { ...next, limit: config.page_size || 50, offset: 0 });
        setRows((res.data || []) as Record<string, unknown>[]);
      } catch (err) {
        message.error(err instanceof Error ? err.message : '报表加载失败');
      } finally {
        setLoading(false);
      }
    },
    [config.page_size, message, report.id],
  );

  useEffect(() => {
    void load({});
  }, [load]);

  const openDrill = async (value: string) => {
    const dimension = drill?.dimension_field || xField;
    if (!dimension) return;
    setDrillValue(value);
    try {
      const res = await executeReport(report.id, {
        ...filters,
        [dimension]: value,
        limit: 500,
        offset: 0,
      });
      const data = ((res.data || []) as Record<string, unknown>[]).filter(
        (row) => String(row[dimension] ?? '') === value,
      );
      setDrillRows(data.length ? data : ((res.data || []) as Record<string, unknown>[]));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '下钻失败');
    }
  };

  return (
    <div style={{ padding: 16 }}>
      <Space style={{ marginBottom: 12 }}>
        <Button onClick={() => navigate('/apps/kuaireport/reports')}>返回</Button>
        <Button type="primary" loading={exporting} onClick={() => void onExport()}>
          全量 Excel
        </Button>
        <span style={{ fontWeight: 600 }}>{report.name}</span>
      </Space>
      <QueryPanel
        parameters={config.parameters || []}
        onSubmit={(next) => {
          setFilters(next);
          onFilters(next);
          void load(next);
        }}
      />
      <Spin spinning={loading}>
        <ChartCanvas
          chartType={config.chart_type || 'table'}
          rows={rows}
          xField={xField}
          yField={yField}
          fields={fields}
          drillEnabled={Boolean(drill?.enabled)}
          onDrill={(value) => void openDrill(value)}
        />
      </Spin>
      {drill?.enabled ? <div style={{ marginTop: 8, color: '#8c8c8c' }}>点击图表维度可下钻明细</div> : null}
      <DrillDrawer
        open={drillValue != null}
        title={drill?.title || '明细下钻'}
        rows={drillRows}
        fields={fields}
        onClose={() => setDrillValue(null)}
      />
    </div>
  );
}
