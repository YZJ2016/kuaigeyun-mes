/**
 * 数采中心：运营总览。KPI 与分区全部来自真实接口：
 * - getDiagnostics：在线/超时/异常连接/最近上报/离线设备/边缘代理/待投递
 * - listAlerts：未确认与打开的告警
 * - getEquipmentOpsFeed(24)：OEE 分区
 * - listMessageLogs：今日点数（按返回的消息追踪现算，最多 100 条）
 * 某源不可用时对应位置显示 “—” 与原因，不补零。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Card, Col, Empty, Row, Space, Spin, Table, Typography, theme } from 'antd';
import {
  AlertOutlined,
  ClusterOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  LinkOutlined,
  ReloadOutlined,
  TagsOutlined,
} from '@ant-design/icons';
import {
  AgentStatusTag,
  AlertStatusTag,
  HealthStatusTag,
  OnlineTag,
  SeverityTag,
} from '../../components/status-tags';
import { formatBusinessDateOnly, formatDateTimeBySiteSetting } from '../../../../utils/format';
import type { DiagnosticsOut } from '../../services/kuaiiot';
import { loadDashboardSources, type DashboardSourceKey, type DashboardSources } from './api';

const { Title, Text } = Typography;
const { useToken } = theme;

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

function KpiCard({ title, value, hint }: { title: string; value: string | number; hint?: string }) {
  return (
    <Card size="small" style={{ flex: '1 1 180px', minWidth: 180 }}>
      <Text type="secondary">{title}</Text>
      <div>
        <Title level={3} style={{ margin: '4px 0' }}>
          {value}
        </Title>
      </div>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {hint ?? ' '}
      </Text>
    </Card>
  );
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
    <Card
      size="small"
      title={title}
      extra={to ? <Link to={to}>查看全部</Link> : null}
      style={{ height: '100%' }}
    >
      {error ? <Alert type="warning" showIcon message={`数据不可用：${error}`} /> : children}
    </Card>
  );
}

export default function DashboardPage() {
  const { token } = useToken();
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

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space wrap>
        <Title level={4} style={{ margin: 0 }}>
          数采中心
        </Title>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>
          刷新
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {loadedAt ? `更新于 ${formatDateTimeBySiteSetting(loadedAt)}` : '进入页面自动加载'}
        </Text>
      </Space>

      {loading && !sources ? (
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <Spin size="large" />
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            <KpiCard
              title="在线设备"
              value={err('diagnostics') ? '—' : `${onlineCount} / ${devices.length}`}
              hint={err('diagnostics') ? `不可用：${err('diagnostics')}` : `超时未上报 ${staleDevices.length} 台 · 在线 / 设备总数`}
            />
            <KpiCard
              title="今日点数"
              value={err('messages') ? '—' : (todayPoints ?? '—')}
              hint={
                err('messages')
                  ? `不可用：${err('messages')}`
                  : `按消息追踪现算，最多覆盖最近 ${(sources?.messages ?? []).length} 条消息`
              }
            />
            <KpiCard
              title="未确认告警"
              value={err('alerts') ? '—' : openAlerts.length}
              hint={err('alerts') ? `不可用：${err('alerts')}` : '状态为未确认的告警记录'}
            />
            <KpiCard
              title="异常连接"
              value={err('diagnostics') ? '—' : abnormalConnections.length}
              hint={err('diagnostics') ? `不可用：${err('diagnostics')}` : `已启用连接 ${err('connections') ? '—' : (sources?.connections ?? []).filter(c => c.is_enabled).length} · 健康状态为已断开或不可用`}
            />
          </div>

          <Card size="small" title="快捷入口">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(128px, 1fr))',
                gap: 12,
              }}
            >
              {[
                { title: '接入配置', path: 'connections', icon: <LinkOutlined /> },
                { title: '设备链接', path: 'devices', icon: <DeploymentUnitOutlined /> },
                { title: '告警中心', path: 'alerts', icon: <AlertOutlined /> },
                { title: '数采链路', path: 'pipeline', icon: <ClusterOutlined /> },
                { title: '边缘配置', path: 'edge-configs', icon: <DashboardOutlined /> },
                { title: '点位映射', path: 'tags', icon: <TagsOutlined /> },
              ].map(({ title, path, icon }) => (
                <Link
                  key={path}
                  to={`/apps/kuaiiot/${path}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    minWidth: 0,
                    color: token.colorText,
                  }}
                >
                  <span
                    style={{
                      width: 32,
                      height: 32,
                      flexShrink: 0,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderRadius: token.borderRadius,
                      background: token.colorPrimaryBg,
                      color: token.colorPrimary,
                      fontSize: 18,
                    }}
                  >
                    {icon}
                  </span>
                  <span>{title}</span>
                </Link>
              ))}
            </div>
          </Card>
          <Card size="small" title="待办">
            {todos.length ? (
              <Space direction="vertical" size={4}>
                {todos.map((todo) =>
                  todo.to ? (
                    <Link key={todo.key} to={todo.to}>
                      {todo.text}
                    </Link>
                  ) : (
                    <Text key={todo.key}>{todo.text}</Text>
                  ),
                )}
              </Space>
            ) : (
              <Text type="secondary">
                {Object.keys(errors).length ? '部分数据源不可用，待办无法完整计算' : '暂无待办'}
              </Text>
            )}
          </Card>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
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
            </Col>
            <Col xs={24} xl={12}>
              <SectionCard title="最近上报" to="/apps/kuaiiot/devices" error={err('diagnostics')}>
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
            </Col>
            <Col xs={24} xl={12}>
              <SectionCard title="OEE 实时（近 24 小时）" error={err('feed')}>
                <Table
                  size="small"
                  rowKey="equipment_uuid"
                  pagination={false}
                  scroll={{ x: 'max-content' }}
                  dataSource={metrics.slice(0, SECTION_LIMIT)}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无绑定 MES 设备" /> }}
                  columns={[
                    { title: '设备', dataIndex: 'name' },
                    {
                      title: 'OEE',
                      dataIndex: 'oee_live',
                      render: (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`),
                    },
                    {
                      title: '可用率',
                      dataIndex: 'availability_rate',
                      render: (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`),
                    },
                    {
                      title: '覆盖率',
                      dataIndex: 'coverage_rate',
                      render: (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`),
                    },
                    {
                      title: '不可用原因',
                      dataIndex: 'unavailable_reasons',
                      render: (v: string[]) => (v && v.length ? v.join('；') : '—'),
                    },
                  ]}
                />
              </SectionCard>
            </Col>
            <Col xs={24} xl={12}>
              <SectionCard title="未确认告警" to="/apps/kuaiiot/alerts" error={err('alerts')}>
                <Table
                  size="small"
                  rowKey="id"
                  pagination={false}
                  scroll={{ x: 'max-content' }}
                  dataSource={sortedOpenAlerts}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无未确认告警" /> }}
                  columns={[
                    {
                      title: '设备',
                      dataIndex: 'device_id',
                      render: (v: number) => (
                        <Link to="/apps/kuaiiot/alerts">{deviceNameById.get(v) ?? `#${v}`}</Link>
                      ),
                    },
                    { title: '级别', dataIndex: 'severity', render: (v: string) => <SeverityTag value={v} /> },
                    { title: '状态', dataIndex: 'status', render: (v: string) => <AlertStatusTag value={v} /> },
                    { title: '说明', dataIndex: 'message', ellipsis: true },
                    { title: '触发时间', dataIndex: 'triggered_at', render: fmtTime },
                  ]}
                />
              </SectionCard>
            </Col>
            <Col xs={24} xl={12}>
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
            </Col>
            <Col xs={24} xl={12}>
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
            </Col>
          </Row>
        </>
      )}
    </Space>
  );
}
