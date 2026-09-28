import React, { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Alert, Spin } from 'antd';
import { apiRequest } from '../../../../services/api';
import { DashboardWidgets, type DashboardWidget } from './DashboardWidgets';

/**
 * 已登录预览。只请求 `/dashboards/{id}/preview`，不请求分享路径。
 */
export default function DashboardPreviewPage() {
  const params = useParams();
  const [search] = useSearchParams();
  const dashboardId = params.id || search.get('id') || '';
  const [widgets, setWidgets] = useState<DashboardWidget[]>([]);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!dashboardId) return;
    let cancelled = false;
    setLoading(true);
    apiRequest<{ name?: string; widgets_config?: DashboardWidget[] }>(
      `/apps/kuaireport/dashboards/${dashboardId}/preview`,
      { method: 'GET' },
    )
      .then((body) => {
        if (cancelled) return;
        setName(body.name || '');
        setWidgets(body.widgets_config || []);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || '预览失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dashboardId]);

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
