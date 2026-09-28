import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Alert, Spin } from 'antd';
import { apiRequest } from '../../../../services/api';
import { DashboardWidgets, type DashboardWidget } from './DashboardWidgets';

const DATA_WIDGET_TYPES = new Set(['metric', 'table', 'chart']);

/**
 * 已登录预览。只请求 `/dashboards/{id}/preview`，不请求分享路径。
 * 数据组件（metric/table/chart）按其 refresh_seconds 的最小值轮询重取；
 * 后端没有单组件刷新端点，轮询整体 preview（会重算各数据组件的 result）。
 */
export default function DashboardPreviewPage() {
  const params = useParams();
  const [search] = useSearchParams();
  const dashboardId = params.id || search.get('id') || '';
  const [widgets, setWidgets] = useState<DashboardWidget[]>([]);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const mountedRef = useRef(true);

  const refreshSeconds = useMemo(() => {
    const seconds = widgets
      .filter((widget) => DATA_WIDGET_TYPES.has(widget.type))
      .map((widget) => widget.refresh_seconds)
      .filter((value): value is number => typeof value === 'number' && value >= 1);
    return seconds.length ? Math.min(...seconds) : 0;
  }, [widgets]);

  const loadPreview = useCallback(
    async (showSpinner: boolean) => {
      if (!dashboardId) return;
      if (showSpinner) setLoading(true);
      try {
        const body = await apiRequest<{ name?: string; widgets_config?: DashboardWidget[] }>(
          `/apps/kuaireport/dashboards/${dashboardId}/preview`,
          { method: 'GET' },
        );
        if (!mountedRef.current) return;
        setName(body.name || '');
        setWidgets(body.widgets_config || []);
        setError('');
      } catch (err) {
        if (mountedRef.current && showSpinner) {
          setError(err instanceof Error ? err.message : '预览失败');
        }
      } finally {
        if (mountedRef.current && showSpinner) setLoading(false);
      }
    },
    [dashboardId],
  );

  useEffect(() => {
    mountedRef.current = true;
    void loadPreview(true);
    return () => {
      mountedRef.current = false;
    };
  }, [loadPreview]);

  useEffect(() => {
    if (!refreshSeconds) return undefined;
    const timer = window.setInterval(() => {
      void loadPreview(false);
    }, refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [loadPreview, refreshSeconds]);

  if (!dashboardId) return <Alert type="info" message="缺少大屏 id" />;
  if (loading) return <Spin />;
  if (error) return <Alert type="error" message={error} />;
  return (
    <div style={{ padding: 16 }}>
      <h1>{name}</h1>
      <DashboardWidgets widgets={widgets} />
    </div>
  );
}
