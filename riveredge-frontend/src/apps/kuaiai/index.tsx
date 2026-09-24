/**
 * 星AI APP 入口文件
 *
 * 路由约定（与 pages/ 一一对应）：
 * - 文件: pages/{path}/index.tsx
 * - Route path: {path}
 * - 完整 URL: /apps/kuaiai/{path}
 */

import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import PageSkeleton from '../../components/page-skeleton';

const withPageSuspense = (LazyComponent: React.LazyExoticComponent<React.ComponentType<any>>) => (
  <Suspense fallback={<PageSkeleton variant="content" />}>
    <LazyComponent />
  </Suspense>
);

const ChatPage = lazy(() => import('./pages/chat'));
const AgentsPage = lazy(() => import('./pages/agents'));
const KnowledgePage = lazy(() => import('./pages/knowledge'));
const ModelsPage = lazy(() => import('./pages/models'));
const McpPage = lazy(() => import('./pages/mcp'));

const KuaiaiApp: React.FC = () => {
  return (
    <Routes>
      <Route index element={<Navigate to="chat" replace />} />
      <Route path="chat" element={withPageSuspense(ChatPage)} />
      <Route path="agents" element={withPageSuspense(AgentsPage)} />
      <Route path="knowledge" element={withPageSuspense(KnowledgePage)} />
      <Route path="models" element={withPageSuspense(ModelsPage)} />
      <Route path="mcp" element={withPageSuspense(McpPage)} />
      <Route path="*" element={<Navigate to="chat" replace />} />
    </Routes>
  );
};

export default KuaiaiApp;
