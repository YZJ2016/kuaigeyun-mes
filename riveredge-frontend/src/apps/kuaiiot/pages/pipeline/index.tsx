/**
 * 数采链路：连接源 → 设备 → 点位 → MES 设备 四列关联视图。
 * 数据来自 listConnections / listDevices / listTags 与设备运营馈送（或星制造设备
 * 列表兜底），在前端现建关联图。点击节点只高亮同一条关联路径；节点可 Tab 聚焦，
 * Enter/Space 触发；高亮同时用描边加粗、图标和透明度表达，不只看颜色。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Empty, Row, Space, Spin, Typography, theme } from 'antd';
import { LinkOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  HealthStatusTag,
  OnlineTag,
  ValueTypeTag,
} from '../../components/status-tags';
import { formatDateTimeBySiteSetting } from '../../../../utils/format';
import type { ConnectionOut, DeviceOut, TagOut } from '../../services/kuaiiot';
import { loadPipelineSources, type PipelineEquipment, type PipelineSources } from './api';

const { Title, Text } = Typography;

type NodeKind = 'connection' | 'device' | 'tag' | 'equipment';
type Selection = { kind: NodeKind; id: string } | null;

function nodeKey(kind: NodeKind, id: string | number): string {
  return `${kind}:${id}`;
}

function PipelineNode({
  title,
  subtitle,
  status,
  active,
  dimmed,
  onToggle,
}: {
  title: string;
  subtitle?: React.ReactNode;
  status?: React.ReactNode;
  active: boolean;
  dimmed: boolean;
  onToggle: () => void;
}) {
  const { token } = theme.useToken();
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={active}
      onClick={onToggle}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onToggle();
        }
      }}
      style={{
        display: 'block',
        width: '100%',
        padding: '8px 10px',
        marginBottom: 8,
        cursor: 'pointer',
        borderRadius: token.borderRadius,
        border: active ? `2px solid ${token.colorPrimary}` : `1px ${dimmed ? 'dashed' : 'solid'} ${token.colorBorder}`,
        background: active ? token.colorPrimaryBg : token.colorBgContainer,
        opacity: dimmed ? 0.4 : 1,
        fontWeight: active ? 600 : 400,
      }}
    >
      <Space size={6} wrap>
        {active ? <LinkOutlined style={{ color: token.colorPrimary }} aria-hidden /> : null}
        <Text strong={active}>{title}</Text>
        {status}
      </Space>
      {subtitle ? (
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {subtitle}
          </Text>
        </div>
      ) : null}
    </div>
  );
}

function Column({
  title,
  count,
  error,
  emptyText,
  children,
}: {
  title: string;
  count?: number;
  error?: string;
  emptyText: string;
  children: React.ReactNode;
}) {
  return (
    <Card size="small" title={`${title}（${count ?? '—'}）`} style={{ height: '100%' }}>
      {error ? (
        <Alert type="warning" showIcon message={`数据不可用：${error}`} />
      ) : (
        <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
          {count === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} /> : children}
        </div>
      )}
    </Card>
  );
}

export default function PipelinePage() {
  const [sources, setSources] = useState<PipelineSources>();
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Selection>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSources(await loadPipelineSources());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const connections = useMemo(() => sources?.connections ?? [], [sources]);
  const devices = useMemo(() => sources?.devices ?? [], [sources]);
  const tags = useMemo(() => sources?.tags ?? [], [sources]);
  const equipment = useMemo(() => sources?.equipment ?? [], [sources]);
  const errors = sources?.errors ?? {};

  const deviceById = useMemo(() => new Map(devices.map((d) => [d.id, d])), [devices]);
  const tagById = useMemo(() => new Map(tags.map((t) => [t.id, t])), [tags]);
  const equipmentByUuid = useMemo(() => new Map(equipment.map((e) => [e.uuid, e])), [equipment]);
  const tagsByDevice = useMemo(() => {
    const map = new Map<number, TagOut[]>();
    for (const tag of tags) {
      const list = map.get(tag.device_id) ?? [];
      list.push(tag);
      map.set(tag.device_id, list);
    }
    return map;
  }, [tags]);
  const devicesByConnection = useMemo(() => {
    const map = new Map<number, DeviceOut[]>();
    for (const device of devices) {
      if (device.connection_id == null) continue;
      const list = map.get(device.connection_id) ?? [];
      list.push(device);
      map.set(device.connection_id, list);
    }
    return map;
  }, [devices]);
  const devicesByEquipment = useMemo(() => {
    const map = new Map<string, DeviceOut[]>();
    for (const device of devices) {
      if (!device.equipment_uuid) continue;
      const list = map.get(device.equipment_uuid) ?? [];
      list.push(device);
      map.set(device.equipment_uuid, list);
    }
    return map;
  }, [devices]);

  /** 同一关联路径：选中点向上补连接、向下补点位、横向补 MES 设备。 */
  const highlighted = useMemo(() => {
    const keys = new Set<string>();
    if (!selected) return keys;
    const addDevice = (device: DeviceOut | undefined) => {
      if (!device) return;
      keys.add(nodeKey('device', device.id));
      if (device.connection_id != null) keys.add(nodeKey('connection', device.connection_id));
      if (device.equipment_uuid) keys.add(nodeKey('equipment', device.equipment_uuid));
      for (const tag of tagsByDevice.get(device.id) ?? []) keys.add(nodeKey('tag', tag.id));
    };
    if (selected.kind === 'connection') {
      keys.add(nodeKey('connection', selected.id));
      for (const device of devicesByConnection.get(Number(selected.id)) ?? []) addDevice(device);
    } else if (selected.kind === 'device') {
      addDevice(deviceById.get(Number(selected.id)));
    } else if (selected.kind === 'tag') {
      keys.add(nodeKey('tag', selected.id));
      addDevice(deviceById.get(tagById.get(Number(selected.id))?.device_id ?? -1));
    } else {
      keys.add(nodeKey('equipment', selected.id));
      for (const device of devicesByEquipment.get(selected.id) ?? []) addDevice(device);
    }
    return keys;
  }, [selected, devicesByConnection, devicesByEquipment, deviceById, tagById, tagsByDevice]);

  const toggle = (kind: NodeKind, id: string | number) => {
    const idText = String(id);
    setSelected((current) =>
      current && current.kind === kind && current.id === idText ? null : { kind, id: idText },
    );
  };

  const isActive = (kind: NodeKind, id: string | number) => highlighted.has(nodeKey(kind, id));
  const isDimmed = (kind: NodeKind, id: string | number) =>
    highlighted.size > 0 && !isActive(kind, id);

  const namesInPath = (kind: NodeKind): string => {
    const names: string[] = [];
    if (kind === 'connection') {
      for (const c of connections) if (isActive('connection', c.id)) names.push(c.name || c.code || `#${c.id}`);
    } else if (kind === 'device') {
      for (const d of devices) if (isActive('device', d.id)) names.push(d.name || d.code || `#${d.id}`);
    } else if (kind === 'tag') {
      for (const t of tags) if (isActive('tag', t.id)) names.push(t.name || t.tag_key || `#${t.id}`);
    } else {
      for (const key of highlighted) {
        if (!key.startsWith('equipment:')) continue;
        const uuid = key.slice('equipment:'.length);
        const row = equipmentByUuid.get(uuid);
        names.push(row ? row.name || row.code : `未取到名称 ${uuid.slice(0, 8)}`);
      }
    }
    if (!names.length) return '—';
    return names.length > 3 ? `${names.slice(0, 3).join('、')} 等 ${names.length} 项` : names.join('、');
  };

  const countLabel = (label: string, count?: number, error?: string) => (
    <div style={{ flex: '1 1 120px', minWidth: 120 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {label}
      </Text>
      <div>
        <Title level={4} style={{ margin: 0 }}>
          {error ? '—' : count ?? '—'}
        </Title>
      </div>
    </div>
  );

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space wrap>
        <Title level={4} style={{ margin: 0 }}>
          数采链路
        </Title>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>
          刷新
        </Button>
      </Space>
      <Text type="secondary">
        点击或用 Tab + Enter/Space 选中节点，高亮同一条「连接源 → 设备 → 点位 → MES 设备」链路；再次触发取消选中。
      </Text>

      {loading && !sources ? (
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <Spin size="large" />
        </div>
      ) : (
        <>
          <Card size="small">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
              {countLabel('连接源', sources ? connections.length : undefined, errors.connections)}
              {countLabel('设备', sources ? devices.length : undefined, errors.devices)}
              {countLabel('点位', sources ? tags.length : undefined, errors.tags)}
              {countLabel('MES 设备', sources ? equipment.length : undefined, errors.equipment)}
            </div>
          </Card>

          {selected ? (
            <Alert
              type="info"
              showIcon
              message={
                <span>
                  当前链路：连接源 <Text strong>{namesInPath('connection')}</Text> → 设备{' '}
                  <Text strong>{namesInPath('device')}</Text> → 点位{' '}
                  <Text strong>{namesInPath('tag')}</Text> → MES 设备{' '}
                  <Text strong>{namesInPath('equipment')}</Text>
                </span>
              }
            />
          ) : null}

          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} xl={6}>
              <Column
                title="连接源"
                count={sources && !errors.connections ? connections.length : undefined}
                error={errors.connections}
                emptyText="暂无连接"
              >
                {connections.map((conn: ConnectionOut) => (
                  <PipelineNode
                    key={conn.id}
                    title={conn.name || conn.code || `#${conn.id}`}
                    subtitle={`${conn.connection_type} · 关联设备 ${devicesByConnection.get(conn.id)?.length ?? 0} 台`}
                    status={<HealthStatusTag value={conn.health_status} />}
                    active={isActive('connection', conn.id)}
                    dimmed={isDimmed('connection', conn.id)}
                    onToggle={() => toggle('connection', conn.id)}
                  />
                ))}
              </Column>
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Column
                title="设备"
                count={sources && !errors.devices ? devices.length : undefined}
                error={errors.devices}
                emptyText="暂无设备"
              >
                {devices.map((device: DeviceOut) => (
                  <PipelineNode
                    key={device.id}
                    title={device.name || device.code || `#${device.id}`}
                    subtitle={
                      <>
                        {`点位 ${tagsByDevice.get(device.id)?.length ?? 0} 个 · 最近上报 `}
                        {device.last_seen_at ? formatDateTimeBySiteSetting(device.last_seen_at, '—') : '—'}
                      </>
                    }
                    status={<OnlineTag online={device.is_online} />}
                    active={isActive('device', device.id)}
                    dimmed={isDimmed('device', device.id)}
                    onToggle={() => toggle('device', device.id)}
                  />
                ))}
              </Column>
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Column
                title="点位"
                count={sources && !errors.tags ? tags.length : undefined}
                error={errors.tags}
                emptyText="暂无点位"
              >
                {tags.map((tag: TagOut) => (
                  <PipelineNode
                    key={tag.id}
                    title={tag.name || tag.tag_key || `#${tag.id}`}
                    subtitle={`${tag.tag_key} · ${deviceById.get(tag.device_id)?.name ?? `设备 #${tag.device_id}`}`}
                    status={<ValueTypeTag value={tag.value_type} />}
                    active={isActive('tag', tag.id)}
                    dimmed={isDimmed('tag', tag.id)}
                    onToggle={() => toggle('tag', tag.id)}
                  />
                ))}
              </Column>
            </Col>
            <Col xs={24} sm={12} xl={6}>
              <Column
                title="MES 设备"
                count={sources && !errors.equipment ? equipment.length : undefined}
                error={errors.equipment}
                emptyText="暂无绑定的 MES 设备"
              >
                {equipment.map((row: PipelineEquipment) => (
                  <PipelineNode
                    key={row.uuid}
                    title={row.name || row.code || row.uuid.slice(0, 8)}
                    subtitle={`${row.code} · 绑定设备 ${devicesByEquipment.get(row.uuid)?.length ?? 0} 台`}
                    active={isActive('equipment', row.uuid)}
                    dimmed={isDimmed('equipment', row.uuid)}
                    onToggle={() => toggle('equipment', row.uuid)}
                  />
                ))}
              </Column>
            </Col>
          </Row>
        </>
      )}
    </Space>
  );
}
