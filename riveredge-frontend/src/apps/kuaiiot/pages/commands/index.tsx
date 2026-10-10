/**
 * 按产品指令向设备下发。执行结果由边缘心跳带回。
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Card, Form, Input, InputNumber, Space, Table, Typography, message } from 'antd';
import { createDeviceCommand, listDeviceCommands, type DeviceCommand } from '../../services/registry';

const { Title, Text } = Typography;

export default function CommandsPage() {
  const [deviceId, setDeviceId] = useState<number | null>(null);
  const [rows, setRows] = useState<DeviceCommand[]>([]);

  const load = async (id: number) => {
    const data = await listDeviceCommands(id);
    setRows(Array.isArray(data) ? data : []);
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space>
        <Title level={4} style={{ margin: 0 }}>
          设备指令
        </Title>
        <Link to="/apps/kuaiiot">返回登记</Link>
      </Space>
      <Text type="secondary">指令进入待下发后，由设备心跳取走。通道只有边缘心跳。</Text>
      <Card title="下发">
        <Form
          layout="inline"
          initialValues={{ params_json: '{"value": 1}' }}
          onFinish={async (values: { device_id: number; function_key: string; params_json: string }) => {
            let params: Record<string, unknown> = {};
            try {
              const parsed = JSON.parse(values.params_json || '{}');
              if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
                throw new Error('参数必须是对象');
              }
              params = parsed as Record<string, unknown>;
            } catch (error) {
              message.error(error instanceof Error ? error.message : '参数不是合法 JSON');
              return;
            }
            try {
              await createDeviceCommand(values.device_id, { function_key: values.function_key, params });
              setDeviceId(values.device_id);
              message.success('指令已创建');
              await load(values.device_id);
            } catch (error) {
              message.error(error instanceof Error ? error.message : '创建指令失败');
            }
          }}
        >
          <Form.Item name="device_id" rules={[{ required: true, message: '请填写设备编号' }]}>
            <InputNumber placeholder="设备编号" min={1} />
          </Form.Item>
          <Form.Item name="function_key" rules={[{ required: true, message: '请填写指令键' }]}>
            <Input placeholder="指令键" />
          </Form.Item>
          <Form.Item name="params_json" rules={[{ required: true, message: '请填写参数' }]}>
            <Input placeholder='{"value": 1}' style={{ width: 220 }} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            创建
          </Button>
          <Button
            onClick={() => {
              if (deviceId == null) {
                message.error('请先创建或填写设备编号');
                return;
              }
              load(deviceId).catch((error) => message.error(error instanceof Error ? error.message : '读取失败'));
            }}
          >
            刷新
          </Button>
        </Form>
        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          pagination={false}
          dataSource={rows}
          columns={[
            { title: '指令', dataIndex: 'function_key' },
            { title: '状态', dataIndex: 'status' },
            { title: '通道', dataIndex: 'dispatch_channel' },
            { title: '错误', dataIndex: 'error_message' },
          ]}
        />
      </Card>
    </Space>
  );
}
