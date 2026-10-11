/**
 * 星AI APP 入口文件
 *
 * 路由约定（与 pages/ 一一对应）：
 * - 文件: pages/{path}/index.tsx
 * - Route path: {path}
 * - 完整 URL: /apps/kuaiai/{path}
 *
 * 双层结构（spec 181）：
 * - 业务运营层：hub / agent-library / pulse / corpus / trust / insights / settings
 * - 治理底座层：chat / agents / knowledge / mcp（既有页面保持不变）
 */

import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import PageSkeleton from '../../components/page-skeleton';

const withPageSuspense = (LazyComponent: React.LazyExoticComponent<React.ComponentType<any>>) => (
  <Suspense fallback={<PageSkeleton variant="content" />}>
    <LazyComponent />
  </Suspense>
);

// 业务运营层
const HubPage = lazy(() => import('./pages/hub'));
const AgentLibraryPage = lazy(() => import('./pages/agent-library'));
const PulsePage = lazy(() => import('./pages/pulse'));
const CorpusPage = lazy(() => import('./pages/corpus'));
const TrustPage = lazy(() => import('./pages/trust'));
const InsightsPage = lazy(() => import('./pages/insights'));
const SettingsPage = lazy(() => import('./pages/settings'));

// 治理底座层（既有）
const ChatPage = lazy(() => import('./pages/chat'));
const AgentsPage = lazy(() => import('./pages/agents'));
const KnowledgePage = lazy(() => import('./pages/knowledge'));
const McpPage = lazy(() => import('./pages/mcp'));

const KuaiaiApp: React.FC = () => {
  return (
    <Routes>
      <Route index element={<Navigate to="hub" replace />} />
      <Route path="hub" element={withPageSuspense(HubPage)} />
      <Route path="agent-library" element={withPageSuspense(AgentLibraryPage)} />
      <Route path="pulse" element={withPageSuspense(PulsePage)} />
      <Route path="corpus" element={withPageSuspense(CorpusPage)} />
      <Route path="trust" element={withPageSuspense(TrustPage)} />
      <Route path="insights" element={withPageSuspense(InsightsPage)} />
      <Route path="settings" element={withPageSuspense(SettingsPage)} />
      <Route path="chat" element={withPageSuspense(ChatPage)} />
      <Route path="agents" element={withPageSuspense(AgentsPage)} />
      <Route path="knowledge" element={withPageSuspense(KnowledgePage)} />
      <Route path="mcp" element={withPageSuspense(McpPage)} />
      <Route path="*" element={<Navigate to="hub" replace />} />
    </Routes>
  );
};

export default KuaiaiApp;
