/**
 * 星数采应用路由
 */

import React, { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import PageSkeleton from '../../components/page-skeleton';

const DashboardPage = lazy(() => import('./pages/dashboard'));
const ConnectionsPage = lazy(() => import('./pages/connections'));
const ProductsPage = lazy(() => import('./pages/products'));
const DevicesPage = lazy(() => import('./pages/devices'));
const TagsPage = lazy(() => import('./pages/tags'));
const AlertsPage = lazy(() => import('./pages/alerts'));
const EdgeConfigsPage = lazy(() => import('./pages/edge-configs'));
const PipelinePage = lazy(() => import('./pages/pipeline'));
const TemplatesPage = lazy(() => import('./pages/templates'));
const TrendPage = lazy(() => import('./pages/trend'));
const GroupsPage = lazy(() => import('./pages/groups'));
const CommandsPage = lazy(() => import('./pages/commands'));
const MessagesPage = lazy(() => import('./pages/messages'));

const withPageSuspense = (LazyComponent: React.LazyExoticComponent<React.ComponentType>) => (
  <Suspense fallback={<PageSkeleton variant="content" />}>
    <LazyComponent />
  </Suspense>
);

const KuaiiotApp: React.FC = () => (
  <Routes>
    <Route path="/" element={<Navigate to="dashboard" replace />} />
    <Route path="dashboard" element={withPageSuspense(DashboardPage)} />
    <Route path="connections" element={withPageSuspense(ConnectionsPage)} />
    <Route path="products" element={withPageSuspense(ProductsPage)} />
    <Route path="devices" element={withPageSuspense(DevicesPage)} />
    <Route path="tags" element={withPageSuspense(TagsPage)} />
    <Route path="alerts" element={withPageSuspense(AlertsPage)} />
    <Route path="edge-configs" element={withPageSuspense(EdgeConfigsPage)} />
    <Route path="pipeline" element={withPageSuspense(PipelinePage)} />
    <Route path="templates" element={withPageSuspense(TemplatesPage)} />
    <Route path="trend" element={withPageSuspense(TrendPage)} />
    <Route path="groups" element={withPageSuspense(GroupsPage)} />
    <Route path="commands" element={withPageSuspense(CommandsPage)} />
    <Route path="messages" element={withPageSuspense(MessagesPage)} />
    <Route path="*" element={<Navigate to="dashboard" replace />} />
  </Routes>
);

export default KuaiiotApp;
