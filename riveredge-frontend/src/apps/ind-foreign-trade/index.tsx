/**
 * 外贸销售行业插件入口
 */
import React, { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import PageSkeleton from '../../components/page-skeleton';

const DashboardPage = lazy(() => import('./pages/dashboard'));
const ExportCustomersPage = lazy(() => import('./pages/export-customers'));
const InquiryImportPage = lazy(() => import('./pages/inquiry-import'));
const FollowUpsPage = lazy(() => import('./pages/follow-ups'));

const withPageSuspense = (LazyComponent: React.LazyExoticComponent<React.ComponentType<object>>) => (
  <Suspense fallback={<PageSkeleton />}>
    <LazyComponent />
  </Suspense>
);

export default function IndustryForeignTradeApp() {
  return (
    <Routes>
      <Route index element={<Navigate to="dashboard" replace />} />
      <Route path="dashboard" element={withPageSuspense(DashboardPage)} />
      <Route path="export-customers" element={withPageSuspense(ExportCustomersPage)} />
      <Route path="inquiry-import" element={withPageSuspense(InquiryImportPage)} />
      <Route path="follow-ups" element={withPageSuspense(FollowUpsPage)} />
      <Route path="*" element={<Navigate to="dashboard" replace />} />
    </Routes>
  );
}
