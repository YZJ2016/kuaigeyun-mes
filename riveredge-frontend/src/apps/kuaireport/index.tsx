/**
 * 星报表 APP 入口文件
 *
 * 路由约定与 pluginLoader 一致：默认导出应用组件，挂在 /apps/kuaireport 下。
 * 顶部 Menu 给各子页（报表中心/设计器/大屏/分发）提供可达入口。
 */

import React, { Suspense, lazy, useMemo } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Menu } from 'antd';
import PageSkeleton from '../../components/page-skeleton';

const withPageSuspense = (LazyComponent: React.LazyExoticComponent<React.ComponentType<any>>) => (
  <Suspense fallback={<PageSkeleton variant="content" />}>
    <LazyComponent />
  </Suspense>
);

const ReportCenterPage = lazy(() => import('./pages/reports'));
const ReportPreviewPage = lazy(() => import('./pages/reports/preview'));
const ReportDesignerPage = lazy(() => import('./pages/designer'));
const DashboardListPage = lazy(() => import('./pages/dashboards'));
const DashboardDesignPage = lazy(() => import('./pages/dashboards/DashboardDesignPage'));
const DashboardPreviewPage = lazy(() => import('./pages/dashboards/DashboardPreviewPage'));
const DistributionPage = lazy(() => import('./pages/distribution'));

const NAV_ITEMS = [
  { key: 'reports', label: '报表中心' },
  { key: 'designer', label: '设计器' },
  { key: 'dashboards', label: '大屏' },
  { key: 'distribution', label: '分发' },
];

const KuaireportApp: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const selected = useMemo(() => {
    const segment = location.pathname.replace(/^\/apps\/kuaireport\/?/, '').split('/')[0];
    return NAV_ITEMS.some((item) => item.key === segment) ? segment : 'reports';
  }, [location.pathname]);
  return (
    <>
      <Menu
        mode="horizontal"
        selectedKeys={[selected]}
        items={NAV_ITEMS}
        onClick={({ key }) => navigate(`/apps/kuaireport/${key}`)}
      />
      <Routes>
        <Route index element={<Navigate to="reports" replace />} />
        <Route path="reports" element={withPageSuspense(ReportCenterPage)} />
        <Route path="reports/view/:reportId" element={withPageSuspense(ReportPreviewPage)} />
        <Route path="designer" element={withPageSuspense(ReportDesignerPage)} />
        <Route path="dashboards" element={withPageSuspense(DashboardListPage)} />
        <Route path="dashboards/design" element={withPageSuspense(DashboardDesignPage)} />
        <Route path="dashboards/:id/preview" element={withPageSuspense(DashboardPreviewPage)} />
        <Route path="distribution" element={withPageSuspense(DistributionPage)} />
        <Route path="*" element={<Navigate to="reports" replace />} />
      </Routes>
    </>
  );
};

export default KuaireportApp;
