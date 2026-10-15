import React from 'react';
import { createRoot } from 'react-dom/client';
import { App, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { queryClient } from './queryClient';
import { useGlobalStore } from './stores';
import { UniReport } from './components/uni-report/UniReport';
import { UniBatchDeleteButton } from './components/uni-batch';
import CorpusPage from './apps/kuaiai/pages/corpus';

await i18n.use(initReactI18next).init({ lng: 'zh-CN', resources: { 'zh-CN': { translation: {
  common: { export: '导出', print: '打印', confirm: '确定', cancel: '取消', batchDelete: '批量删除', confirmBatchDelete: '确定要批量删除选中的记录吗？', confirmBatchDeleteContent: '将删除 {{count}} 条记录，删除后无法恢复，请谨慎操作。' },
  components: { uniTable: { exportSelected: '导出选中', exportCurrentPage: '导出本页', exportAll: '导出全部' }, uniReport: { exporting: '正在导出', exportSuccess: '导出成功', exportEmpty: '暂无数据' } },
} } } });
useGlobalStore.setState({ currentUser: { id: 999, username: 'ui-test', is_tenant_admin: true } as any });
const rows = [{ name: '第一条', amount: 10 }, { name: '第二条', amount: 20 }, { name: '第三条', amount: 30 }];
queryClient.setQueryDefaults(['kuaiai', 'corpus'], { staleTime: Infinity });
queryClient.setQueryData(['kuaiai', 'corpus', { page: 2, page_size: 20 }], {
  items: Array.from({ length: 5 }, (_, i) => ({ id: i + 21, uuid: `doc-${i + 21}`, title: `语料${i + 21}`, knowledge_name: '验证知识库', knowledge_id: 1, type: 'faq', source_type: 'faq', chunk_count: 1, status: 'ready', is_active: true, error_summary: null, created_at: '2026-10-15T00:00:00', updated_at: '2026-10-15T00:00:00' })),
  total: 25, page: 2, page_size: 20,
});
queryClient.setQueryData(['kuaiai', 'corpus', 'knowledge-options'], [{ id: 1, name: '验证知识库' }]);
createRoot(document.getElementById('root')!).render(
  <BrowserRouter><QueryClientProvider client={queryClient}><ConfigProvider locale={zhCN}><App>
    {location.search.includes('view=corpus') ? <CorpusPage /> : <div style={{ height: '90vh', padding: 16 }}>
      <UniBatchDeleteButton selectedRowKeys={[]} disabled={false} onConfirm={() => {}} />
      <UniReport mode="config" title="导出验证报表" columnPersistenceId="test.report-controls" showFormatExportButton
        reportConfig={{ page_size: 2, fields: [{ field: 'name', label: '名称' }, { field: 'amount', label: '金额' }] }}
        datasetExecute={async (filters) => ({ data: rows.slice(Number(filters.offset || 0), Number(filters.offset || 0) + Number(filters.limit || 2)), total: rows.length, success: true })}
      />
    </div>}
  </App></ConfigProvider></QueryClientProvider></BrowserRouter>,
);
