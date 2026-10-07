/**
 * 维护 IoT 设备分组，并把设备指到本租户分组。
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Card, Form, Input, InputNumber, Space, Table, Typography, message } from 'antd';
import {
  assignDeviceGroup,
  createDeviceGroup,
  listDeviceGroups,
  listDevices,
  type DeviceGroup,
  type DeviceOut,
} from '../../services/kuaiiot';

const { Title, Text } = Typography;

export default function GroupsPage() {
  const [groups, setGroups] = useState<DeviceGroup[]>([]);
  const [devices, setDevices] = useState<DeviceOut[]>([]);

  const load = async () => {
    const [groupRows, deviceRows] = await Promise.all([listDeviceGroups(), listDevices()]);
    setGroups(Array.isArray(groupRows) ? groupRows : []);
    setDevices(Array.isArray(deviceRows) ? deviceRows : []);
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space>
        <Title level={4} style={{ margin: 0 }}>
          设备分组
        </Title>
        <Link to="/apps/kuaiiot/dashboard">返回数采中心</Link>
      </Space>
      <Text type="secondary">分组只挂在 IoT 设备上，不改星制造设备台账。</Text>
      <Card title="新建">
        <Form
          layout="inline"
          onFinish={async (values: { code: string; name: string; parent_id?: number; sort_order?: number }) => {
            try {
              await createDeviceGroup(values);
              message.success('分组已保存');
              await load();
            } catch (error) {
              message.error(error instanceof Error ? error.message : '保存分组失败');
            }
          }}
        >
          <Form.Item name="code" rules={[{ required: true, message: '请填写编码' }]}>
            <Input placeholder="分组编码" />
          </Form.Item>
          <Form.Item name="name" rules={[{ required: true, message: '请填写名称' }]}>
            <Input placeholder="分组名称" />
          </Form.Item>
          <Form.Item name="parent_id">
            <InputNumber placeholder="上级编号" min={1} />
          </Form.Item>
          <Form.Item name="sort_order">
            <InputNumber placeholder="排序" />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            保存
          </Button>
          <Button onClick={() => load().catch((error) => message.error(error instanceof Error ? error.message : '读取失败'))}>
            刷新
          </Button>
        </Form>
        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          pagination={false}
          dataSource={groups}
          columns={[
            { title: '编号', dataIndex: 'id' },
            { title: '编码', dataIndex: 'code' },
            { title: '名称', dataIndex: 'name' },
            { title: '上级', dataIndex: 'parent_id' },
            { title: '排序', dataIndex: 'sort_order' },
          ]}
        />
      </Card>
      <Card title="把设备放进分组">
        <Form
          layout="inline"
          onFinish={async (values: { device_id: number; group_id: number }) => {
            try {
              await assignDeviceGroup(values.device_id, values.group_id);
              message.success('设备已归组');
              await load();
            } catch (error) {
              message.error(error instanceof Error ? error.message : '归组失败');
            }
          }}
        >
          <Form.Item name="device_id" rules={[{ required: true, message: '请填写设备编号' }]}>
            <InputNumber placeholder="设备编号" min={1} />
          </Form.Item>
          <Form.Item name="group_id" rules={[{ required: true, message: '请填写分组编号' }]}>
            <InputNumber placeholder="分组编号" min={1} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            归组
          </Button>
        </Form>
        <Table
          style={{ marginTop: 16 }}
          rowKey="id"
          pagination={false}
          dataSource={devices}
          columns={[
            { title: '编号', dataIndex: 'id' },
            { title: '编码', dataIndex: 'code' },
            { title: '名称', dataIndex: 'name' },
            { title: '分组', dataIndex: 'group_id' },
          ]}
        />
      </Card>
    </Space>
  );
}
