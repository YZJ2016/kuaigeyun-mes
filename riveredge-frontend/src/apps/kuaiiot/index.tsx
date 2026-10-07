/**
 * 星数采 APP 入口。
 * 路由约定与 pluginLoader 一致：默认导出应用组件，挂在 /apps/kuaiiot 下。
 */

import React, { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import PageSkeleton from '../../components/page-skeleton';

const DashboardPage = lazy(() => import('./pages/dashboard'));
const ConnectionsPage = lazy(() => import('./pages/connections'));
const DevicesPage = lazy(() => import('./pages/devices'));
const TagsPage = lazy(() => import('./pages/tags'));
const EdgeConfigsPage = lazy(() => import('./pages/edge-configs'));
const AlertsPage = lazy(() => import('./pages/alerts'));
const TemplatesPage = lazy(() => import('./pages/templates'));
const ProductsPage = lazy(() => import('./pages/products'));
const TrendPage = lazy(() => import('./pages/trend'));
const GroupsPage = lazy(() => import('./pages/groups'));
const CommandsPage = lazy(() => import('./pages/commands'));
const MessagesPage = lazy(() => import('./pages/messages'));
const PipelinePage = lazy(() => import('./pages/pipeline'));

const KuaiiotApp: React.FC = () => {
  return (
    <Routes>
      <Route index element={<Navigate to="dashboard" replace />} />
      <Route
        path="dashboard"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <DashboardPage />
          </Suspense>
        }
      />
      <Route
        path="pipeline"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <PipelinePage />
          </Suspense>
        }
      />
      <Route
        path="connections"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <ConnectionsPage />
          </Suspense>
        }
      />
      <Route
        path="devices"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <DevicesPage />
          </Suspense>
        }
      />
      <Route
        path="tags"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <TagsPage />
          </Suspense>
        }
      />
      <Route
        path="alerts"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <AlertsPage />
          </Suspense>
        }
      />
      <Route
        path="templates"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <TemplatesPage />
          </Suspense>
        }
      />
      <Route
        path="edge-configs"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <EdgeConfigsPage />
          </Suspense>
        }
      />
      <Route path="edge" element={<Navigate to="edge-configs" replace />} />
      <Route
        path="products"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <ProductsPage />
          </Suspense>
        }
      />
      <Route
        path="trend"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <TrendPage />
          </Suspense>
        }
      />
      <Route
        path="groups"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <GroupsPage />
          </Suspense>
        }
      />
      <Route
        path="commands"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <CommandsPage />
          </Suspense>
        }
      />
      <Route
        path="messages"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <MessagesPage />
          </Suspense>
        }
      />
      <Route path="*" element={<Navigate to="." replace />} />
    </Routes>
  );
};

export default KuaiiotApp;
