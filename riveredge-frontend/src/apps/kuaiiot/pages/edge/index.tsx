/**
 * 编辑边缘配置。校验失败时展示服务端指出的缺失字段。
 * OPC UA、S7、modbus_rtu 只保存配置。现场 Agent 只轮询 modbus_tcp。
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Switch, Typography, message } from 'antd';
import { saveEdgeConfig } from './api';

const { Title, Paragraph } = Typography;

const PROTOCOLS = ['modbus_tcp', 'modbus_rtu', 'opc_ua', 's7'].map((value) => ({ value, label: value }));
const PUBLISH_MODES = ['http_ingest', 'mqtt'].map((value) => ({ value, label: value }));

const DEFAULT_CONFIG = `{
  "host": "127.0.0.1",
  "port": 502,
  "unit_id": 1,
  "registers": [{ "tag_key": "temp", "address": 0, "data_type": "float32" }]
}`;

export default function EdgePage() {
  const [fieldError, setFieldError] = useState<string | null>(null);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space>
        <Title level={4} style={{ margin: 0 }}>
          边缘配置
        </Title>
        <Link to="/apps/kuaiiot">返回登记</Link>
      </Space>
      <Paragraph type="secondary">
        可保存 modbus_tcp、modbus_rtu、opc_ua、s7。校验失败会指出缺哪个字段。现场 Agent 只轮询 modbus_tcp，保存 mqtt
        也不会建立订阅。
      </Paragraph>
      {fieldError ? <Alert type="error" showIcon message="配置未保存" description={fieldError} /> : null}
      <Card title="保存">
        <Form
          layout="vertical"
          initialValues={{ protocol: 'modbus_tcp', publish_mode: 'http_ingest', is_enabled: true, config_json: DEFAULT_CONFIG }}
          onFinish={async (values: {
            code: string;
            name: string;
            device_id: number;
            protocol: string;
            publish_mode: string;
            is_enabled: boolean;
            config_json: string;
          }) => {
            setFieldError(null);
            let parsed: Record<string, unknown>;
            try {
              const raw = JSON.parse(values.config_json);
              if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
                throw new Error('config 必须是对象');
              }
              parsed = raw as Record<string, unknown>;
            } catch (error) {
              const text = error instanceof Error ? error.message : 'config 不是合法 JSON';
              setFieldError(text);
              message.error(text);
              return;
            }
            const publish = parsed.publish;
            const publishObject =
              publish !== null && typeof publish === 'object' && !Array.isArray(publish)
                ? { ...(publish as Record<string, unknown>) }
                : {};
            publishObject.mode = values.publish_mode;
            parsed.publish = publishObject;
            try {
              const saved = await saveEdgeConfig({
                code: values.code,
                name: values.name,
                device_id: values.device_id,
                protocol: values.protocol,
                config: parsed,
                is_enabled: values.is_enabled,
              });
              message.success(`已保存 ${saved.code}，版本 ${saved.config_version}`);
            } catch (error) {
              const text = error instanceof Error ? error.message : '保存失败';
              setFieldError(text);
              message.error(text);
            }
          }}
        >
          <Form.Item name="code" label="配置编码" rules={[{ required: true, message: '请填写配置编码' }]}>
            <Input placeholder="line1-modbus" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请填写名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="device_id" label="IoT 设备编号" rules={[{ required: true, message: '请填写设备编号' }]}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="protocol" label="协议" rules={[{ required: true, message: '请选择协议' }]}>
            <Select options={PROTOCOLS} />
          </Form.Item>
          <Form.Item name="publish_mode" label="publish.mode" rules={[{ required: true, message: '请选择 publish.mode' }]}>
            <Select options={PUBLISH_MODES} />
          </Form.Item>
          <Form.Item name="is_enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="config_json"
            label="config JSON"
            rules={[{ required: true, message: '请填写 config' }]}
            extra="Modbus 需要 host、port、unit_id、registers。OPC UA 需要 endpoint、nodes。S7 需要 host、rack、slot、db_blocks。"
          >
            <Input.TextArea rows={10} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            保存配置
          </Button>
        </Form>
      </Card>
    </Space>
  );
}
