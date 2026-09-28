/**
 * 维护产品物模型，并按产品批量创建 IoT 设备。
 * 创建当次展示设备凭据，之后不再从列表回显。
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Typography, message } from 'antd';
import {
  batchCreateDevices,
  createProduct,
  listProducts,
  updateProduct,
  type BatchDeviceOut,
  type ProductEvent,
  type ProductFunction,
  type ProductOut,
  type ProductTag,
} from '../../services/kuaiiot';

const { Title, Text } = Typography;

const MAP_TARGETS = ['temperature', 'pressure', 'vibration', 'status', 'is_online'].map((value) => ({
  value,
  label: value,
}));

const DATA_TYPES = ['int16', 'uint16', 'int32', 'uint32', 'float32', 'bool'].map((value) => ({
  value,
  label: value,
}));

const BUILTIN_EVENTS: ProductEvent[] = [
  { event_key: 'fault', name: '故障', severity: 'critical', message: '设备故障' },
  { event_key: 'mold_change', name: '换模', severity: 'info', message: '换模' },
];

export default function ProductsPage() {
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [created, setCreated] = useState<BatchDeviceOut[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [events, setEvents] = useState<ProductEvent[]>([]);
  const [functions, setFunctions] = useState<ProductFunction[]>([]);

  const load = async () => {
    const rows = await listProducts();
    setProducts(Array.isArray(rows) ? rows : []);
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space>
        <Title level={4} style={{ margin: 0 }}>
          产品物模型
        </Title>
        <Link to="/apps/kuaiiot">返回登记</Link>
        <Link to="/apps/kuaiiot/trend">趋势</Link>
      </Space>
      <Text type="secondary">点位写在产品 tags 上。按产品一批最多 100 台 IoT 设备，不新建设备台账。</Text>

      <Card title="产品">
        <Form
          layout="inline"
          initialValues={{ value_type: 'number', map_target: 'temperature' }}
          onFinish={async (values: {
            code: string;
            name: string;
            tag_key: string;
            tag_name: string;
            value_type: string;
            map_target: string;
          }) => {
            const tag: ProductTag = {
              tag_key: values.tag_key,
              name: values.tag_name,
              value_type: values.value_type,
              map_target: values.map_target,
            };
            try {
              await createProduct({ code: values.code, name: values.name, tags: [tag] });
              message.success('产品已保存');
              await load();
            } catch (error) {
              message.error(error instanceof Error ? error.message : '保存产品失败');
            }
          }}
        >
          <Form.Item name="code" rules={[{ required: true, message: '请填写编码' }]}>
            <Input placeholder="产品编码" />
          </Form.Item>
          <Form.Item name="name" rules={[{ required: true, message: '请填写名称' }]}>
            <Input placeholder="产品名称" />
          </Form.Item>
          <Form.Item name="tag_key" rules={[{ required: true, message: '请填写点位键' }]}>
            <Input placeholder="点位键" />
          </Form.Item>
          <Form.Item name="tag_name" rules={[{ required: true, message: '请填写点位名称' }]}>
            <Input placeholder="点位名称" />
          </Form.Item>
          <Form.Item name="value_type">
            <Select
              style={{ width: 120 }}
              options={[
                { value: 'number', label: 'number' },
                { value: 'boolean', label: 'boolean' },
                { value: 'text', label: 'text' },
              ]}
            />
          </Form.Item>
          <Form.Item name="map_target">
            <Select style={{ width: 160 }} options={MAP_TARGETS} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            保存产品
          </Button>
          <Button onClick={() => load().catch((error) => message.error(error instanceof Error ? error.message : '读取失败'))}>
            刷新
          </Button>
        </Form>
        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          pagination={false}
          dataSource={products}
          columns={[
            { title: '编码', dataIndex: 'code' },
            { title: '名称', dataIndex: 'name' },
            {
              title: '点位',
              dataIndex: 'tags',
              render: (tags: ProductTag[]) => (tags || []).map((tag) => tag.tag_key).join(', '),
            },
            {
              title: '事件',
              dataIndex: 'events',
              render: (rows: ProductEvent[]) => (rows || []).map((item) => item.event_key).join(', '),
            },
            {
              title: '指令',
              dataIndex: 'functions',
              render: (rows: ProductFunction[]) => (rows || []).map((item) => item.function_key).join(', '),
            },
          ]}
        />
      </Card>

      <Card title="事件与指令">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Button
              onClick={() =>
                load().catch((error) => message.error(error instanceof Error ? error.message : '读取失败'))
              }
            >
              刷新产品
            </Button>
            {BUILTIN_EVENTS.map((preset) => (
              <Button
                key={preset.event_key}
                onClick={() =>
                  setEvents((current) =>
                    current.some((item) => item.event_key === preset.event_key) ? current : [...current, preset],
                  )
                }
              >
                加入{preset.name}
              </Button>
            ))}
          </Space>
          <Form
            layout="inline"
            onFinish={(values: { product_id: number }) => {
              const product = products.find((item) => item.id === values.product_id);
              if (!product) {
                message.error('请先刷新并选择已有产品');
                return;
              }
              setEditingId(product.id);
              setEvents(product.events || []);
              setFunctions(product.functions || []);
            }}
          >
            <Form.Item name="product_id" rules={[{ required: true, message: '请填写产品编号' }]}>
              <InputNumber placeholder="产品编号" min={1} />
            </Form.Item>
            <Button htmlType="submit">载入</Button>
          </Form>
          <Form
            layout="inline"
            onFinish={(values: { event_key: string; name: string; severity: string }) => {
              setEvents((current) => {
                if (current.some((item) => item.event_key === values.event_key)) {
                  return current;
                }
                return [...current, values];
              });
            }}
          >
            <Form.Item name="event_key" rules={[{ required: true, message: '请填写事件键' }]}>
              <Input placeholder="事件键" />
            </Form.Item>
            <Form.Item name="name" rules={[{ required: true, message: '请填写事件名称' }]}>
              <Input placeholder="事件名称" />
            </Form.Item>
            <Form.Item name="severity" initialValue="warning">
              <Select
                style={{ width: 120 }}
                options={[
                  { value: 'info', label: 'info' },
                  { value: 'warning', label: 'warning' },
                  { value: 'critical', label: 'critical' },
                ]}
              />
            </Form.Item>
            <Button htmlType="submit">添加事件</Button>
          </Form>
          <Form
            layout="inline"
            initialValues={{ data_type: 'uint16', param_key: 'value', scale: 1, timeout_seconds: 30 }}
            onFinish={(values: {
              function_key: string;
              name: string;
              address: number;
              data_type: string;
              param_key: string;
              scale: number;
              timeout_seconds: number;
            }) => {
              const next: ProductFunction = {
                function_key: values.function_key,
                name: values.name,
                timeout_seconds: values.timeout_seconds,
                params: [{ key: values.param_key, name: values.param_key, value_type: 'number', required: true }],
                edge_action: {
                  type: 'modbus_write',
                  param_key: values.param_key,
                  address: values.address,
                  data_type: values.data_type,
                  scale: values.scale,
                },
              };
              setFunctions((current) => {
                if (current.some((item) => item.function_key === next.function_key)) {
                  return current.map((item) => (item.function_key === next.function_key ? next : item));
                }
                return [...current, next];
              });
            }}
          >
            <Form.Item name="function_key" rules={[{ required: true, message: '请填写指令键' }]}>
              <Input placeholder="指令键" />
            </Form.Item>
            <Form.Item name="name" rules={[{ required: true, message: '请填写指令名称' }]}>
              <Input placeholder="指令名称" />
            </Form.Item>
            <Form.Item name="address" rules={[{ required: true, message: '请填写寄存器地址' }]}>
              <InputNumber placeholder="地址" min={0} />
            </Form.Item>
            <Form.Item name="data_type">
              <Select style={{ width: 120 }} options={DATA_TYPES} />
            </Form.Item>
            <Form.Item name="param_key">
              <Input placeholder="参数键" />
            </Form.Item>
            <Form.Item name="scale">
              <InputNumber placeholder="scale" />
            </Form.Item>
            <Form.Item name="timeout_seconds">
              <InputNumber placeholder="超时秒" min={1} />
            </Form.Item>
            <Button htmlType="submit">添加指令</Button>
          </Form>
          <Text>
            当前产品 {editingId ?? '未载入'}。事件：{events.map((item) => item.event_key).join(', ') || '无'}。指令：
            {functions.map((item) => item.function_key).join(', ') || '无'}
          </Text>
          <Button
            type="primary"
            disabled={editingId == null}
            onClick={() => {
              if (editingId == null) {
                return;
              }
              updateProduct(editingId, { events, functions })
                .then(async () => {
                  message.success('事件与指令已保存');
                  await load();
                })
                .catch((error) => message.error(error instanceof Error ? error.message : '保存失败'));
            }}
          >
            保存事件与指令
          </Button>
        </Space>
      </Card>

      <Card title="按产品批量建设备">
        <Form
          layout="inline"
          onFinish={async (values: { product_id: number; name_prefix: string; code_prefix: string; count: number }) => {
            try {
              const rows = await batchCreateDevices(values);
              setCreated(rows);
              message.success(`已创建 ${rows.length} 台。凭据只在本次显示`);
            } catch (error) {
              setCreated([]);
              message.error(error instanceof Error ? error.message : '批量创建失败');
            }
          }}
        >
          <Form.Item name="product_id" rules={[{ required: true, message: '请填写产品编号' }]}>
            <InputNumber placeholder="产品编号" min={1} />
          </Form.Item>
          <Form.Item name="name_prefix" rules={[{ required: true, message: '请填写名称前缀' }]}>
            <Input placeholder="名称前缀" />
          </Form.Item>
          <Form.Item name="code_prefix" rules={[{ required: true, message: '请填写编码前缀' }]}>
            <Input placeholder="编码前缀" />
          </Form.Item>
          <Form.Item name="count" rules={[{ required: true, message: '请填写数量' }]}>
            <InputNumber placeholder="数量" min={1} max={100} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            批量创建
          </Button>
        </Form>
        {created.length > 0 ? (
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message="设备凭据只在这次创建结果里出现，离开后不再显示。"
          />
        ) : null}
        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          pagination={false}
          dataSource={created}
          columns={[
            { title: '编码', dataIndex: 'code' },
            { title: '名称', dataIndex: 'name' },
            { title: '凭据', dataIndex: 'device_token' },
          ]}
        />
      </Card>
    </Space>
  );
}
