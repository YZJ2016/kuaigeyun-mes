/**
 * 阈值告警：登记规则并查看已落库的告警。不新造通知通道。
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Card, Form, Input, InputNumber, Select, Space, Switch, Table, Typography, message } from 'antd';
import { createAlertRule, listAlerts, transitionAlert, type AlertOut } from '../../services/kuaiiot';

const { Title } = Typography;

const OPERATORS = ['gt', 'lt', 'gte', 'lte', 'eq', 'ne'].map((value) => ({ value, label: value }));

export default function AlertsPage() {
  const [rows, setRows] = useState<AlertOut[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await listAlerts();
      setRows(Array.isArray(data) ? data : []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '读取告警失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space>
        <Title level={4} style={{ margin: 0 }}>
          阈值告警
        </Title>
        <Link to="/apps/kuaiiot">返回登记</Link>
      </Space>

      <Card title="新增阈值规则">
        <Form
          layout="inline"
          initialValues={{ operator: 'gt', cooldown_seconds: 300, notify_enabled: false }}
          onFinish={async (values: {
            code: string;
            name: string;
            tag_key: string;
            operator: string;
            threshold_number?: number;
            device_id?: number;
            cooldown_seconds?: number;
            notify_enabled?: boolean;
          }) => {
            try {
              await createAlertRule(values);
              message.success('规则已保存');
              await load();
            } catch (error) {
              message.error(error instanceof Error ? error.message : '保存规则失败');
            }
          }}
        >
          <Form.Item name="code" rules={[{ required: true, message: '请填写编码' }]}>
            <Input placeholder="编码" />
          </Form.Item>
          <Form.Item name="name" rules={[{ required: true, message: '请填写名称' }]}>
            <Input placeholder="名称" />
          </Form.Item>
          <Form.Item name="tag_key" rules={[{ required: true, message: '请填写点位键' }]}>
            <Input placeholder="点位键" />
          </Form.Item>
          <Form.Item name="operator" rules={[{ required: true }]}>
            <Select style={{ width: 100 }} options={OPERATORS} />
          </Form.Item>
          <Form.Item name="threshold_number">
            <InputNumber placeholder="数值阈值" />
          </Form.Item>
          <Form.Item name="device_id">
            <InputNumber placeholder="设备编号" min={1} />
          </Form.Item>
          <Form.Item name="cooldown_seconds">
            <InputNumber min={0} placeholder="冷却秒" />
          </Form.Item>
          <Form.Item name="notify_enabled" valuePropName="checked" label="通知标记">
            <Switch />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            保存规则
          </Button>
        </Form>
      </Card>

      <Card title="告警">
        <Button style={{ marginBottom: 12 }} loading={loading} onClick={load}>
          刷新
        </Button>
        <Table
          rowKey="id"
          pagination={false}
          loading={loading}
          dataSource={rows}
          columns={[
            { title: '点位', dataIndex: 'tag_key' },
            { title: '级别', dataIndex: 'severity' },
            { title: '说明', dataIndex: 'message' },
            { title: '实际值', dataIndex: 'actual_value' },
            { title: '状态', dataIndex: 'status' },
            { title: '触发时间', dataIndex: 'triggered_at' },
            { title: '恢复时间', dataIndex: 'recovered_at' },
            { title: '操作', render: (_, row: AlertOut) => <Space>
              <Button disabled={!!row.acknowledged_at || row.status === 'closed'} onClick={async () => {
                try { await transitionAlert(row.id, 'acknowledge'); await load(); } catch { message.error('确认失败'); }
              }}>确认</Button>
              <Button disabled={row.status === 'closed'} onClick={async () => {
                try { await transitionAlert(row.id, 'close'); await load(); } catch { message.error('处置失败'); }
              }}>处置完成</Button>
            </Space> },
          ]}
        />
      </Card>
    </Space>
  );
}
