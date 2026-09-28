import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Alert, Button, Form, Input, Table } from 'antd';
import { apiRequest } from '../../../services/api';

type SharedReport = {
  name?: string;
  code?: string;
  data?: Record<string, unknown>[];
  total?: number;
  summary?: Record<string, number>;
};

function deniedReason(error: unknown): string {
  const data = (error as { response?: { data?: { detail?: { reason?: string } } } })?.response?.data;
  return data?.detail?.reason || (error as Error)?.message || '分享打不开';
}

export default function ReportSharedView() {
  const [search] = useSearchParams();
  const token = search.get('token') || '';
  const [report, setReport] = useState<SharedReport | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const openReport = async (password: string) => {
    setLoading(true);
    setError('');
    try {
      const body = await apiRequest<SharedReport>(
        `/apps/kuaireport/reports/shared?token=${encodeURIComponent(token)}`,
        {
          method: 'GET',
          headers: password ? { 'X-Share-Password': password } : {},
        },
      );
      setReport(body);
    } catch (err) {
      setReport(null);
      setError(deniedReason(err));
    } finally {
      setLoading(false);
    }
  };

  if (!token) return <Alert type="error" message="缺少分享参数" />;

  if (!report) {
    return (
      <Form
        layout="vertical"
        style={{ maxWidth: 360, margin: '15vh auto' }}
        onFinish={(values: { password?: string }) => void openReport(values.password || '')}
      >
        <Form.Item name="password" label="访问口令" rules={[{ required: true }]}>
          <Input.Password />
        </Form.Item>
        {error ? <Alert type="error" message={error} style={{ marginBottom: 12 }} /> : null}
        <Button type="primary" htmlType="submit" loading={loading} block>
          打开账表
        </Button>
      </Form>
    );
  }

  const rows = report.data || [];
  const columns = Object.keys(rows[0] || {}).map((key) => ({ title: key, dataIndex: key }));
  return (
    <div style={{ padding: 24 }}>
      <h1>{report.name}</h1>
      <p>合计 {report.total ?? 0}</p>
      <Table
        size="small"
        pagination={false}
        rowKey={(_, index) => String(index)}
        dataSource={rows}
        columns={columns}
      />
    </div>
  );
}
