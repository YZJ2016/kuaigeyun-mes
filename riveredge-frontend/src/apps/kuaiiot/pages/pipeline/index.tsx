import React, { useEffect, useState } from 'react';
import { Alert, Button, Card, DatePicker, Form, InputNumber, Select, Space, Table, Typography, message } from 'antd';
import dayjs from 'dayjs';
import { apiRequest } from '../../../../services/api';
import { listDevices, type DeviceOut } from '../../services/kuaiiot';
import { equipmentApi } from '../../../kuaizhizao/services/equipment';

type Diagnostics = {
  connections: Array<{ id: number; name: string; type: string; health_status: string; last_health_at?: string }>;
  devices: Array<{ id: number; name: string; is_online: boolean; last_seen_at?: string }>;
  agents: Array<{ id: number; name: string; agent_status: string; buffer_pending_count: number; last_agent_heartbeat_at?: string }>;
  deliveries: Array<{ id: number; kind: string; status: string; attempts: number; last_error?: string }>;
};

export default function PipelinePage() {
  const [data, setData] = useState<Diagnostics>();
  const [devices, setDevices] = useState<DeviceOut[]>([]);
  const [metrics, setMetrics] = useState<Array<{ equipment_uuid: string; name: string; oee_live: number | null; performance_rate: number | null; coverage_rate: number | null; unavailable_reasons: string[] }>>([]);
  const [metricsError, setMetricsError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [oeeForm] = Form.useForm();
  const load = async () => {
    setLoading(true);
    try {
      const [result, registered] = await Promise.all([apiRequest<Diagnostics>('/apps/kuaiiot/diagnostics'), listDevices()]);
      setData(result); setDevices(registered);
      try {
        const feed = await apiRequest<{ ops_metrics: typeof metrics }>('/apps/kuaiiot/analytics/equipment-ops-feed');
        setMetrics(feed.ops_metrics); setMetricsError(undefined);
      } catch { setMetricsError('OEE 馈送读取失败，请核对报表数据源配置与访问权限'); }
    } catch { message.error('诊断读取失败'); } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const loadOee = async (uuid: string) => {
    try {
      const row = await equipmentApi.get(uuid) as { technical_parameters?: { oee?: { ideal_cycle_seconds?: number; planned_windows?: Array<{ start: string; end: string }> } } };
      const config = row.technical_parameters?.oee;
      oeeForm.setFieldsValue({ ideal_cycle_seconds: config?.ideal_cycle_seconds,
        planned_windows: (config?.planned_windows ?? []).map((w) => ({ range: [dayjs(w.start), dayjs(w.end)] })) });
    } catch { message.error('设备 OEE 配置读取失败'); }
  };
  return <Space direction="vertical" style={{ width: '100%', padding: 16 }} size={16}>
    <Space><Typography.Title level={4} style={{ margin: 0 }}>数采链路诊断</Typography.Title><Button loading={loading} onClick={load}>刷新</Button></Space>
    <Alert type="info" showIcon message="按连接、设备入站、Agent、历史与通知投递逐段检查。认证通过不代表设备指令成功；无数采覆盖时不展示完整 OEE。" />
    <Card title="连接"><Table rowKey="id" dataSource={data?.connections ?? []} columns={[
      { title: '名称', dataIndex: 'name' }, { title: '类型', dataIndex: 'type' }, { title: '健康状态', dataIndex: 'health_status' }, { title: '检查时间', dataIndex: 'last_health_at' },
    ]} /></Card>
    <Card title="设备入站"><Table rowKey="id" dataSource={data?.devices ?? []} columns={[
      { title: '设备', dataIndex: 'name' }, { title: '在线', dataIndex: 'is_online', render: (value: boolean) => value ? '在线' : '离线' }, { title: '最近入站', dataIndex: 'last_seen_at' },
    ]} /></Card>
    <Card title="Agent 与缓存"><Table rowKey="id" dataSource={data?.agents ?? []} columns={[
      { title: '配置', dataIndex: 'name' }, { title: '状态', dataIndex: 'agent_status' }, { title: '待补传', dataIndex: 'buffer_pending_count' }, { title: '最近心跳', dataIndex: 'last_agent_heartbeat_at' },
    ]} /></Card>
    <Card title="待完成的历史和通知投递（最多 100 条）"><Table rowKey="id" dataSource={data?.deliveries ?? []} columns={[
      { title: '类型', dataIndex: 'kind' }, { title: '状态', dataIndex: 'status' }, { title: '尝试次数', dataIndex: 'attempts' }, { title: '原因', dataIndex: 'last_error' },
    ]} /></Card>
    <Card title="最近 24 小时 OEE 与可用性">
      {metricsError && <Alert type="warning" message={metricsError} />}
      <Table rowKey="equipment_uuid" dataSource={metrics} columns={[
        { title: '设备', dataIndex: 'name' },
        { title: 'OEE', dataIndex: 'oee_live', render: (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(2)}%` },
        { title: '性能因子', dataIndex: 'performance_rate', render: (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(2)}%` },
        { title: '覆盖率', dataIndex: 'coverage_rate', render: (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(2)}%` },
        { title: '不可用原因', dataIndex: 'unavailable_reasons', render: (value: string[]) => value?.join('；') || '—' },
      ]} />
    </Card>
    <Card title="OEE 计算依据">
      <Typography.Paragraph type="secondary">维护理想节拍和实际计划生产窗口。两端按同一口径计算；计划时间不使用默认每天 8 小时。保存需要制造设备编辑权限。</Typography.Paragraph>
      <Form form={oeeForm} layout="vertical" onFinish={async (values) => {
        try {
          const row = await equipmentApi.get(values.equipment_uuid) as { technical_parameters?: Record<string, unknown> };
          await equipmentApi.update(values.equipment_uuid, { technical_parameters: { ...(row.technical_parameters ?? {}), oee: {
            ideal_cycle_seconds: values.ideal_cycle_seconds,
            planned_windows: (values.planned_windows ?? []).map((w: { range: [dayjs.Dayjs, dayjs.Dayjs] }) => ({ start: w.range[0].toISOString(), end: w.range[1].toISOString() })),
          } } });
          message.success('OEE 依据已保存');
        } catch { message.error('保存失败，请检查窗口重叠、理想节拍和编辑权限'); }
      }}>
        <Form.Item name="equipment_uuid" label="绑定的制造设备" rules={[{ required: true }]}>
          <Select showSearch optionFilterProp="label" options={devices.filter((d) => d.equipment_uuid).map((d) => ({ value: d.equipment_uuid, label: d.name }))} onChange={loadOee} />
        </Form.Item>
        <Form.Item name="ideal_cycle_seconds" label="理想节拍（秒/件）" rules={[{ required: true }]}><InputNumber min={0.001} /></Form.Item>
        <Form.List name="planned_windows">{(fields, { add, remove }) => <>
          {fields.map((field) => <Space key={field.key}><Form.Item name={[field.name, 'range']} label="计划生产窗口" rules={[{ required: true }]}><DatePicker.RangePicker showTime /></Form.Item><Button onClick={() => remove(field.name)}>移除</Button></Space>)}
          <Button onClick={() => add()}>添加计划窗口</Button>
        </>}</Form.List>
        <Button type="primary" htmlType="submit" style={{ marginTop: 16 }}>保存计算依据</Button>
      </Form>
    </Card>
  </Space>;
}
