/**
 * 星报表 APP 入口文件
 *
 * 路由约定与 pluginLoader 一致：默认导出应用组件，挂在 /apps/kuaireport 下。
 */

import React, { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import PageSkeleton from '../../components/page-skeleton';

const withPageSuspense = (LazyComponent: React.LazyExoticComponent<React.ComponentType<any>>) => (
  <Suspense fallback={<PageSkeleton variant="content" />}>
    <LazyComponent />
  </Suspense>
);

const ReportCenterPage = lazy(() => import('./pages/reports'));
const ReportPreviewPage = lazy(() => import('./pages/reports/preview'));
const ReportDesignerPage = lazy(() => import('./pages/designer'));
const DashboardDesignPage = lazy(() => import('./pages/dashboards/DashboardDesignPage'));
const DashboardPreviewPage = lazy(() => import('./pages/dashboards/DashboardPreviewPage'));
const DistributionPage = lazy(() => import('./pages/distribution'));

const KuaireportApp: React.FC = () => {
  return (
    <Routes>
      <Route index element={<Navigate to="reports" replace />} />
      <Route path="reports" element={withPageSuspense(ReportCenterPage)} />
      <Route path="reports/view/:reportId" element={withPageSuspense(ReportPreviewPage)} />
      <Route path="designer" element={withPageSuspense(ReportDesignerPage)} />
      <Route path="dashboards/design" element={withPageSuspense(DashboardDesignPage)} />
      <Route path="dashboards/:id/preview" element={withPageSuspense(DashboardPreviewPage)} />
      <Route path="distribution" element={withPageSuspense(DistributionPage)} />
      <Route path="*" element={<Navigate to="reports" replace />} />
    </Routes>
  );
};

export default KuaireportApp;
