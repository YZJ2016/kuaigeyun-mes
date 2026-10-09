/**
 * 数采中心：运营总览。KPI 与分区全部来自真实接口：
 * - getDiagnostics：在线/超时/异常连接/最近上报/离线设备/边缘代理/待投递
 * - listAlerts：未确认与打开的告警
 * - getEquipmentOpsFeed(24)：OEE 分区
 * - listMessageLogs：今日点数（按返回的消息追踪现算，最多 100 条）
 * 某源不可用时对应位置显示 “—” 与原因，不补零。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Alert, Empty, Space, Table, Tooltip, Typography } from 'antd';
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
import {
  AgentStatusTag,
  HealthStatusTag,
  OnlineTag,
  SeverityTag,
} from '../../components/status-tags';
import { formatBusinessDateOnly, formatDateTimeBySiteSetting } from '../../../../utils/format';
import type { DiagnosticsOut } from '../../services/kuaiiot';
import { loadDashboardSources, type DashboardSourceKey, type DashboardSources } from './api';

import { ModuleCenterLayout, ModuleKpiRow, ModuleShortcutGrid, ModuleActionMasonry, ModuleActionPanel, ModuleChartPanel, ModuleTodoList, ModuleFeedList } from '../../../kuaizhizao/components/module-center';
import type { ModuleKpiDef } from '../../../kuaizhizao/components/module-center/types';

const { Text } = Typography;

/** 与后端 run_kuaiiot_offline_check 的设备离线口径一致：超过 5 分钟未上报。 */
const STALE_DEVICE_MS = 5 * 60 * 1000;
const SECTION_LIMIT = 8;
const ABNORMAL_HEALTH = new Set(['disconnected', 'unavailable']);

type DiagnosticDevice = DiagnosticsOut['devices'][number];

function fmtTime(value?: string | null): string {
  return value ? formatDateTimeBySiteSetting(value, '—') : '—';
}

function isStale(device: DiagnosticDevice, now: number): boolean {
  if (!device.is_online) return false;
  if (!device.last_seen_at) return true;
  const ts = Date.parse(device.last_seen_at);
  return Number.isNaN(ts) || now - ts > STALE_DEVICE_MS;
}

function isToday(value?: string | null): boolean {
  if (!value) return false;
  return formatBusinessDateOnly(value, '') === formatBusinessDateOnly(new Date(), '');
}

function SectionCard({
  title,
  to,
  error,
  children,
}: {
  title: string;
  to?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <ModuleActionPanel
      layout="masonry"
      title={title}
      extra={to ? <Link to={to}>查看全部</Link> : null}
    >
      {error ? <Alert type="warning" showIcon message={`数据不可用：${error}`} /> : children}
    </ModuleActionPanel>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [sources, setSources] = useState<DashboardSources>();
  const [loading, setLoading] = useState(false);
  const [loadedAt, setLoadedAt] = useState<Date>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSources(await loadDashboardSources());
      setLoadedAt(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const now = Date.now();
  const devices = sources?.diagnostics?.devices ?? [];
  const connections = sources?.diagnostics?.connections ?? [];
  const agents = sources?.diagnostics?.agents ?? [];
  const deliveries = sources?.diagnostics?.deliveries ?? [];
  const alerts = sources?.alerts ?? [];
  const metrics = sources?.feed?.ops_metrics ?? [];
  const errors = sources?.errors ?? {};

  const err = (key: DashboardSourceKey) => errors[key];

  const onlineCount = devices.filter((d) => d.is_online).length;
  const staleDevices = devices.filter((d) => isStale(d, now));
  const offlineDevices = devices.filter((d) => !d.is_online);
  const abnormalConnections = connections.filter((c) => ABNORMAL_HEALTH.has((c.health_status || '').trim()));
  const openAlerts = alerts.filter((a) => (a.status || '').trim() === 'open');
  const abnormalAgents = agents.filter((a) => ['offline', 'error'].includes((a.agent_status || '').trim()));

  const todayPoints = useMemo(() => {
    if (!sources?.messages) return null;
    let total = 0;
    for (const row of sources.messages) {
      if (row.direction !== 'in' || row.msg_type !== 'ingest' || !isToday(row.created_at)) continue;
      const keys = (row.payload as { tag_keys?: unknown } | undefined)?.tag_keys;
      total += Array.isArray(keys) ? keys.length : 1;
    }
    return total;
  }, [sources?.messages]);

  const deviceNameById = useMemo(() => {
    const map = new Map<number, string>();
    for (const d of devices) map.set(d.id, d.name);
    return map;
  }, [devices]);

  const recentDevices = [...devices]
    .sort((a, b) => (Date.parse(b.last_seen_at ?? '') || 0) - (Date.parse(a.last_seen_at ?? '') || 0))
    .slice(0, SECTION_LIMIT);
  const sortedOpenAlerts = [...openAlerts]
    .sort((a, b) => (Date.parse(b.triggered_at) || 0) - (Date.parse(a.triggered_at) || 0))
    .slice(0, SECTION_LIMIT);

  const todos: Array<{ key: string; text: string; to?: string }> = [];
  if (!err('diagnostics')) {
    if (abnormalConnections.length) {
      todos.push({ key: 'conn', text: `${abnormalConnections.length} 个连接健康异常`, to: '/apps/kuaiiot/connections' });
    }
    if (staleDevices.length) {
      todos.push({ key: 'stale', text: `${staleDevices.length} 台设备超过 5 分钟未上报`, to: '/apps/kuaiiot/devices' });
    }
    if (offlineDevices.length) {
      todos.push({ key: 'offline', text: `${offlineDevices.length} 台设备离线`, to: '/apps/kuaiiot/devices' });
    }
    if (abnormalAgents.length) {
      todos.push({ key: 'agent', text: `${abnormalAgents.length} 个边缘代理不在线`, to: '/apps/kuaiiot/edge-configs' });
    }
    if (deliveries.length) {
      todos.push({ key: 'delivery', text: `${deliveries.length} 条历史/通知投递待完成` });
    }
  }
  if (!err('alerts') && openAlerts.length) {
    todos.unshift({ key: 'alert', text: `${openAlerts.length} 条告警未确认`, to: '/apps/kuaiiot/alerts' });
  }

  const kpis: ModuleKpiDef[] = [
    { key: 'online', title: '在线设备', value: err('diagnostics') ? '—' : onlineCount, subtitle: err('diagnostics') ? `不可用：${err('diagnostics')}` : `设备总数 ${devices.length}`, icon: <CloudServerOutlined />, gradient: 'linear-gradient(135deg, #52c41a, #95de64)', sideMetrics: [{label: '超时未上报', value: err('diagnostics') ? '—' : staleDevices.length}], onClick: () => navigate('/apps/kuaiiot/devices') },
    { key: 'points', title: '今日点数', value: err('messages') ? '—' : (todayPoints ?? '—'), subtitle: err('messages') ? `不可用：${err('messages')}` : `最近 ${(sources?.messages ?? []).length} 条消息内统计`, icon: <ApiOutlined />, gradient: 'linear-gradient(135deg, #1890ff, #69c0ff)' },
    { key: 'alerts', title: '未确认告警', value: err('alerts') ? '—' : openAlerts.length, subtitle: err('alerts') ? `不可用：${err('alerts')}` : '待确认告警', icon: <AlertOutlined />, gradient: 'linear-gradient(135deg, #ff4d4f, #ff7875)', onClick: () => navigate('/apps/kuaiiot/alerts') },
    { key: 'connections', title: '异常连接', value: err('diagnostics') ? '—' : abnormalConnections.length, subtitle: err('diagnostics') ? `不可用：${err('diagnostics')}` : '连接健康异常', icon: <LinkOutlined />, gradient: 'linear-gradient(135deg, #fa8c16, #ffc069)', sideMetrics: [{label: '启用连接', value: err('connections') ? '—' : (sources?.connections ?? []).filter(c => c.is_enabled).length}], onClick: () => navigate('/apps/kuaiiot/connections') },
  ];
  return <ModuleCenterLayout loading={loading}
    kpiRow={<ModuleKpiRow items={kpis} colProps={{xs:24, sm:12, lg:6}} />}
    shortcutRow={<ModuleShortcutGrid items={[
      {key:'connections',title:'接入配置',icon:<LinkOutlined />,path:'/apps/kuaiiot/connections'},
      {key:'devices',title:'设备连接',icon:<DeploymentUnitOutlined />,path:'/apps/kuaiiot/devices'},
      {key:'alerts',title:'告警中心',icon:<AlertOutlined />,path:'/apps/kuaiiot/alerts'},
      {key:'pipeline',title:'数采链路',icon:<ClusterOutlined />,path:'/apps/kuaiiot/pipeline'},
      {key:'edge',title:'边缘配置',icon:<DashboardOutlined />,path:'/apps/kuaiiot/edge-configs'},
      {key:'tags',title:'点位映射',icon:<TagsOutlined />,path:'/apps/kuaiiot/tags'},
    ]} />}
    actionRow={<ModuleActionMasonry>
      <SectionCard title="待办事项"><ModuleTodoList items={todos.map(todo => ({id:todo.key,type:'kuaiiot',title:todo.text,priority:['alert','conn'].includes(todo.key)?'high':'medium',status:'pending',link:todo.to,created_at:loadedAt?.toISOString() ?? ''}))} emptyText={Object.keys(errors).length ? '部分数据源不可用，待办无法完整计算' : '暂无待办'} /></SectionCard>
<SectionCard title="打开告警" to="/apps/kuaiiot/alerts" error={err('alerts')}>
          <ModuleFeedList emptyText="无打开告警" items={sortedOpenAlerts.map(row => ({
            id: row.id, title: row.tag_key,
            subtitle: row.message, meta: <Space size={8}><SeverityTag value={row.severity} /><Text type="secondary" style={{fontSize: 11}}>{fmtTime(row.triggered_at)}</Text></Space>,
            onClick: () => navigate('/apps/kuaiiot/alerts'),
          }))} />
        </SectionCard>
<SectionCard title="异常连接" to="/apps/kuaiiot/connections" error={err('diagnostics')}>
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  scroll={{ x: 'max-content' }}
                  dataSource={abnormalConnections.slice(0, SECTION_LIMIT)}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无异常连接" /> }}
                  columns={[
                    {
                      title: '名称',
                      dataIndex: 'name',
                      render: (value: string, row) => <Link to="/apps/kuaiiot/connections">{value || `#${row.id}`}</Link>,
                    },
                    { title: '类型', dataIndex: 'type' },
                    { title: '健康状态', dataIndex: 'health_status', render: (v: string) => <HealthStatusTag value={v} /> },
                    { title: '最近检查', dataIndex: 'last_health_at', render: fmtTime },
                  ]}
                />
              </SectionCard>
<SectionCard title="离线设备" to="/apps/kuaiiot/devices" error={err('diagnostics')}>
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  scroll={{ x: 'max-content' }}
                  dataSource={offlineDevices.slice(0, SECTION_LIMIT)}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无离线设备" /> }}
                  columns={[
                    {
                      title: '设备',
                      dataIndex: 'name',
                      render: (value: string, row) => <Link to="/apps/kuaiiot/devices">{value || `#${row.id}`}</Link>,
                    },
                    { title: '状态', dataIndex: 'is_online', render: (v: boolean) => <OnlineTag online={v} /> },
                    { title: '最近上报', dataIndex: 'last_seen_at', render: fmtTime },
                  ]}
                />
              </SectionCard>
<SectionCard title="最近上报设备" to="/apps/kuaiiot/devices" error={err('diagnostics')}>
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  scroll={{ x: 'max-content' }}
                  dataSource={recentDevices}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无设备" /> }}
                  columns={[
                    {
                      title: '设备',
                      dataIndex: 'name',
                      render: (value: string, row) => <Link to="/apps/kuaiiot/devices">{value || `#${row.id}`}</Link>,
                    },
                    { title: '状态', dataIndex: 'is_online', render: (v: boolean) => <OnlineTag online={v} /> },
                    { title: '最近上报', dataIndex: 'last_seen_at', render: fmtTime },
                  ]}
                />
              </SectionCard>
<SectionCard title="边缘代理" to="/apps/kuaiiot/edge-configs" error={err('diagnostics')}>
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  scroll={{ x: 'max-content' }}
                  dataSource={agents.slice(0, SECTION_LIMIT)}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无边缘配置" /> }}
                  columns={[
                    {
                      title: '配置',
                      dataIndex: 'name',
                      render: (value: string, row) => <Link to="/apps/kuaiiot/edge-configs">{value || `#${row.id}`}</Link>,
                    },
                    { title: 'Agent 状态', dataIndex: 'agent_status', render: (v: string) => <AgentStatusTag value={v} /> },
                    { title: '待补传', dataIndex: 'buffer_pending_count' },
                    { title: '最近心跳', dataIndex: 'last_agent_heartbeat_at', render: fmtTime },
                  ]}
                />
              </SectionCard>
<ModuleChartPanel layout="masonry" title="OEE 实时信号">{err('feed') ? <Alert type="warning" showIcon message={`数据不可用：${err('feed')}`} /> : (
                <Table
                  size="small"
                  rowKey="equipment_uuid"
                  pagination={false}
                  scroll={{ x: 'max-content' }}
                  dataSource={metrics.slice(0, SECTION_LIMIT)}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无绑定 MES 设备" /> }}
                  columns={[
                    { title: 'MES 设备', dataIndex: 'name' },
                    {
                      title: 'Sensor 可用率',
                      dataIndex: 'availability_rate',
                      render: (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`),
                    },
                  {
                      title: 'OEE Live',
                      dataIndex: 'oee_live',
                      render: (v: number | null, row) => <Tooltip title={`覆盖率：${row.coverage_rate == null ? '—' : `${(row.coverage_rate * 100).toFixed(1)}%`}；${row.unavailable_reasons?.join('；') || '近 24 小时实时信号'}`}>{v == null ? '—' : `${(v * 100).toFixed(1)}%`}</Tooltip>,
                    },
                    ]}
                />
              )}</ModuleChartPanel>
    </ModuleActionMasonry>}
  />;
}
