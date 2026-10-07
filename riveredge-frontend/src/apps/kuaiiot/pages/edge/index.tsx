import React, { useEffect, useState } from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Switch, Table, message } from 'antd';
import { EdgeConfigOut, listEdgeConfigs, requestTrial, saveEdgeConfig } from './api';
import { DeviceOut, listDevices } from '../../services/kuaiiot';

export default function EdgePage() {
  const [devices, setDevices] = useState<DeviceOut[]>([]);
  const [configs, setConfigs] = useState<EdgeConfigOut[]>([]);
  const [error, setError] = useState<string>();
  const reload = async () => { try { const [d, c] = await Promise.all([listDevices(), listEdgeConfigs()]); setDevices(d); setConfigs(c); } catch (e) { setError(e instanceof Error ? e.message : '读取失败'); } };
  useEffect(() => { void reload(); }, []);
  return <Space direction="vertical" style={{ width: '100%', padding: 16 }}>
    <Alert type="info" showIcon message="现场 Agent 支持 Modbus TCP 保持寄存器读取，通过 HTTP 上报。其他协议需对应驱动，不能作为已接通链路发布。" />
    {error && <Alert type="error" message={error} />}
    <Card title="配置采集点位">
      <Form layout="vertical" initialValues={{ port: 502, unit_id: 1, is_enabled: true, registers: [{ tag_key: '', address: 0, data_type: 'uint16', scale: 1 }] }} onFinish={async (v) => {
        try { await saveEdgeConfig({ code: v.code, name: v.name, device_id: v.device_id, protocol: 'modbus_tcp', is_enabled: v.is_enabled, config: { host: v.host, port: v.port, unit_id: v.unit_id, registers: v.registers, publish: { mode: 'http_ingest' } } }); message.success('配置已保存；需等待 Agent 应用，并通过试读确认'); await reload(); } catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
      }}>
        <Space wrap>
          <Form.Item name="code" label="配置编码" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="device_id" label="登记设备" rules={[{ required: true }]}><Select style={{ width: 240 }} options={devices.map(d => ({ value: d.id, label: `${d.name} (${d.code})` }))} /></Form.Item>
          <Form.Item name="host" label="PLC 地址" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="port" label="端口" rules={[{ required: true }]}><InputNumber min={1} max={65535} /></Form.Item>
          <Form.Item name="unit_id" label="从站地址" rules={[{ required: true }]}><InputNumber min={0} max={255} /></Form.Item>
          <Form.Item name="is_enabled" label="启用" valuePropName="checked"><Switch /></Form.Item>
        </Space>
        <Form.List name="registers" rules={[{ validator: async (_, rows) => { if (!rows?.length) throw new Error('至少配置一个点位'); if (new Set(rows.map((r: any) => r.tag_key)).size !== rows.length) throw new Error('点位标识不能重复'); } }]}>{(fields, { add, remove }, { errors }) => <>
          {fields.map(field => <Space key={field.key} wrap>
            <Form.Item name={[field.name, 'tag_key']} label="点位标识" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name={[field.name, 'address']} label="零基寄存器地址" rules={[{ required: true }]}><InputNumber min={0} max={65534} /></Form.Item>
            <Form.Item name={[field.name, 'data_type']} label="类型（大端序）" rules={[{ required: true }]}><Select style={{ width: 130 }} options={['bool', 'int16', 'uint16', 'int32', 'uint32', 'float32'].map(value => ({ value, label: value }))} /></Form.Item>
            <Form.Item name={[field.name, 'scale']} label="换算倍率" rules={[{ required: true }]}><InputNumber /></Form.Item>
            <Button onClick={() => remove(field.name)}>移除</Button>
          </Space>)}
          <Form.ErrorList errors={errors} /><Button onClick={() => add({ address: 0, data_type: 'uint16', scale: 1 })}>添加点位</Button>
        </>}</Form.List>
        <Button type="primary" htmlType="submit" style={{ marginTop: 16 }}>保存配置</Button>
      </Form>
    </Card>
    <Card title="应用版本与现场试读" extra={<Button onClick={() => void reload()}>刷新结果</Button>}>
      {configs.map(c => <Card key={c.id} size="small" title={`${c.name} · 配置版本 ${c.config_version} · Agent 已应用 ${c.agent_config_version ?? "未知"} · ${c.agent_status}`} extra={<Button disabled={c.protocol !== 'modbus_tcp' || !c.is_enabled} onClick={async () => { try { await requestTrial(c.id); message.info('试读请求已提交，等待 Agent 心跳回传后刷新结果'); await reload(); } catch (e) { setError(e instanceof Error ? e.message : '试读失败'); } }}>现场试读</Button>}>
        {c.trial_result ? <Table pagination={false} size="small" rowKey="key" dataSource={Object.entries(c.trial_result.tags).map(([key, value]) => ({ key, raw: JSON.stringify(c.trial_result?.raw_values?.[key] ?? null), value: JSON.stringify(value), quality: c.trial_result?.qualities?.[key] ?? '未知' }))} columns={[{ title: '点位', dataIndex: 'key' }, { title: '原始寄存器', dataIndex: 'raw' }, { title: '换算结果', dataIndex: 'value' }, { title: '质量', dataIndex: 'quality' }]} footer={() => `试读版本 ${c.trial_result?.config_version}，回传时间 ${c.trial_result?.received_at}`} /> : <span>{c.trial_request_uuid ? '等待试读结果' : '尚未试读'}</span>}
      </Card>)}
    </Card>
  </Space>;
}
