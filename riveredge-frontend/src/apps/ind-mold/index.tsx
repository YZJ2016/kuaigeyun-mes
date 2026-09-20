/**
 * 模具机加行业插件入口
 */
import React, { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import PageSkeleton from '../../components/page-skeleton';

const ProgramSheetsPage = lazy(() => import('./pages/program-sheets'));
const MaterialArrivalsPage = lazy(() => import('./pages/material-arrivals'));

const withPageSuspense = (LazyComponent: React.LazyExoticComponent<React.ComponentType<object>>) => (
  <Suspense fallback={<PageSkeleton />}>
    <LazyComponent />
  </Suspense>
);

export default function IndustryMoldApp() {
  return (
    <Routes>
      <Route index element={<Navigate to="program-sheets" replace />} />
      <Route path="program-sheets" element={withPageSuspense(ProgramSheetsPage)} />
      <Route path="material-arrivals" element={withPageSuspense(MaterialArrivalsPage)} />
      <Route path="*" element={<Navigate to="program-sheets" replace />} />
    </Routes>
  );
}
