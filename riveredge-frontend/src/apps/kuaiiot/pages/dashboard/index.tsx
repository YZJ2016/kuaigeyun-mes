import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Table } from 'antd';
import {
  AlertOutlined,
  ApiOutlined,
  CloudServerOutlined,
  ClusterOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  LinkOutlined,
  TagsOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { formatDateTimeBySiteSetting } from '../../../../utils/format';
import {
  ModuleCenterLayout,
  ModuleKpiRow,
  ModuleShortcutGrid,
  ModuleActionPanel,
  ModuleActionMasonry,
  ModuleTodoList,
  ModuleChartPanel,
  ModuleFeedList,
  showMasonryCard,
  masonryWeightFromRows,
  resolveMasonryEmptyFallback,
} from '../../../kuaizhizao/components/module-center';
import type { ModuleKpiDef, ModuleShortcutDef, ModuleTodoItem } from '../../../kuaizhizao/components/module-center';
import {
  getDashboardSummary,
  getOpsSummary,
  listAlerts,
  listConnections,
  listEdgeConfigs,
  listOeeLive,
  type AlertRecord,
  type Connection,
  type DashboardSummary,
  type EdgeConfig,
  type OeeLiveItem,
  type OpsSummary,
} from '../../services/kuaiiot';
import { translateSeverity } from '../../constants/formOptions';
import {
  IOT_LIST_COL,
  renderIotAgentStatusMarker,
  renderIotHealthMarker,
  renderIotOnlineMarker,
} from '../../utils/iotListPresentation';

const POLL_MS = 30000;

const KuaiiotDashboardPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [ops, setOps] = useState<OpsSummary | null>(null);
  const [openAlerts, setOpenAlerts] = useState<AlertRecord[]>([]);
  const [unhealthyConnections, setUnhealthyConnections] = useState<Connection[]>([]);
  const [edgeIssues, setEdgeIssues] = useState<EdgeConfig[]>([]);
  const [oeeItems, setOeeItems] = useState<OeeLiveItem[]>([]);

  const loadDashboard = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    try {
      const [summaryRes, opsRes, alertsRes, connectionsRes, edgeRes, oeeRes] = await Promise.all([
        getDashboardSummary(),
        getOpsSummary().catch(() => null),
        listAlerts({ status: 'open', page_size: 8 }).catch(() => ({ items: [], total: 0 })),
        listConnections({ page_size: 50 }).catch(() => ({ items: [], total: 0 })),
        listEdgeConfigs({ page_size: 30 }).catch(() => ({ items: [], total: 0 })),
        listOeeLive({ hours: 24, limit: 8 }).catch(() => ({ items: [], total: 0 })),
      ]);
      setSummary(summaryRes);
      setOps(opsRes);
      setOpenAlerts(alertsRes.items ?? []);
      setUnhealthyConnections(
        (connectionsRes.items ?? []).filter((row) => String(row.health_status).toLowerCase() === 'unhealthy'),
      );
      setEdgeIssues(
        (edgeRes.items ?? []).filter((row) => {
          const status = String(row.agent_status ?? '').toLowerCase();
          return status === 'offline' || Number(row.buffer_pending_count ?? 0) > 0;
        }),
      );
      setOeeItems(oeeRes.items ?? []);
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard(true);
    const timer = window.setInterval(() => {
      void loadDashboard(false);
    }, POLL_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [loadDashboard]);

  const offlineRecentDevices = useMemo(
    () => (summary?.recent_devices ?? []).filter((d) => !d.is_online).slice(0, 8),
    [summary?.recent_devices],
  );

  const opsTodos: ModuleTodoItem[] = useMemo(() => {
    const items: ModuleTodoItem[] = [];
    const push = (
      id: string,
      title: string,
      link: string,
      priority: 'high' | 'medium' | 'low',
    ) => {
      items.push({
        id,
        type: 'kuaiiot',
        title,
        priority,
        status: 'pending',
        link,
        created_at: new Date().toISOString(),
      });
    };
    const openCount = ops?.alerts?.open ?? 0;
    if (openCount > 0) {
      push(
        'open-alerts',
        t('app.kuaiiot.dashboard.todoOpenAlerts', { count: openCount }),
        '/apps/kuaiiot/alerts',
        'high',
      );
    }
    const unhealthy = ops?.connections?.unhealthy ?? 0;
    if (unhealthy > 0) {
      push(
        'unhealthy-conn',
        t('app.kuaiiot.dashboard.todoUnhealthyConnections', { count: unhealthy }),
        '/apps/kuaiiot/connections',
        'high',
      );
    }
    const stale = ops?.devices?.stale ?? 0;
    if (stale > 0) {
      push(
        'stale-devices',
        t('app.kuaiiot.dashboard.todoStaleDevices', { count: stale }),
        '/apps/kuaiiot/devices',
        'medium',
      );
    }
    const offlineAgents = (ops?.edge_agents?.total ?? 0) - (ops?.edge_agents?.online ?? 0);
    if (offlineAgents > 0) {
      push(
        'edge-offline',
        t('app.kuaiiot.dashboard.todoEdgeOffline', { count: offlineAgents }),
        '/apps/kuaiiot/edge-configs',
        'medium',
      );
    }
    return items;
  }, [ops, t]);

  const alertFeedItems = useMemo(
    () =>
      openAlerts.map((row) => ({
        id: row.uuid,
        title: row.tag_key,
        subtitle: row.message,
        tag: {
          label: translateSeverity(t, row.severity),
          color: row.severity === 'critical' ? 'error' : row.severity === 'warning' ? 'warning' : 'default',
        },
        meta: (
          <span style={{ fontSize: 10, color: 'var(--ant-color-text-secondary)' }}>
            {formatDateTimeBySiteSetting(row.triggered_at)}
          </span>
        ),
        onClick: () => navigate('/apps/kuaiiot/alerts'),
      })),
    [navigate, openAlerts, t],
  );

  const kpis: ModuleKpiDef[] = useMemo(
    () => [
      {
        key: 'online',
        title: t('app.kuaiiot.dashboard.onlineDevices'),
        value: summary?.online_devices ?? 0,
        subtitle: t('app.kuaiiot.dashboard.kpiOnlineSubtitle', {
          total: summary?.total_devices ?? 0,
        }),
        icon: <CloudServerOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #52c41a 0%, #95de64 100%)',
        onClick: () => navigate('/apps/kuaiiot/devices'),
        sideMetrics: [
          {
            label: t('app.kuaiiot.ops.staleDevices'),
            value: ops?.devices?.stale ?? 0,
          },
        ],
      },
      {
        key: 'ingest',
        title: t('app.kuaiiot.dashboard.pointsToday'),
        value: summary?.points_today ?? 0,
        subtitle: t('app.kuaiiot.dashboard.kpiIngestSubtitle'),
        icon: <ApiOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #1890ff 0%, #36cfc9 100%)',
        onClick: () => navigate('/apps/kuaiiot/pipeline'),
      },
      {
        key: 'alerts',
        title: t('app.kuaiiot.ops.openAlerts'),
        value: ops?.alerts?.open ?? 0,
        subtitle: t('app.kuaiiot.dashboard.kpiAlertsSubtitle'),
        icon: <AlertOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #ff4d4f 0%, #ff7875 100%)',
        onClick: () => navigate('/apps/kuaiiot/alerts'),
      },
      {
        key: 'connections',
        title: t('app.kuaiiot.ops.unhealthyConnections'),
        value: ops?.connections?.unhealthy ?? 0,
        subtitle: t('app.kuaiiot.dashboard.kpiConnectionsSubtitle', {
          total: ops?.connections?.total ?? summary?.total_connections ?? 0,
        }),
        icon: <LinkOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #fa8c16 0%, #ffc069 100%)',
        onClick: () => navigate('/apps/kuaiiot/connections'),
        sideMetrics: [
          {
            label: t('app.kuaiiot.dashboard.enabledConnections'),
            value: summary?.enabled_connections ?? 0,
          },
        ],
      },
    ],
    [navigate, ops, summary, t],
  );

  const shortcuts: ModuleShortcutDef[] = useMemo(
    () => [
      {
        key: 'connections',
        title: t('app.kuaiiot.menu.connections'),
        icon: <LinkOutlined style={{ fontSize: 22, color: '#1890ff' }} />,
        path: '/apps/kuaiiot/connections',
      },
      {
        key: 'devices',
        title: t('app.kuaiiot.menu.devices'),
        icon: <DeploymentUnitOutlined style={{ fontSize: 22, color: '#52c41a' }} />,
        path: '/apps/kuaiiot/devices',
      },
      {
        key: 'alerts',
        title: t('app.kuaiiot.menu.alerts'),
        icon: <AlertOutlined style={{ fontSize: 22, color: '#ff4d4f' }} />,
        path: '/apps/kuaiiot/alerts',
      },
      {
        key: 'pipeline',
        title: t('app.kuaiiot.menu.pipeline'),
        icon: <ClusterOutlined style={{ fontSize: 22, color: '#722ed1' }} />,
        path: '/apps/kuaiiot/pipeline',
      },
      {
        key: 'edge',
        title: t('app.kuaiiot.menu.edgeConfigs'),
        icon: <DashboardOutlined style={{ fontSize: 22, color: '#13c2c2' }} />,
        path: '/apps/kuaiiot/edge-configs',
      },
      {
        key: 'tags',
        title: t('app.kuaiiot.menu.tags'),
        icon: <TagsOutlined style={{ fontSize: 22, color: '#fa8c16' }} />,
        path: '/apps/kuaiiot/tags',
      },
    ],
    [t],
  );

  const deviceColumns = useMemo(
    () => [
      {
        title: t('common.code'),
        dataIndex: 'code',
        width: IOT_LIST_COL.code.width,
        ellipsis: true,
      },
      {
        title: t('common.name'),
        dataIndex: 'name',
        width: IOT_LIST_COL.name.width,
        ellipsis: true,
      },
      {
        title: t('app.kuaiiot.field.online'),
        dataIndex: 'is_online',
        width: IOT_LIST_COL.marker.width,
        render: (online: boolean) => renderIotOnlineMarker(t, online),
      },
      {
        title: t('app.kuaiiot.field.lastSeen'),
        dataIndex: 'last_seen_at',
        width: IOT_LIST_COL.datetime.width,
        render: (val: string | undefined) => (val ? formatDateTimeBySiteSetting(val) : '-'),
      },
    ],
    [t],
  );

  const connectionColumns = useMemo(
    () => [
      {
        title: t('common.code'),
        dataIndex: 'code',
        width: IOT_LIST_COL.code.width,
        ellipsis: true,
      },
      {
        title: t('common.name'),
        dataIndex: 'name',
        width: IOT_LIST_COL.name.width,
        ellipsis: true,
      },
      {
        title: t('app.kuaiiot.field.health'),
        dataIndex: 'health_status',
        width: IOT_LIST_COL.marker.width,
        render: (val: string) => renderIotHealthMarker(t, val),
      },
    ],
    [t],
  );

  const oeeColumns = useMemo(
    () => [
      {
        title: t('app.kuaiiot.field.equipment'),
        dataIndex: 'equipment_name',
        width: IOT_LIST_COL.name.width,
        ellipsis: true,
      },
      {
        title: t('app.kuaiiot.dashboard.availabilityRate'),
        width: IOT_LIST_COL.count.width,
        render: (_: unknown, row: OeeLiveItem) =>
          row.sensor?.availability_rate != null ? `${row.sensor.availability_rate}%` : '-',
      },
      {
        title: t('app.kuaiiot.dashboard.oeeLiveValue'),
        width: IOT_LIST_COL.count.width,
        render: (_: unknown, row: OeeLiveItem) => (row.oee_live != null ? `${row.oee_live}%` : '-'),
      },
    ],
    [t],
  );

  const edgeColumns = useMemo(
    () => [
      {
        title: t('common.code'),
        dataIndex: 'code',
        width: IOT_LIST_COL.code.width,
        ellipsis: true,
      },
      {
        title: t('common.name'),
        dataIndex: 'name',
        width: IOT_LIST_COL.name.width,
        ellipsis: true,
      },
      {
        title: t('app.kuaiiot.field.agentStatus'),
        dataIndex: 'agent_status',
        width: IOT_LIST_COL.markerMd.width,
        render: (val: string) => renderIotAgentStatusMarker(t, val),
      },
      {
        title: t('app.kuaiiot.field.bufferPending'),
        dataIndex: 'buffer_pending_count',
        width: IOT_LIST_COL.count.width,
        render: (val: number | undefined) => Number(val ?? 0),
      },
    ],
    [t],
  );

  const hasOeeData = oeeItems.some(
    (row) => row.oee_live != null || row.sensor?.availability_rate != null,
  );

  const masonryEmptyFallback = resolveMasonryEmptyFallback(loading, [
    opsTodos.length > 0,
    openAlerts.length > 0,
    unhealthyConnections.length > 0,
    offlineRecentDevices.length > 0,
    (summary?.recent_devices?.length ?? 0) > 0,
    edgeIssues.length > 0,
    hasOeeData,
  ]);

  return (
    <ModuleCenterLayout
      moduleHelpKey="kuaiiot"
      loading={loading && !summary}
      kpiRow={<ModuleKpiRow items={kpis} colProps={{ xs: 24, sm: 12, lg: 6 }} />}
      shortcutRow={<ModuleShortcutGrid items={shortcuts} />}
      actionRow={
        <ModuleActionMasonry>
          {showMasonryCard(loading, opsTodos.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaiiot.dashboard.todosTitle')}
              loading={loading}
              masonryWeight={masonryWeightFromRows(opsTodos.length)}
            >
              <ModuleTodoList items={opsTodos} emptyText={t('app.kuaiiot.dashboard.noTodos')} />
            </ModuleActionPanel>
          ) : null}

          {showMasonryCard(loading, openAlerts.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaiiot.dashboard.panel.openAlerts')}
              loading={loading}
              masonryWeight={masonryWeightFromRows(openAlerts.length)}
              extra={
                <a onClick={() => navigate('/apps/kuaiiot/alerts')}>
                  {t('app.kuaiiot.dashboard.viewAll')}
                </a>
              }
            >
              <ModuleFeedList items={alertFeedItems} emptyText={t('common.noData')} />
            </ModuleActionPanel>
          ) : null}

          {showMasonryCard(loading, unhealthyConnections.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaiiot.dashboard.panel.unhealthyConnections')}
              loading={loading}
              masonryWeight={masonryWeightFromRows(unhealthyConnections.length)}
              extra={
                <a onClick={() => navigate('/apps/kuaiiot/connections')}>
                  {t('app.kuaiiot.dashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                rowKey="uuid"
                pagination={false}
                dataSource={unhealthyConnections.slice(0, 8)}
                columns={connectionColumns}
              />
            </ModuleActionPanel>
          ) : null}

          {showMasonryCard(loading, offlineRecentDevices.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaiiot.dashboard.panel.offlineDevices')}
              loading={loading}
              masonryWeight={masonryWeightFromRows(offlineRecentDevices.length)}
              extra={
                <a onClick={() => navigate('/apps/kuaiiot/devices')}>
                  {t('app.kuaiiot.dashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                rowKey="uuid"
                pagination={false}
                dataSource={offlineRecentDevices}
                columns={deviceColumns}
              />
            </ModuleActionPanel>
          ) : null}

          {showMasonryCard(
            loading,
            (summary?.recent_devices?.length ?? 0) > 0,
            masonryEmptyFallback,
          ) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaiiot.dashboard.recentDevices')}
              loading={loading}
              masonryWeight={masonryWeightFromRows(Math.min(summary?.recent_devices?.length ?? 0, 8))}
              extra={
                <a onClick={() => navigate('/apps/kuaiiot/devices')}>
                  {t('app.kuaiiot.dashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                rowKey="uuid"
                pagination={false}
                dataSource={(summary?.recent_devices ?? []).slice(0, 8)}
                columns={deviceColumns}
              />
            </ModuleActionPanel>
          ) : null}

          {showMasonryCard(loading, edgeIssues.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaiiot.dashboard.panel.edgeAgents')}
              loading={loading}
              masonryWeight={masonryWeightFromRows(edgeIssues.length)}
              extra={
                <a onClick={() => navigate('/apps/kuaiiot/edge-configs')}>
                  {t('app.kuaiiot.dashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                rowKey="uuid"
                pagination={false}
                dataSource={edgeIssues.slice(0, 8)}
                columns={edgeColumns}
              />
            </ModuleActionPanel>
          ) : null}

          {showMasonryCard(loading, hasOeeData, masonryEmptyFallback) ? (
            <ModuleChartPanel
              layout="masonry"
              title={t('app.kuaiiot.dashboard.oeeLive')}
              loading={loading}
              masonryWeight={3}
            >
              <Table
                size="small"
                tableLayout="fixed"
                rowKey="equipment_uuid"
                pagination={false}
                dataSource={oeeItems}
                columns={oeeColumns}
              />
            </ModuleChartPanel>
          ) : null}
        </ModuleActionMasonry>
      }
    />
  );
};

export default KuaiiotDashboardPage;
