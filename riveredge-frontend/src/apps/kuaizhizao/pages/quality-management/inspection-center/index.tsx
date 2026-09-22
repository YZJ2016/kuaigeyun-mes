import React, { useMemo } from 'react';
import { App, Button, Table, Typography, theme } from 'antd';
import {
  ThunderboltOutlined,
  CheckCircleOutlined,
  AlertOutlined,
  ClockCircleOutlined,
  SafetyCertificateOutlined,
  PartitionOutlined,
  DatabaseOutlined,
  ExportOutlined,
  AuditOutlined,
  LineChartOutlined,
  NodeIndexOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';
import 'dayjs/locale/en';
import { qualityApi, type QualityAnomalyItem } from '../../../services/quality-execution';
import { qualityImprovementApi } from '../../../services/quality-improvement';
import { normalizeQualityImprovementListResponse } from '../../../utils/qualityImprovementListCore';
import { mesDashboardService } from '../../../services/dashboard';
import { useDashboardRequest } from '../../../utils/dashboardRequestOptions';
import {
  ModuleCenterLayout,
  ModuleKpiRow,
  ModuleShortcutGrid,
  ModuleActionPanel,
  ModuleActionMasonry,
  ModuleTodoList,
  ModuleChartPanel,
  ModuleTrendLine,
  ModuleFeedList,
  showMasonryCard,
  masonryWeightFromRows,
  resolveMasonryEmptyFallback,
} from '../../../components/module-center';
import { MarkerTag, StatusTag } from '../../../../../constants/statusBadges';
import { normalizeQualityInspectionListResponse } from '../../../utils/qualityInspectionListCore';
import type { ModuleKpiDef, ModuleShortcutDef } from '../../../components/module-center';

dayjs.extend(relativeTime);

const { Text } = Typography;

const INSPECTION_LIST_PATH: Record<string, string> = {
  incoming: '/apps/kuaizhizao/quality-management/incoming-inspection',
  process: '/apps/kuaizhizao/quality-management/process-inspection',
  finished: '/apps/kuaizhizao/quality-management/finished-goods-inspection',
  oqc: '/apps/kuaizhizao/quality-management/oqc-inspection',
};

const INSPECTION_TYPE_KEY: Record<string, string> = {
  incoming: 'app.kuaizhizao.quality.common.type.incoming',
  process: 'app.kuaizhizao.quality.common.type.process',
  finished: 'app.kuaizhizao.quality.common.type.finished',
  oqc: 'app.kuaizhizao.quality.common.type.oqc',
};

function anomalySeverity(a: QualityAnomalyItem): 'high' | 'medium' | 'low' {
  const iq = Number(a.inspection_quantity) || 0;
  const uq = Number(a.unqualified_quantity) || 0;
  if (iq <= 0) return 'low';
  const ratio = uq / iq;
  if (ratio >= 0.5) return 'high';
  if (ratio >= 0.2) return 'medium';
  return 'low';
}

const InspectionCenter: React.FC = () => {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { message } = App.useApp();
  const { token } = theme.useToken();

  const dayjsLocale =
    i18n.language === 'en-US' || i18n.language?.startsWith('en') ? 'en' : 'zh-cn';
  dayjs.locale(dayjsLocale);

  const { data: summary, loading: summaryLoading } = useDashboardRequest(
    () => qualityApi.qualityStatistics.getInspectionCenterSummary(),
    'kz:quality-dashboard:summary',
    {
      onError: (e: { message?: string }) =>
        message.error(
          e?.message || t('app.kuaizhizao.quality.inspectionCenter.messages.loadSummaryFailed'),
        ),
    },
  );

  const { data: anomaliesResp, loading: anomaliesLoading } = useDashboardRequest(
    () => qualityApi.qualityStatistics.getAnomalies({ limit: 12 }),
    'kz:quality-dashboard:anomalies',
    {
      onError: (e: { message?: string }) =>
        message.error(
          e?.message || t('app.kuaizhizao.quality.inspectionCenter.messages.loadAnomaliesFailed'),
        ),
    },
  );

  const { data: todosData, loading: todosLoading } = useDashboardRequest(
    () => mesDashboardService.getTodosByModule('quality', 8),
    'kz:quality-dashboard:todos',
  );

  const { data: ncItems, loading: ncLoading } = useDashboardRequest(async () => {
    const res = await qualityImprovementApi.nonconformingLedger.list({ limit: 6 });
    const { data } = normalizeQualityImprovementListResponse(res);
    return data;
  }, 'kz:quality-dashboard:nc-ledger');

  const { data: incomingPendingRaw, loading: incomingPendingLoading } = useDashboardRequest(async () => {
    const res = await qualityApi.incomingInspection.list({ limit: 6, status: '待检验' });
    return normalizeQualityInspectionListResponse(res).data;
  }, 'kz:quality-dashboard:incoming-pending');

  const { data: processPendingRaw, loading: processPendingLoading } = useDashboardRequest(async () => {
    const res = await qualityApi.processInspection.list({ limit: 6, status: '待检验' });
    return normalizeQualityInspectionListResponse(res).data;
  }, 'kz:quality-dashboard:process-pending');

  const incomingPending = (incomingPendingRaw ?? []) as Record<string, unknown>[];
  const processPending = (processPendingRaw ?? []) as Record<string, unknown>[];

  const anomalies = anomaliesResp?.anomalies ?? [];
  const qualityTodos = todosData?.items ?? [];

  const pendingTotal =
    (summary?.pending_incoming || 0) +
    (summary?.pending_process || 0) +
    (summary?.pending_finished || 0) +
    (summary?.pending_oqc || 0);

  const pendingByType = useMemo(
    () => [
      { key: 'incoming', count: summary?.pending_incoming || 0 },
      { key: 'process', count: summary?.pending_process || 0 },
      { key: 'finished', count: summary?.pending_finished || 0 },
      { key: 'oqc', count: summary?.pending_oqc || 0 },
    ],
    [summary],
  );

  const kpis: ModuleKpiDef[] = useMemo(
    () => [
      {
        key: 'pending',
        title: t('app.kuaizhizao.quality.inspectionCenter.kpi.pendingTotal'),
        value: pendingTotal,
        subtitle: t('app.kuaizhizao.quality.inspectionCenter.kpi.pendingSubtitle'),
        icon: <ClockCircleOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #1890ff 0%, #36cfc9 100%)',
        onClick: () => navigate('/apps/kuaizhizao/quality-management/incoming-inspection'),
        sideMetrics: [
          {
            label: t('app.kuaizhizao.quality.inspectionCenter.kpi.incomingProcess'),
            value: `${summary?.pending_incoming || 0} / ${summary?.pending_process || 0}`,
          },
          {
            label: t('app.kuaizhizao.quality.inspectionCenter.kpi.finishedOqc'),
            value: `${summary?.pending_finished || 0} / ${summary?.pending_oqc || 0}`,
          },
        ],
      },
      {
        key: 'today',
        title: t('app.kuaizhizao.quality.inspectionCenter.kpi.todayQualified'),
        value: `${summary?.today_qualified_rate ?? 0}%`,
        subtitle: t('app.kuaizhizao.quality.inspectionCenter.kpi.todaySubtitle', {
          count: summary?.total_inspected_today || 0,
        }),
        icon: <ThunderboltOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #722ed1 0%, #b37feb 100%)',
        sideMetrics: [
          {
            label: t('app.kuaizhizao.quality.inspectionCenter.kpi.todayReported'),
            value: summary?.total_inspected_today || 0,
          },
          {
            label: t('common.status'),
            value:
              summary && summary.today_qualified_rate >= 98
                ? t('app.kuaizhizao.quality.inspectionCenter.kpi.statusExcellent')
                : t('app.kuaizhizao.quality.inspectionCenter.kpi.statusControlled'),
          },
        ],
      },
      {
        key: 'month',
        title: t('app.kuaizhizao.quality.inspectionCenter.kpi.monthRate'),
        value: `${summary?.month_qualified_rate ?? 0}%`,
        subtitle: t('app.kuaizhizao.quality.inspectionCenter.kpi.monthSubtitle', {
          rate: summary?.last_month_qualified_rate || 0,
        }),
        icon: <CheckCircleOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #52c41a 0%, #95de64 100%)',
        sideMetrics: [
          {
            label: t('app.kuaizhizao.quality.inspectionCenter.kpi.lastMonth'),
            value: `${summary?.last_month_qualified_rate || 0}%`,
          },
          {
            label: t('app.kuaizhizao.quality.inspectionCenter.kpi.trend'),
            value:
              summary && summary.month_qualified_rate >= (summary.last_month_qualified_rate || 0)
                ? '↑'
                : '↓',
          },
        ],
      },
    ],
    [summary, pendingTotal, navigate, t],
  );

  const shortcuts: ModuleShortcutDef[] = useMemo(
    () => [
      {
        key: 'incoming',
        title: t('app.kuaizhizao.menu.quality-management.incoming-inspection'),
        icon: <DatabaseOutlined style={{ fontSize: 20, color: '#1890ff' }} />,
        path: '/apps/kuaizhizao/quality-management/incoming-inspection',
      },
      {
        key: 'process',
        title: t('app.kuaizhizao.menu.quality-management.process-inspection'),
        icon: <PartitionOutlined style={{ fontSize: 20, color: '#722ed1' }} />,
        path: '/apps/kuaizhizao/quality-management/process-inspection',
      },
      {
        key: 'finished',
        title: t('app.kuaizhizao.menu.quality-management.finished-goods-inspection'),
        icon: <SafetyCertificateOutlined style={{ fontSize: 20, color: '#52c41a' }} />,
        path: '/apps/kuaizhizao/quality-management/finished-goods-inspection',
      },
      {
        key: 'oqc',
        title: t('app.kuaizhizao.menu.quality-management.oqc-inspection'),
        icon: <ExportOutlined style={{ fontSize: 20, color: '#13c2c2' }} />,
        path: '/apps/kuaizhizao/quality-management/oqc-inspection',
      },
      {
        key: 'nc',
        title: t('app.kuaizhizao.menu.quality-management.nonconforming-ledger'),
        icon: <AlertOutlined style={{ fontSize: 20, color: '#f5222d' }} />,
        path: '/apps/kuaizhizao/quality-management/nonconforming-ledger',
      },
      {
        key: '8d',
        title: t('app.kuaizhizao.menu.quality-management.eight-d-reports'),
        icon: <AuditOutlined style={{ fontSize: 20, color: '#eb2f96' }} />,
        path: '/apps/kuaizhizao/quality-management/eight-d-reports',
      },
      {
        key: 'trace',
        title: t('app.kuaizhizao.menu.quality-management.traceability'),
        icon: <NodeIndexOutlined style={{ fontSize: 20, color: '#2f54eb' }} />,
        path: '/apps/kuaizhizao/quality-management/traceability',
      },
      {
        key: 'reports',
        title: t('app.kuaizhizao.menu.quality-management.reports'),
        icon: <LineChartOutlined style={{ fontSize: 20, color: '#fa541c' }} />,
        path: '/apps/kuaizhizao/quality-management/reports/incoming-inspection',
      },
    ],
    [t],
  );

  const chartData = useMemo(
    () =>
      (summary?.daily_pass_rate_trend || []).map((d) => ({
        date: d.date.slice(5),
        rate: d.rate,
      })),
    [summary],
  );

  const trendConfig = useMemo(() => {
    const rows = chartData.length ? chartData : [{ date: '-', rate: 0 }];
    const rates = chartData.map((d) => d.rate);
    const hasRates = rates.length > 0;
    const minR = hasRates ? Math.min(...rates) : 0;
    const maxR = hasRates ? Math.max(...rates) : 100;
    const pad = 5;
    return {
      data: rows,
      xField: 'date',
      yField: 'rate',
      animation: false,
      padding: 'auto' as const,
      color: '#1890ff',
      point: { size: 4, shape: 'diamond' as const },
      label: { style: { fill: '#aaa' } },
      yAxis: hasRates
        ? { min: Math.max(0, minR - pad), max: Math.min(100, maxR + pad) }
        : { min: 0, max: 100 },
    };
  }, [chartData]);

  const hasPendingByType = pendingByType.some((item) => item.count > 0);
  const hasTrendData = chartData.length > 0;
  const ncPending = ncItems?.slice(0, 6) ?? [];

  const masonryLoading =
    todosLoading || summaryLoading || anomaliesLoading || ncLoading;
  const masonryEmptyFallback = resolveMasonryEmptyFallback(masonryLoading, [
    qualityTodos.length > 0,
    hasPendingByType,
    anomalies.length > 0,
    ncPending.length > 0,
    hasTrendData,
  ]);

  const inspectionQueueColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.quality.common.label.inspectionCode'),
        dataIndex: 'inspection_code',
        ellipsis: true,
        render: (text: string) => text || '-',
      },
      {
        title: t('app.kuaizhizao.quality.common.label.materialName'),
        dataIndex: 'material_name',
        ellipsis: true,
        render: (text: string) => text || '-',
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 80,
        render: (status: string) => (
          <StatusTag color="processing">{status || t('app.kuaizhizao.quality.common.docStatus.pendingInspection')}</StatusTag>
        ),
      },
    ],
    [t],
  );

  const anomalyFeedItems = useMemo(
    () =>
      anomalies.slice(0, 12).map((item) => ({
        id: `${item.inspection_type}-${item.inspection_id}`,
        title: item.material_name || item.inspection_code,
        subtitle:
          item.nonconformance_reason ||
          t('app.kuaizhizao.quality.inspectionCenter.anomalyDefaultReason'),
        tag: {
          label: INSPECTION_TYPE_KEY[item.inspection_type]
            ? t(INSPECTION_TYPE_KEY[item.inspection_type])
            : item.inspection_type,
          color: anomalySeverity(item) === 'high' ? 'error' : 'warning',
        },
        meta: (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {dayjs(item.inspection_time).fromNow()}
          </Text>
        ),
        onClick: () => navigate(INSPECTION_LIST_PATH[item.inspection_type] || '/'),
      })),
    [anomalies, navigate, t],
  );

  const ncFeedItems = useMemo(
    () =>
      ncPending.map((item: Record<string, unknown>) => ({
        id: String(item.id ?? item.code ?? item.uuid),
        title: String(item.code ?? ''),
        subtitle: String(item.product_name || item.defect_reason || item.defect_type || ''),
        tag: item.status ? { label: String(item.status), color: 'warning' } : undefined,
        onClick: () => navigate('/apps/kuaizhizao/quality-management/nonconforming-ledger'),
      })),
    [ncPending, navigate],
  );

  const pendingByTypeItems = useMemo(
    () => pendingByType.filter((item) => item.count > 0),
    [pendingByType],
  );

  return (
    <ModuleCenterLayout
      loading={summaryLoading && !summary}
      kpiRow={<ModuleKpiRow items={kpis} />}
      shortcutRow={<ModuleShortcutGrid items={shortcuts} />}
      actionRow={
        <ModuleActionMasonry>
          {showMasonryCard(todosLoading, qualityTodos.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel layout="masonry" title={t('app.kuaizhizao.quality.inspectionCenter.todoPanel')} loading={todosLoading} masonryWeight={masonryWeightFromRows(qualityTodos.length)}>
              <ModuleTodoList items={qualityTodos} emptyText={t('app.kuaizhizao.quality.common.empty.noTodos')} />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(incomingPendingLoading, incomingPending.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.quality.inspectionCenter.incomingPendingTitle')}
              loading={incomingPendingLoading}
              masonryWeight={masonryWeightFromRows(incomingPending.length)}
              extra={
                <a onClick={() => navigate(INSPECTION_LIST_PATH.incoming)}>
                  {t('app.kuaizhizao.quality.common.actions.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.inspection_code)}
                dataSource={incomingPending}
                columns={inspectionQueueColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(processPendingLoading, processPending.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.quality.inspectionCenter.processPendingTitle')}
              loading={processPendingLoading}
              masonryWeight={masonryWeightFromRows(processPending.length)}
              extra={
                <a onClick={() => navigate(INSPECTION_LIST_PATH.process)}>
                  {t('app.kuaizhizao.quality.common.actions.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.inspection_code)}
                dataSource={processPending}
                columns={inspectionQueueColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(anomaliesLoading, anomalies.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.quality.inspectionCenter.anomalyPanel')}
              loading={anomaliesLoading}
              masonryWeight={masonryWeightFromRows(anomalyFeedItems.length)}
              extra={
                <Button type="link" onClick={() => navigate('/apps/kuaizhizao/production-execution/quality-exceptions')}>
                  {t('app.kuaizhizao.quality.common.actions.viewAll')}
                </Button>
              }
            >
              <ModuleFeedList items={anomalyFeedItems} emptyText={t('common.noData')} />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(ncLoading, ncPending.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.quality.inspectionCenter.ncPendingTitle')}
              loading={ncLoading}
              masonryWeight={masonryWeightFromRows(ncPending.length)}
              extra={
                <a onClick={() => navigate('/apps/kuaizhizao/quality-management/nonconforming-ledger')}>
                  {t('app.kuaizhizao.quality.common.actions.viewAll')}
                </a>
              }
            >
              <ModuleFeedList items={ncFeedItems} emptyText={t('common.noData')} />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(summaryLoading, hasPendingByType, masonryEmptyFallback) ? (
            <ModuleActionPanel layout="masonry" title={t('app.kuaizhizao.quality.inspectionCenter.pendingByTypeTitle')} masonryWeight={masonryWeightFromRows(pendingByType.filter((i) => i.count > 0).length)}>
              <div className="dashboard-feed-list">
                {pendingByTypeItems.map((item) => (
                  <div
                    key={item.key}
                    role="button"
                    tabIndex={0}
                    onClick={() => navigate(INSPECTION_LIST_PATH[item.key] || '/')}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        navigate(INSPECTION_LIST_PATH[item.key] || '/');
                      }
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 8,
                      padding: '8px 10px',
                      borderRadius: 6,
                      marginBottom: 6,
                      border: `1px solid ${token.colorBorderSecondary}`,
                      cursor: 'pointer',
                    }}
                  >
                    <Text style={{ flex: 1, minWidth: 0 }}>
                      {INSPECTION_TYPE_KEY[item.key] ? t(INSPECTION_TYPE_KEY[item.key]) : item.key}
                    </Text>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                      <MarkerTag color="processing">{item.count}</MarkerTag>
                      <RightOutlined style={{ color: token.colorTextTertiary, fontSize: 11 }} />
                    </div>
                  </div>
                ))}
              </div>
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(summaryLoading, hasTrendData, masonryEmptyFallback) ? (
            <ModuleChartPanel layout="masonry" title={t('app.kuaizhizao.quality.inspectionCenter.passRateTrend')} height={300} masonryWeight={3}>
              <ModuleTrendLine {...trendConfig} height={280} />
            </ModuleChartPanel>
          ) : null}
        </ModuleActionMasonry>
      }
    />
  );
};

export default InspectionCenter;
