import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Input,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ClockCircleOutlined,
  TeamOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  FieldTimeOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs, { type Dayjs } from 'dayjs';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import { ChartSuspense, LazyColumn, LazyPie } from '../../../../../components/common/lazyAntCharts';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { getDepartmentTree } from '../../../../../services/department';
import { flattenDepartmentOptions } from '../../../utils/oaLookupFields';
import {
  getAttendanceAnalysis,
  type AttendanceAnalysisPayload,
} from '../../../services/attendanceAnalysis';
import {
  ModuleKpiRow,
  type ModuleKpiDef,
} from '../../../../kuaizhizao/components/module-center';

const RESULT_CODES = ['normal', 'late', 'early', 'absent', 'leave', 'rest', 'other'] as const;

const AttendanceAnalysisPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const perms = useResourcePermissions('kuaioa:attendance-analysis');

  const [granularity, setGranularity] = useState<'day' | 'month'>('day');
  const [range, setRange] = useState<[Dayjs, Dayjs]>(() => [dayjs().subtract(29, 'day'), dayjs()]);
  const [department, setDepartment] = useState<string | undefined>();
  const [keywordInput, setKeywordInput] = useState('');
  const [appliedKeyword, setAppliedKeyword] = useState('');
  const [deptOptions, setDeptOptions] = useState<Array<{ label: string; value: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState<AttendanceAnalysisPayload | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await getDepartmentTree({ host_resource: 'kuaioa:attendance-analysis' }).catch(
          () => getDepartmentTree(),
        );
        setDeptOptions(flattenDepartmentOptions(res.items ?? []));
      } catch {
        setDeptOptions([]);
      }
    })();
  }, []);

  const granularityInitRef = useRef(true);
  // 切换按月时默认看本年，按天默认近 30 天（跳过首次挂载）
  useEffect(() => {
    if (granularityInitRef.current) {
      granularityInitRef.current = false;
      return;
    }
    if (granularity === 'month') {
      setRange([dayjs().startOf('year'), dayjs()]);
    } else {
      setRange([dayjs().subtract(29, 'day'), dayjs()]);
    }
  }, [granularity]);

  const load = useCallback(async () => {
    if (!perms.canRead) return;
    if (!range?.[0]?.isValid() || !range?.[1]?.isValid()) {
      message.error(t('app.kuaioa.attendanceAnalysis.rangeInvalid'));
      return;
    }
    setLoading(true);
    try {
      const data = await getAttendanceAnalysis({
        granularity,
        date_from: range[0].format('YYYY-MM-DD'),
        date_to: range[1].format('YYYY-MM-DD'),
        department_name: department || undefined,
        keyword: appliedKeyword.trim() || undefined,
      });
      setPayload(data);
    } catch (error) {
      message.error(getApiErrorMessage(error));
      setPayload(null);
    } finally {
      setLoading(false);
    }
  }, [appliedKeyword, department, granularity, message, perms.canRead, range, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const resultLabel = useCallback(
    (code: string) => {
      if (code === 'other') return t('app.kuaioa.attendanceAnalysis.result.other');
      return t(`app.kuaioa.attendanceDaily.result.${code}`, { defaultValue: code });
    },
    [t],
  );

  const summary = payload?.summary;
  const kpis: ModuleKpiDef[] = useMemo(() => {
    if (!summary) return [];
    return [
      {
        key: 'records',
        title: t('app.kuaioa.attendanceAnalysis.kpi.records'),
        value: summary.record_count,
        icon: <TeamOutlined />,
        gradient: 'blue',
      },
      {
        key: 'rate',
        title: t('app.kuaioa.attendanceAnalysis.kpi.attendanceRate'),
        value: `${Number(summary.attendance_rate || 0).toFixed(1)}%`,
        icon: <CheckCircleOutlined />,
        gradient: 'green',
      },
      {
        key: 'late',
        title: t('app.kuaioa.attendanceAnalysis.kpi.late'),
        value: summary.late_count,
        icon: <WarningOutlined />,
        gradient: 'orange',
        sideMetrics: [
          {
            label: t('app.kuaioa.attendanceAnalysis.kpi.lateMinutes'),
            value: summary.late_minutes,
          },
        ],
      },
      {
        key: 'ot',
        title: t('app.kuaioa.attendanceAnalysis.kpi.otHours'),
        value: Number(summary.ot_hours || 0).toFixed(1),
        icon: <FieldTimeOutlined />,
        gradient: 'purple',
        sideMetrics: [
          {
            label: t('app.kuaioa.attendanceAnalysis.kpi.early'),
            value: summary.early_count,
          },
        ],
      },
      {
        key: 'absent',
        title: t('app.kuaioa.attendanceAnalysis.kpi.absent'),
        value: summary.absent_count,
        icon: <ClockCircleOutlined />,
        gradient: 'red',
        sideMetrics: [
          {
            label: t('app.kuaioa.attendanceAnalysis.kpi.leave'),
            value: summary.leave_count,
          },
        ],
      },
    ];
  }, [summary, t]);

  const stackedColumnData = useMemo(() => {
    const series = payload?.series || [];
    const rows: Array<{ period: string; type: string; value: number }> = [];
    for (const item of series) {
      for (const code of RESULT_CODES) {
        const count = Number((item as Record<string, unknown>)[`${code}_count`] || 0);
        if (count <= 0) continue;
        rows.push({
          period: item.label,
          type: resultLabel(code),
          value: count,
        });
      }
    }
    return rows;
  }, [payload?.series, resultLabel]);

  const hoursColumnData = useMemo(() => {
    const series = payload?.series || [];
    const rows: Array<{ period: string; type: string; value: number }> = [];
    for (const item of series) {
      rows.push({
        period: item.label,
        type: t('app.kuaioa.attendanceAnalysis.metric.otHours'),
        value: Number(item.ot_hours || 0),
      });
      rows.push({
        period: item.label,
        type: t('app.kuaioa.attendanceAnalysis.metric.lateMinutes'),
        value: Number(item.late_minutes || 0),
      });
    }
    return rows;
  }, [payload?.series, t]);

  const pieData = useMemo(
    () =>
      (payload?.result_distribution || []).map((item) => ({
        type: resultLabel(item.result),
        value: item.count,
      })),
    [payload?.result_distribution, resultLabel],
  );

  const deptColumns: ColumnsType<Record<string, unknown>> = useMemo(
    () => [
      { title: t('app.kuaioa.common.department'), dataIndex: 'label', width: 140 },
      { title: t('app.kuaioa.attendanceAnalysis.col.records'), dataIndex: 'record_count', width: 90 },
      { title: t('app.kuaioa.attendanceDaily.result.normal'), dataIndex: 'normal_count', width: 80 },
      { title: t('app.kuaioa.attendanceDaily.result.late'), dataIndex: 'late_count', width: 80 },
      { title: t('app.kuaioa.attendanceDaily.result.early'), dataIndex: 'early_count', width: 80 },
      { title: t('app.kuaioa.attendanceDaily.result.absent'), dataIndex: 'absent_count', width: 80 },
      { title: t('app.kuaioa.attendanceDaily.result.leave'), dataIndex: 'leave_count', width: 80 },
      {
        title: t('app.kuaioa.attendanceAnalysis.metric.lateMinutes'),
        dataIndex: 'late_minutes',
        width: 100,
      },
      {
        title: t('app.kuaioa.attendanceAnalysis.metric.otHours'),
        dataIndex: 'ot_hours',
        width: 100,
        render: (v) => Number(v || 0).toFixed(1),
      },
    ],
    [t],
  );

  const empColumns: ColumnsType<Record<string, unknown>> = useMemo(
    () => [
      { title: t('app.kuaioa.attendanceDaily.employeeName'), dataIndex: 'employee_name', width: 110 },
      { title: t('app.kuaioa.attendanceDaily.employeeCode'), dataIndex: 'employee_code', width: 100 },
      { title: t('app.kuaioa.common.department'), dataIndex: 'department_name', width: 120 },
      { title: t('app.kuaioa.attendanceAnalysis.col.records'), dataIndex: 'record_count', width: 90 },
      {
        title: t('app.kuaioa.attendanceAnalysis.metric.lateMinutes'),
        dataIndex: 'late_minutes',
        width: 100,
        defaultSortOrder: 'descend',
        sorter: (a, b) => Number(a.late_minutes || 0) - Number(b.late_minutes || 0),
      },
      {
        title: t('app.kuaioa.attendanceAnalysis.metric.otHours'),
        dataIndex: 'ot_hours',
        width: 100,
        sorter: (a, b) => Number(a.ot_hours || 0) - Number(b.ot_hours || 0),
        render: (v) => Number(v || 0).toFixed(1),
      },
      { title: t('app.kuaioa.attendanceDaily.result.late'), dataIndex: 'late_count', width: 80 },
      { title: t('app.kuaioa.attendanceDaily.result.absent'), dataIndex: 'absent_count', width: 80 },
    ],
    [t],
  );

  const handleExport = async () => {
    if (!payload) return;
    const seriesRows = (payload.series || []).map((row) => ({
      period: row.label,
      record_count: row.record_count,
      normal_count: row.normal_count,
      late_count: row.late_count,
      early_count: row.early_count,
      absent_count: row.absent_count,
      leave_count: row.leave_count,
      rest_count: row.rest_count,
      late_minutes: row.late_minutes,
      ot_hours: row.ot_hours,
      actual_hours: row.actual_hours,
    }));
    await downloadRecordsAsXlsx(
      seriesRows,
      [
        { key: 'period', title: t('app.kuaioa.attendanceAnalysis.col.period') },
        { key: 'record_count', title: t('app.kuaioa.attendanceAnalysis.col.records') },
        { key: 'normal_count', title: t('app.kuaioa.attendanceDaily.result.normal') },
        { key: 'late_count', title: t('app.kuaioa.attendanceDaily.result.late') },
        { key: 'early_count', title: t('app.kuaioa.attendanceDaily.result.early') },
        { key: 'absent_count', title: t('app.kuaioa.attendanceDaily.result.absent') },
        { key: 'leave_count', title: t('app.kuaioa.attendanceDaily.result.leave') },
        { key: 'rest_count', title: t('app.kuaioa.attendanceDaily.result.rest') },
        { key: 'late_minutes', title: t('app.kuaioa.attendanceAnalysis.metric.lateMinutes') },
        { key: 'ot_hours', title: t('app.kuaioa.attendanceAnalysis.metric.otHours') },
        { key: 'actual_hours', title: t('app.kuaioa.attendanceDaily.actualHours') },
      ],
      t('app.kuaioa.attendanceAnalysis.exportFileName'),
    );
  };

  if (!perms.canRead) {
    return <ListPageTemplate>{t('app.kuaioa.common.noPermission')}</ListPageTemplate>;
  }

  return (
    <ListPageTemplate
      title={t('app.kuaioa.attendanceAnalysis.title')}
      toolbarExtra={
        <Space wrap>
          <Segmented
            value={granularity}
            onChange={(v) => setGranularity(v as 'day' | 'month')}
            options={[
              { label: t('app.kuaioa.attendanceAnalysis.granularity.day'), value: 'day' },
              { label: t('app.kuaioa.attendanceAnalysis.granularity.month'), value: 'month' },
            ]}
          />
          <DatePicker.RangePicker
            value={range}
            onChange={(v) => {
              if (v?.[0] && v?.[1]) setRange([v[0], v[1]]);
            }}
            allowClear={false}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaioa.common.department')}
            style={{ minWidth: 160 }}
            options={deptOptions}
            value={department}
            onChange={(v) => setDepartment(v)}
          />
          <Input.Search
            allowClear
            placeholder={t('app.kuaioa.attendanceAnalysis.keywordPlaceholder')}
            style={{ width: 200 }}
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onSearch={(v) => setAppliedKeyword(v.trim())}
          />
          <Button type="primary" loading={loading} onClick={() => void load()}>
            {t('common.query')}
          </Button>
          {perms.canExport ? (
            <Button disabled={!payload?.series?.length} onClick={() => void handleExport()}>
              {t('common.export')}
            </Button>
          ) : null}
        </Space>
      }
    >
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('app.kuaioa.attendanceAnalysis.hint')}
      </Typography.Paragraph>

      {kpis.length ? (
        <div style={{ marginBottom: 16 }}>
          <ModuleKpiRow items={kpis} colProps={{ xs: 24, sm: 12, lg: 8 }} />
        </div>
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card
            size="small"
            title={
              granularity === 'day'
                ? t('app.kuaioa.attendanceAnalysis.chart.resultByDay')
                : t('app.kuaioa.attendanceAnalysis.chart.resultByMonth')
            }
            loading={loading}
          >
            {stackedColumnData.length ? (
              <ChartSuspense fallback={<div style={{ height: 320 }} />}>
                <LazyColumn
                  data={stackedColumnData}
                  xField="period"
                  yField="value"
                  colorField="type"
                  stack={true}
                  height={320}
                  autoFit
                  axis={{ x: { labelAutoRotate: true, labelAutoHide: true } }}
                  legend={{ color: { position: 'top' } }}
                />
              </ChartSuspense>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card size="small" title={t('app.kuaioa.attendanceAnalysis.chart.resultPie')} loading={loading}>
            {pieData.length ? (
              <ChartSuspense fallback={<div style={{ height: 320 }} />}>
                <LazyPie
                  data={pieData}
                  angleField="value"
                  colorField="type"
                  height={320}
                  autoFit
                  innerRadius={0.55}
                  legend={{ color: { position: 'bottom' } }}
                  label={{ text: 'value' }}
                />
              </ChartSuspense>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
            )}
          </Card>
        </Col>
        <Col span={24}>
          <Card size="small" title={t('app.kuaioa.attendanceAnalysis.chart.otAndLate')} loading={loading}>
            {hoursColumnData.length ? (
              <ChartSuspense fallback={<div style={{ height: 300 }} />}>
                <LazyColumn
                  data={hoursColumnData}
                  xField="period"
                  yField="value"
                  colorField="type"
                  group={true}
                  height={300}
                  autoFit
                  axis={{ x: { labelAutoRotate: true, labelAutoHide: true } }}
                  legend={{ color: { position: 'top' } }}
                />
              </ChartSuspense>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title={t('app.kuaioa.attendanceAnalysis.table.byDepartment')} loading={loading}>
            <Table
              size="small"
              rowKey="key"
              columns={deptColumns}
              dataSource={payload?.by_department || []}
              pagination={{ pageSize: 8, hideOnSinglePage: true }}
              scroll={{ x: 900 }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title={t('app.kuaioa.attendanceAnalysis.table.byEmployee')} loading={loading}>
            <Table
              size="small"
              rowKey="key"
              columns={empColumns}
              dataSource={payload?.by_employee || []}
              pagination={{ pageSize: 8, hideOnSinglePage: true }}
              scroll={{ x: 900 }}
            />
          </Card>
        </Col>
      </Row>
    </ListPageTemplate>
  );
};

export default AttendanceAnalysisPage;
