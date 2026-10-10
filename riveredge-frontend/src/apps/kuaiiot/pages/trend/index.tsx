/**
 * 数值点位趋势。租户未启用 kuaiiot_tsdb 时显示不可用，不把空表当成历史。
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Card, Form, Input, Space, Table, Typography, message } from 'antd';
import { queryTrend, type TrendPoint } from '../../services/registry';

const { Title } = Typography;

function defaultRange(): { start: string; stop: string } {
  const stop = new Date();
  const start = new Date(stop.getTime() - 60 * 60 * 1000);
  return { start: start.toISOString(), stop: stop.toISOString() };
}

export default function TrendPage() {
  const [range] = useState(defaultRange);
  const [unavailable, setUnavailable] = useState(false);
  const [points, setPoints] = useState<TrendPoint[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    queryTrend({ device_id: 0, tag_key: 'temp', start: range.start, stop: range.stop })
      .then(() => {
        if (!cancelled) setUnavailable(false);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const text = error instanceof Error ? error.message : '';
        setUnavailable(text.includes('趋势不可用'));
      });
    return () => {
      cancelled = true;
    };
  }, [range.start, range.stop]);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: 16 }}>
      <Space>
        <Title level={4} style={{ margin: 0 }}>
          点位趋势
        </Title>
        <Link to="/apps/kuaiiot/products">产品</Link>
      </Space>
      {unavailable ? (
        <Alert type="warning" showIcon message="趋势不可用" description="当前租户没有启用的 kuaiiot_tsdb 集成。" />
      ) : (
        <Card title="查询">
          <Form
            layout="inline"
            initialValues={{ tag_key: 'temp', start: range.start, stop: range.stop }}
            onFinish={async (values: { device_id: string; tag_key: string; start: string; stop: string }) => {
              setPoints(null);
              try {
                const rows = await queryTrend({
                  device_id: Number(values.device_id),
                  tag_key: values.tag_key,
                  start: new Date(values.start).toISOString(),
                  stop: new Date(values.stop).toISOString(),
                });
                setUnavailable(false);
                setPoints(Array.isArray(rows) ? rows : []);
              } catch (error) {
                const text = error instanceof Error ? error.message : '查询趋势失败';
                setPoints(null);
                if (text.includes('趋势不可用')) {
                  setUnavailable(true);
                  return;
                }
                message.error(text);
              }
            }}
          >
            <Form.Item name="device_id" rules={[{ required: true, message: '请填写设备编号' }]}>
              <Input placeholder="设备编号" />
            </Form.Item>
            <Form.Item name="tag_key" rules={[{ required: true, message: '请填写点位键' }]}>
              <Input placeholder="点位键" />
            </Form.Item>
            <Form.Item name="start" rules={[{ required: true }]}>
              <Input placeholder="开始时间" />
            </Form.Item>
            <Form.Item name="stop" rules={[{ required: true }]}>
              <Input placeholder="结束时间" />
            </Form.Item>
            <Button type="primary" htmlType="submit">
              查询趋势
            </Button>
          </Form>
          {points ? (
            <Table
              style={{ marginTop: 16 }}
              rowKey={(row) => `${row.time}-${row.value}`}
              pagination={false}
              dataSource={points}
              locale={{ emptyText: '这段时间没有数值' }}
              columns={[
                { title: '时间', dataIndex: 'time' },
                { title: '数值', dataIndex: 'value' },
              ]}
            />
          ) : null}
        </Card>
      )}
    </Space>
  );
}
