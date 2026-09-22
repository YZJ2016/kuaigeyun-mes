import React from 'react';
import { Navigate } from 'react-router-dom';
import PageSkeleton from '../page-skeleton';
import { TENANT_HOME_FALLBACK } from '../../stores/configStore';
import { useTenantEffectiveHomePath } from '../../hooks/useTenantEffectiveHomePath';

/**
 * /system/default-home 路由门控：仅当有效首页确为兜底页时才渲染内容。
 * 已配置角色/菜单首页时一次性 replace，不先展示「未配置首页」卡片。
 */
export const DefaultHomeRouteGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { path, ready } = useTenantEffectiveHomePath();

  if (!ready) {
    return <PageSkeleton variant="content" />;
  }

  if (path !== TENANT_HOME_FALLBACK) {
    return <Navigate to={path} replace />;
  }

  return <>{children}</>;
};

export default DefaultHomeRouteGate;
