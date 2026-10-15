/**
 * 查看入站、事件、指令和监控写回的消息追踪。
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { UniTable } from '../../../../components/uni-table';
import { Button, Card, Form, InputNumber, Space, Typography, message } from 'antd';
import { listMessageLogs, type MessageLog } from '../../services/registry';

const { Title } = Typography;

export default function MessagesPage({ title = '消息追踪' }: { title?: string }) {
  const [rows, setRows] = useState<MessageLog[]>([]);

  const [form] = Form.useForm();
  const refresh = () => form.submit();

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space>
        <Title level={4} style={{ margin: 0 }}>
          {title}
        </Title>
        <Link to="/apps/kuaiiot">返回登记</Link>
      </Space>
      <Card title="列表">
        <Form
          form={form}
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
        <UniTable
          columnPersistenceId="apps.kuaiiot.pages.messages.list-1"
          viewTypes={['table']}
          showImportButton={false}
          showExportButton={false}
          showFuzzySearch={false}
          showAdvancedSearch={false}
          options={{ reload: refresh }}
          style={{ marginTop: 16 }}
          rowKey="id"
          pagination={false}
          params={{ rows: rows }}
          request={async () => ({ data: rows, total: rows.length, success: true })}
          columns={[
            { title: '设备', dataIndex: 'device_id' },
            { title: '方向', dataIndex: 'direction' },
            { title: '类型', dataIndex: 'msg_type' },
            { title: '结果', dataIndex: 'result' },
            {
              title: '内容',
              dataIndex: 'payload',
              render: (_, row) => JSON.stringify(row.payload || {}),
            },
            { title: '错误', dataIndex: 'error_message' },
          ]}
        />
      </Card>
    </Space>
  );
}
