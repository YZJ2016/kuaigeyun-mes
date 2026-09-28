import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Alert, Button, Form, Input, Spin } from 'antd';
import { apiRequest } from '../../../services/api';
import { DashboardWidgets, type DashboardWidget } from './dashboards/DashboardWidgets';

type SharedDashboard = {
  name?: string;
  widgets_config?: DashboardWidget[];
};

function deniedReason(error: unknown): string {
  const data = (error as { response?: { data?: { detail?: { reason?: string } } } })?.response?.data;
  return data?.detail?.reason || (error as Error)?.message || '分享打不开';
}

export default function DashboardSharedView() {
  const [search] = useSearchParams();
  const token = search.get('token') || '';
  const [password, setPassword] = useState('');
  const [board, setBoard] = useState<SharedDashboard | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const openBoard = async (nextPassword: string) => {
    setLoading(true);
    setError('');
    try {
      const body = await apiRequest<SharedDashboard>(
        `/apps/kuaireport/dashboards/shared?token=${encodeURIComponent(token)}`,
        {
          method: 'GET',
          headers: nextPassword ? { 'X-Share-Password': nextPassword } : {},
        },
      );
      setBoard(body);
      setPassword(nextPassword);
    } catch (err) {
      setBoard(null);
      setError(deniedReason(err));
    } finally {
      setLoading(false);
    }
  };

  if (!token) return <Alert type="error" message="缺少分享参数" />;

  return (
    <div style={{ minHeight: '100vh', padding: 24, background: '#001529' }}>
      {!board ? (
        <Form
          layout="vertical"
          style={{ maxWidth: 360, margin: '15vh auto', background: '#fff', padding: 24 }}
          onFinish={(values: { password?: string }) => void openBoard(values.password || '')}
        >
          <Form.Item name="password" label="访问口令" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          {error ? <Alert type="error" message={error} style={{ marginBottom: 12 }} /> : null}
          <Button type="primary" htmlType="submit" loading={loading} block>
            打开大屏
          </Button>
        </Form>
      ) : loading ? (
        <Spin />
      ) : (
        <>
          <h1 style={{ color: '#fff' }}>{board.name}</h1>
          <DashboardWidgets widgets={board.widgets_config || []} shareToken={token} />
        </>
      )}
    </div>
  );
}
