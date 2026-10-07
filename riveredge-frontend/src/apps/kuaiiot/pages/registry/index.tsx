/**
 * 登记连接、IoT 设备、点位，并查看该设备最新快照。
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Card, Form, Input, Select, Space, Table, Typography, message } from 'antd';
import {
  createConnection,
  createDevice,
  createTag,
  listSnapshots,
  listConnections,
  type ConnectionOut,
  type SnapshotOut,
} from '../../services/kuaiiot';
import { getIntegrationConfigListAllMatching, type IntegrationConfig } from '../../../../services/integrationConfig';

const { Title, Text } = Typography;

const CONNECTION_TYPES = [
  { value: 'http', label: 'http' },
  { value: 'mqtt', label: 'mqtt' },
  { value: 'thingsboard', label: 'thingsboard' },
  { value: 'jetlinks', label: 'jetlinks' },
];

const MAP_TARGETS = [
  { value: 'status', label: 'status' },
  { value: 'is_online', label: 'is_online' },
  { value: 'temperature', label: 'temperature' },
  { value: 'pressure', label: 'pressure' },
  { value: 'vibration', label: 'vibration' },
  { value: 'other_parameters', label: 'other_parameters' },
];

const SECTION_TITLE = {
  center: '数采中心',
  connection: '接入配置',
  device: '设备连接',
  tag: '点位映射',
} as const;

export type RegistrySection = keyof typeof SECTION_TITLE;

export default function RegistryPage({ section = 'center' }: { section?: RegistrySection }) {
  const [connectionId, setConnectionId] = useState<number | null>(null);
  const [deviceId, setDeviceId] = useState<number | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotOut[]>([]);
  const [loadingSnapshots, setLoadingSnapshots] = useState(false);
  const [connectionForm] = Form.useForm();
  const [connectionType, setConnectionType] = useState('http');
  const [coreConnections, setCoreConnections] = useState<IntegrationConfig[]>([]);
  const [connections, setConnections] = useState<ConnectionOut[]>([]);
  const [loadingConnections, setLoadingConnections] = useState(false);
  const showConnection = section === 'center' || section === 'connection';
  const showDevice = section === 'center' || section === 'device';
  const showTag = section === 'center' || section === 'tag';
  const showSnapshot = section === 'center';
  useEffect(() => {
    let cancelled = false;
    setLoadingConnections(true);
    const load = async () => {
      try {
        const [core, rows] = await Promise.all([
          showConnection ? getIntegrationConfigListAllMatching({ is_active: true }) : Promise.resolve([]),
          listConnections(),
        ]);
        if (!cancelled) {
          setCoreConnections(core);
          setConnections(rows);
        }
      } catch {
        if (!cancelled) message.error('连接列表加载失败，请刷新重试');
      } finally {
        if (!cancelled) setLoadingConnections(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [showConnection]);
  const eligibleCore = coreConnections.filter((row) => connectionType === 'http'
    ? ['API', 'api', 'Webhook'].includes(row.type) : row.type === connectionType);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Title level={4}>{SECTION_TITLE[section]}</Title>
      <Space>
        <Link to="/apps/kuaiiot/alerts">告警</Link>
        <Link to="/apps/kuaiiot/templates">点位模板</Link>
        <Link to="/apps/kuaiiot/products">产品</Link>
        <Link to="/apps/kuaiiot/trend">趋势</Link>
        <Link to="/apps/kuaiiot/groups">分组</Link>
        <Link to="/apps/kuaiiot/commands">指令</Link>
        <Link to="/apps/kuaiiot/messages">消息</Link>
      </Space>
      <Text type="secondary">登记连接、IoT 设备与点位后，可查看该设备的最新快照。</Text>

      {showConnection ? <Card title="连接">
        <Form
          form={connectionForm}
          layout="inline"
          onFinish={async (values: { code: string; name: string; connection_type: string; integration_uuid?: string; topic?: string; device_token_path?: string; tags_path?: string; events_path?: string; timestamp_path?: string; idempotency_key_path?: string }) => {
            try {
              const { code, name, connection_type, integration_uuid, ...mapping } = values;
              const config = Object.fromEntries(Object.entries(mapping).filter(([, value]) => value?.trim()));
              const row = await createConnection({ code, name, connection_type, integration_uuid, config });
              setConnectionId(row.id);
              setConnections((rows) => [...rows, row]);
              message.success(`连接已登记，编号 ${row.id}`);
            } catch (error) {
              message.error(error instanceof Error ? error.message : '连接登记失败');
            }
          }}
        >
          <Form.Item name="code" rules={[{ required: true, message: '请填写编码' }]}>
            <Input placeholder="编码" />
          </Form.Item>
          <Form.Item name="name" rules={[{ required: true, message: '请填写名称' }]}>
            <Input placeholder="名称" />
          </Form.Item>
          <Form.Item name="connection_type" initialValue="http" rules={[{ required: true }]}>
            <Select style={{ width: 160 }} options={CONNECTION_TYPES} onChange={(value) => {
              setConnectionType(value);
              connectionForm.resetFields(['integration_uuid', 'topic', 'device_token_path', 'tags_path', 'events_path', 'timestamp_path', 'idempotency_key_path']);
            }} />
          </Form.Item>
          <Form.Item name="integration_uuid" label="公共连接" rules={[{ required: connectionType !== 'http', message: '请选择公共连接' }]}>
            <Select allowClear showSearch optionFilterProp="label" loading={loadingConnections}
              style={{ width: 260 }} placeholder="选择已启用的公共连接"
              options={eligibleCore.map((row) => ({ value: row.uuid, label: `${row.name} (${row.code})` }))} />
          </Form.Item>
          {connectionType === 'mqtt' ? <Form.Item name="topic" label="订阅主题"><Input placeholder="plant/+" /></Form.Item> : null}
          {connectionType !== 'http' ? ['device_token_path', 'tags_path', 'events_path', 'timestamp_path', 'idempotency_key_path'].map((key) => (
            <Form.Item key={key} name={key} label={{ device_token_path: '设备凭据路径', tags_path: '点位路径', events_path: '事件路径', timestamp_path: '采样时间路径', idempotency_key_path: '幂等键路径' }[key]}>
              <Input placeholder="载荷中的点分路径" />
            </Form.Item>
          )) : null}
          <Button type="primary" htmlType="submit">
            登记连接
          </Button>
        </Form>
        <Text type="secondary">地址与凭据在公共连接中维护。直接 HTTP 入站可不选公共连接。</Text>
        <Link to="/system/application-connections" style={{ marginLeft: 12 }}>管理公共连接</Link>
      </Card> : null}

      {showDevice ? <Card title="IoT 设备">
        <Form
          layout="inline"
          onFinish={async (values: {
            external_device_id: string;
            code: string;
            name: string;
            equipment_uuid?: string;
          }) => {
            try {
              const row = await createDevice({
                ...values,
                equipment_uuid: values.equipment_uuid || undefined,
                connection_id: connectionId ?? undefined,
              });
              setDeviceId(row.id);
              message.success(`设备已登记，编号 ${row.id}`);
            } catch (error) {
              message.error(error instanceof Error ? error.message : '设备登记失败');
            }
          }}
        >
          <Form.Item label="数采连接">
            <Select allowClear value={connectionId ?? undefined} loading={loadingConnections}
              style={{ width: 220 }} placeholder="选择已登记的数采连接"
              onChange={(value) => setConnectionId(value ?? null)}
              options={connections.map((row) => ({ value: row.id, label: `${row.name} (${row.code})` }))} />
          </Form.Item>
          <Form.Item
            name="external_device_id"
            rules={[{ required: true, message: '请填写外部设备标识' }]}
          >
            <Input placeholder="外部设备标识" />
          </Form.Item>
          <Form.Item name="code" rules={[{ required: true, message: '请填写编码' }]}>
            <Input placeholder="编码" />
          </Form.Item>
          <Form.Item name="name" rules={[{ required: true, message: '请填写名称' }]}>
            <Input placeholder="名称" />
          </Form.Item>
          <Form.Item name="equipment_uuid">
            <Input placeholder="星制造设备 UUID（可空）" />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            登记设备
          </Button>
        </Form>
      </Card> : null}

      {showTag ? <Card title="点位">
        <Form
          layout="inline"
          onFinish={async (values: { tag_key: string; name: string; value_type: string; map_target: string }) => {
            if (deviceId == null) {
              message.error('请先登记 IoT 设备');
              return;
            }
            try {
              await createTag(deviceId, values);
              message.success('点位已登记');
            } catch (error) {
              message.error(error instanceof Error ? error.message : '点位登记失败');
            }
          }}
        >
          <Form.Item name="tag_key" rules={[{ required: true, message: '请填写点位键' }]}>
            <Input placeholder="点位键" />
          </Form.Item>
          <Form.Item name="name" rules={[{ required: true, message: '请填写名称' }]}>
            <Input placeholder="名称" />
          </Form.Item>
          <Form.Item name="value_type" initialValue="number" rules={[{ required: true }]}>
            <Select
              style={{ width: 120 }}
              options={[
                { value: 'number', label: 'number' },
                { value: 'boolean', label: 'boolean' },
                { value: 'text', label: 'text' },
              ]}
            />
          </Form.Item>
          <Form.Item name="map_target" initialValue="temperature" rules={[{ required: true }]}>
            <Select style={{ width: 180 }} options={MAP_TARGETS} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            登记点位
          </Button>
        </Form>
      </Card> : null}

      {showSnapshot ? <Card title="最新快照">
        <Space style={{ marginBottom: 12 }}>
          <Button
            loading={loadingSnapshots}
            onClick={async () => {
              if (deviceId == null) {
                message.error('请先登记 IoT 设备');
                return;
              }
              setLoadingSnapshots(true);
              try {
                const rows = await listSnapshots(deviceId);
                setSnapshots(Array.isArray(rows) ? rows : []);
              } catch (error) {
                message.error(error instanceof Error ? error.message : '读取快照失败');
              } finally {
                setLoadingSnapshots(false);
              }
            }}
          >
            查看最新快照
          </Button>
          <Text>当前设备编号：{deviceId ?? '未登记'}</Text>
        </Space>
        <Table
          rowKey="id"
          pagination={false}
          dataSource={snapshots}
          columns={[
            { title: '点位', dataIndex: 'tag_key' },
            { title: '文本', dataIndex: 'value_text' },
            { title: '数值', dataIndex: 'value_number' },
            { title: '布尔', dataIndex: 'value_bool', render: (value) => (value == null ? '' : String(value)) },
            { title: '采样时间', dataIndex: 'sampled_at' },
          ]}
        />
      </Card> : null}
    </Space>
  );
}
