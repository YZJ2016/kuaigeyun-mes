import React, { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Alert, Button, Form, Input, Spin, Table } from 'antd';
import { apiRequest } from '../../../services/api';

type SharedReport = {
  name?: string;
  code?: string;
  data?: Record<string, unknown>[];
  total?: number;
  summary?: Record<string, number>;
};

const DEFAULT_PAGE_SIZE = 20;

/** detail.reason 后端原因码 → 中文提示 */
const DENIED_REASON_MESSAGES: Record<string, string> = {
  password_required: '请输入访问口令',
  password_mismatch: '访问口令错误，请重试',
  expired: '分享链接已过期',
  ip_denied: '当前 IP 不在允许访问名单内',
  missing: '分享链接无效或已关闭',
};

function deniedReason(error: unknown): { reason: string; message: string } {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const reason = (detail as { reason?: unknown }).reason;
    const message = (detail as { message?: unknown }).message;
    if (typeof reason === 'string' && reason) {
      return {
        reason,
        message:
          DENIED_REASON_MESSAGES[reason] ??
          (typeof message === 'string' && message ? message : '分享打不开'),
      };
    }
    if (typeof message === 'string' && message) return { reason: '', message };
  }
  if (typeof detail === 'string' && detail) return { reason: '', message: detail };
  const fallback = (error as Error)?.message;
  return { reason: '', message: fallback || '分享打不开' };
}

export default function ReportSharedView() {
  const [search] = useSearchParams();
  const token = search.get('token') || '';
  const [report, setReport] = useState<SharedReport | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [needsPassword, setNeedsPassword] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const openReport = useCallback(
    async (sharePassword: string | undefined, limit: number, offset: number) => {
      setLoading(true);
      setError('');
      try {
        const params = new URLSearchParams({ token });
        params.set('limit', String(limit));
        params.set('offset', String(offset));
        const body = await apiRequest<SharedReport>(
          `/apps/kuaireport/reports/shared?${params.toString()}`,
          {
            method: 'GET',
            headers: sharePassword ? { 'X-Share-Password': sharePassword } : {},
          },
        );
        setReport(body);
      } catch (err) {
        setReport(null);
        const denied = deniedReason(err);
        setError(denied.message);
        setNeedsPassword(
          denied.reason === 'password_required' || denied.reason === 'password_mismatch',
        );
      } finally {
        setLoading(false);
      }
    },
    [token],
  );

  // 挂载时不带口令先探一次：8h 解锁 cookie 有效时后端直接放行
  useEffect(() => {
    if (token) void openReport(undefined, DEFAULT_PAGE_SIZE, 0);
  }, [token, openReport]);

  if (!token) return <Alert type="error" message="缺少分享参数" />;

  if (!report) {
    if (needsPassword) {
      return (
        <Form
          layout="vertical"
          style={{ maxWidth: 360, margin: '15vh auto' }}
          onFinish={(values: { password?: string }) => {
            setPage(1);
            void openReport(values.password || '', pageSize, 0);
          }}
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
    return loading ? (
      <Spin style={{ display: 'block', margin: '20vh auto' }} />
    ) : (
      <Alert type="error" message={error || '分享打不开'} />
    );
  }

  const rows = report.data || [];
  const columns = Object.keys(rows[0] || {}).map((key) => ({ title: key, dataIndex: key }));
  const summaryEntries = Object.entries(report.summary || {});
  return (
    <div style={{ padding: 24 }}>
      <h1>{report.name}</h1>
      {summaryEntries.length ? (
        <p>合计：{summaryEntries.map(([k, v]) => `${k} ${v}`).join('；')}</p>
      ) : null}
      <Table
        size="small"
        loading={loading}
        rowKey={(_, index) => String(index)}
        dataSource={rows}
        columns={columns}
        pagination={{
          current: page,
          pageSize,
          total: report.total ?? rows.length,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 行`,
        }}
        onChange={(pagination) => {
          const nextPage = pagination.current ?? 1;
          const nextSize = pagination.pageSize ?? pageSize;
          setPage(nextPage);
          setPageSize(nextSize);
          void openReport(undefined, nextSize, (nextPage - 1) * nextSize);
        }}
      />
    </div>
  );
}
