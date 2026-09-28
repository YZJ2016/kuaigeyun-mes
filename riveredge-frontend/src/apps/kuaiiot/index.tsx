/**
 * 星数采 APP 入口。
 * 路由约定与 pluginLoader 一致：默认导出应用组件，挂在 /apps/kuaiiot 下。
 */

import React, { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import PageSkeleton from '../../components/page-skeleton';

const RegistryPage = lazy(() => import('./pages/registry'));
const AlertsPage = lazy(() => import('./pages/alerts'));
const TemplatesPage = lazy(() => import('./pages/templates'));
const EdgePage = lazy(() => import('./pages/edge'));
const ProductsPage = lazy(() => import('./pages/products'));
const TrendPage = lazy(() => import('./pages/trend'));
const GroupsPage = lazy(() => import('./pages/groups'));
const CommandsPage = lazy(() => import('./pages/commands'));
const MessagesPage = lazy(() => import('./pages/messages'));

const KuaiiotApp: React.FC = () => {
  return (
    <Routes>
      <Route
        index
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <RegistryPage />
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
        path="edge"
        element={
          <Suspense fallback={<PageSkeleton variant="content" />}>
            <EdgePage />
          </Suspense>
        }
      />
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
