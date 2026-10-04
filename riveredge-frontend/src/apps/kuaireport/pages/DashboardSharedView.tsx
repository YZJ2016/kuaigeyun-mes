import React, { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Alert, Button, Form, Input, Spin } from 'antd';
import { apiRequest } from '../../../services/api';
import { DashboardWidgets, type DashboardWidget } from './dashboards/DashboardWidgets';
import { DashboardCanvasFrame, isCanvasLayout, isFlowLayout, parseTheme } from './dashboards/dashboardStage';

type SharedDashboard = {
  name?: string;
  widgets_config?: DashboardWidget[];
  layout_config?: unknown;
  theme_config?: unknown;
};

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

export default function DashboardSharedView() {
  const [search] = useSearchParams();
  const token = search.get('token') || '';
  const [board, setBoard] = useState<SharedDashboard | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [needsPassword, setNeedsPassword] = useState(false);

  const openBoard = useCallback(
    async (sharePassword?: string) => {
      setLoading(true);
      setError('');
      try {
        const body = await apiRequest<SharedDashboard>(
          `/apps/kuaireport/dashboards/shared?token=${encodeURIComponent(token)}`,
          {
            method: 'GET',
            headers: sharePassword ? { 'X-Share-Password': sharePassword } : {},
          },
        );
        setBoard(body);
      } catch (err) {
        setBoard(null);
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
    if (token) void openBoard();
  }, [token, openBoard]);

  if (!token) return <Alert type="error" message="缺少分享参数" />;

  return (
    <div style={{ minHeight: '100vh', padding: 24, background: '#001529' }}>
      {board ? (
        isCanvasLayout(board.layout_config) ? (
          <DashboardCanvasFrame
            theme={parseTheme(board.theme_config)}
            widgets={board.widgets_config || []}
            shareToken={token}
            flow={isFlowLayout(board.layout_config)}
          />
        ) : (
          <>
            <h1 style={{ color: '#fff' }}>{board.name}</h1>
            <DashboardWidgets widgets={board.widgets_config || []} shareToken={token} />
          </>
        )
      ) : needsPassword ? (
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
        <Alert type="error" message={error || '分享打不开'} />
      )}
    </div>
  );
}
