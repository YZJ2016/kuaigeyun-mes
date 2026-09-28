/**
 * 查看入站、事件、指令和监控写回的消息追踪。
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Card, Form, InputNumber, Space, Table, Typography, message } from 'antd';
import { listMessageLogs, type MessageLog } from '../../services/kuaiiot';

const { Title } = Typography;

export default function MessagesPage() {
  const [rows, setRows] = useState<MessageLog[]>([]);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space>
        <Title level={4} style={{ margin: 0 }}>
          消息追踪
        </Title>
        <Link to="/apps/kuaiiot">返回登记</Link>
      </Space>
      <Card title="列表">
        <Form
          layout="inline"
          onFinish={async (values: { device_id?: number }) => {
            try {
              const data = await listMessageLogs(values.device_id);
              setRows(Array.isArray(data) ? data : []);
            } catch (error) {
              message.error(error instanceof Error ? error.message : '读取消息失败');
            }
          }}
        >
          <Form.Item name="device_id">
            <InputNumber placeholder="设备编号，可空" min={1} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            查询
          </Button>
        </Form>
        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          pagination={false}
          dataSource={rows}
          columns={[
            { title: '设备', dataIndex: 'device_id' },
            { title: '方向', dataIndex: 'direction' },
            { title: '类型', dataIndex: 'msg_type' },
            { title: '结果', dataIndex: 'result' },
            {
              title: '内容',
              dataIndex: 'payload',
              render: (payload: MessageLog['payload']) => JSON.stringify(payload || {}),
            },
            { title: '错误', dataIndex: 'error_message' },
          ]}
        />
      </Card>
    </Space>
  );
}
