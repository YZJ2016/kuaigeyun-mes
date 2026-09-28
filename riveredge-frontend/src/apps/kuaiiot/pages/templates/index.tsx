/**
 * 套用通用产线、注塑机、CNC 三套点位模板。只写点位定义。
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Card, Form, InputNumber, Select, Space, Typography, message } from 'antd';
import { applyTemplate, listTemplates, type TemplateOut } from '../../services/kuaiiot';

const { Title, Paragraph } = Typography;

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<TemplateOut[]>([]);

  useEffect(() => {
    listTemplates()
      .then((rows) => setTemplates(Array.isArray(rows) ? rows : []))
      .catch((error: unknown) => {
        message.error(error instanceof Error ? error.message : '读取模板失败');
      });
  }, []);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space>
        <Title level={4} style={{ margin: 0 }}>
          点位模板
        </Title>
        <Link to="/apps/kuaiiot">返回登记</Link>
      </Space>
      <Paragraph type="secondary">套用后只写入该 IoT 设备的点位定义。</Paragraph>
      <Card title="套用">
        <Form
          layout="inline"
          onFinish={async (values: { device_id: number; code: string }) => {
            try {
              const result = await applyTemplate(values.device_id, values.code);
              message.success(`已套用 ${result.code}，点位 ${result.tag_keys.join('、')}`);
            } catch (error) {
              message.error(error instanceof Error ? error.message : '套用失败');
            }
          }}
        >
          <Form.Item name="device_id" rules={[{ required: true, message: '请填写设备编号' }]}>
            <InputNumber min={1} placeholder="IoT 设备编号" />
          </Form.Item>
          <Form.Item name="code" rules={[{ required: true, message: '请选择模板' }]}>
            <Select
              style={{ width: 220 }}
              placeholder="模板"
              options={templates.map((item) => ({
                value: item.code,
                label: `${item.name}（${item.tags.length} 个点位）`,
              }))}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            套用模板
          </Button>
        </Form>
      </Card>
    </Space>
  );
}
