import React, { useMemo, useCallback } from 'react';
import { App, Table } from 'antd';
import {
  UnorderedListOutlined,
  PartitionOutlined,
  ExportOutlined,
  ImportOutlined,
  RollbackOutlined,
  FileSearchOutlined,
  AccountBookOutlined,
  AlertOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import {
  outsourceWorkOrderApi,
  outsourceOrderApi,
  outsourceMaterialIssueApi,
  outsourceMaterialReceiptApi,
} from '../../../services/production';
import { useDashboardRequest } from '../../../utils/dashboardRequestOptions';
import { formatDateTime } from '../../../../../utils/format';
import {
  translateOutsourceWorkOrderLifecycleStatus,
} from '../../../utils/outsourceWorkOrderLifecycle';
import { MarkerTag, StatusTag } from '../../../../../constants/statusBadges';
import {
  ModuleCenterLayout,
  ModuleKpiRow,
  ModuleShortcutGrid,
  ModuleActionPanel,
  ModuleActionMasonry,
  showMasonryCard,
  masonryWeightFromRows,
  resolveMasonryEmptyFallback,
} from '../../../components/module-center';
import type { ModuleKpiDef, ModuleShortcutDef } from '../../../components/module-center';

const BASE = '/apps/kuaizhizao/outsource-management';

const OPEN_STATUSES = new Set(['released', 'in_progress', '已下达', '执行中']);
const DRAFT_STATUSES = new Set(['draft', '草稿']);

type OutsourceRow = Record<string, unknown>;

function normStatus(value: unknown): string {
  return String(value ?? '').trim();
}

function isOpenStatus(status: unknown): boolean {
  return OPEN_STATUSES.has(normStatus(status));
}

function isDraftStatus(status: unknown): boolean {
  return DRAFT_STATUSES.has(normStatus(status));
}

function plannedEndRaw(row: OutsourceRow): string | null {
  const raw = row.planned_end_date ?? row.plannedEndDate;
  if (raw == null || String(raw).trim() === '') return null;
  return String(raw);
}

function isOverdueOpen(row: OutsourceRow): boolean {
  if (!isOpenStatus(row.status)) return false;
  const end = plannedEndRaw(row);
  if (!end) return false;
  return dayjs(end).isBefore(dayjs(), 'day');
}

function needsIssue(row: OutsourceRow): boolean {
  if (!isOpenStatus(row.status)) return false;
  const qty = Number(row.quantity ?? 0);
  const issued = Number(row.issued_quantity ?? row.issuedQuantity ?? 0);
  return qty > 0 && issued < qty;
}

function needsReceipt(row: OutsourceRow): boolean {
  if (!isOpenStatus(row.status)) return false;
  const qty = Number(row.quantity ?? 0);
  const received = Number(row.received_quantity ?? row.receivedQuantity ?? 0);
  return qty > 0 && received < qty;
}

function rowCode(row: OutsourceRow): string {
  return String(row.code ?? '').trim() || '-';
}

function supplierName(row: OutsourceRow): string {
  return String(row.supplier_name ?? row.supplierName ?? '').trim() || '-';
}

function productName(row: OutsourceRow): string {
  return String(row.product_name ?? row.productName ?? '').trim() || '-';
}

function asRows(raw: unknown): OutsourceRow[] {
  if (Array.isArray(raw)) return raw as OutsourceRow[];
  if (raw && typeof raw === 'object' && Array.isArray((raw as { data?: unknown }).data)) {
    return (raw as { data: OutsourceRow[] }).data;
  }
  if (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown }).items)) {
    return (raw as { items: OutsourceRow[] }).items;
  }
  return [];
}

function statusTagColor(status: string): 'default' | 'processing' | 'success' | 'error' | 'warning' {
  const s = normStatus(status);
  if (DRAFT_STATUSES.has(s)) return 'default';
  if (s === 'released' || s === '已下达') return 'processing';
  if (s === 'in_progress' || s === '执行中') return 'warning';
  if (s === 'completed' || s === '已完成') return 'success';
  if (s === 'cancelled' || s === '已取消') return 'error';
  return 'default';
}

const PROCESS_ORDER_STATUS_I18N: Record<string, string> = {
  draft: 'app.kuaizhizao.outsourceOrder.statusDraft',
  released: 'app.kuaizhizao.outsourceOrder.statusReleased',
  in_progress: 'app.kuaizhizao.outsourceOrder.statusInProgress',
  completed: 'app.kuaizhizao.outsourceOrder.statusCompleted',
  cancelled: 'app.kuaizhizao.outsourceOrder.statusCancelled',
  草稿: 'app.kuaizhizao.outsourceOrder.statusDraft',
  已下达: 'app.kuaizhizao.outsourceOrder.statusReleased',
  执行中: 'app.kuaizhizao.outsourceOrder.statusInProgress',
  已完成: 'app.kuaizhizao.outsourceOrder.statusCompleted',
  已取消: 'app.kuaizhizao.outsourceOrder.statusCancelled',
};

function translateProcessOrderStatus(t: (key: string) => string, status?: string | null): string {
  if (!status) return '-';
  const key = PROCESS_ORDER_STATUS_I18N[normStatus(status)];
  return key ? t(key) : status;
}

const OutsourceDashboard: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { message } = App.useApp();

  const { data: woData, loading: woLoading } = useDashboardRequest(
    () => outsourceWorkOrderApi.list({ limit: 50, order_by: '-updated_at' }),
    'kz:outsource-dashboard:work-orders',
    {
      onError: (e: { message?: string }) =>
        message.error(e?.message || t('app.kuaizhizao.outsourceDashboard.loadFailed')),
    },
  );

  const { data: orderData, loading: orderLoading } = useDashboardRequest(
    () => outsourceOrderApi.list({ limit: 50, order_by: '-updated_at' }),
    'kz:outsource-dashboard:process-orders',
    {
      onError: (e: { message?: string }) =>
        message.error(e?.message || t('app.kuaizhizao.outsourceDashboard.loadFailed')),
    },
  );

  const { data: issueRaw, loading: issueLoading } = useDashboardRequest(
    () => outsourceMaterialIssueApi.list({ limit: 8 }),
    'kz:outsource-dashboard:recent-issues',
  );

  const { data: receiptRaw, loading: receiptLoading } = useDashboardRequest(
    () => outsourceMaterialReceiptApi.list({ limit: 8 }),
    'kz:outsource-dashboard:recent-receipts',
  );

  const workOrders = useMemo(() => asRows(woData?.data ?? woData), [woData]);
  const processOrders = useMemo(() => asRows(orderData?.data ?? orderData), [orderData]);
  const recentIssues = useMemo(() => asRows(issueRaw).slice(0, 6), [issueRaw]);
  const recentReceipts = useMemo(() => asRows(receiptRaw).slice(0, 6), [receiptRaw]);

  const openWorkOrders = useMemo(
    () => workOrders.filter((row) => isOpenStatus(row.status)).slice(0, 8),
    [workOrders],
  );
  const draftWorkOrders = useMemo(
    () => workOrders.filter((row) => isDraftStatus(row.status)).slice(0, 8),
    [workOrders],
  );
  const overdueWorkOrders = useMemo(
    () =>
      workOrders
        .filter(isOverdueOpen)
        .sort((a, b) => dayjs(plannedEndRaw(a)!).valueOf() - dayjs(plannedEndRaw(b)!).valueOf())
        .slice(0, 8),
    [workOrders],
  );
  const pendingIssueRows = useMemo(
    () => workOrders.filter(needsIssue).slice(0, 8),
    [workOrders],
  );
  const pendingReceiptRows = useMemo(
    () => workOrders.filter(needsReceipt).slice(0, 8),
    [workOrders],
  );
  const openProcessOrders = useMemo(
    () => processOrders.filter((row) => isOpenStatus(row.status)).slice(0, 8),
    [processOrders],
  );

  const openWoCount = useMemo(
    () => workOrders.filter((row) => isOpenStatus(row.status)).length,
    [workOrders],
  );
  const draftWoCount = useMemo(
    () => workOrders.filter((row) => isDraftStatus(row.status)).length,
    [workOrders],
  );
  const openProcessCount = useMemo(
    () => processOrders.filter((row) => isOpenStatus(row.status)).length,
    [processOrders],
  );
  const draftProcessCount = useMemo(
    () => processOrders.filter((row) => isDraftStatus(row.status)).length,
    [processOrders],
  );
  const overdueCount = useMemo(() => workOrders.filter(isOverdueOpen).length, [workOrders]);
  const pendingReceiptCount = useMemo(
    () => workOrders.filter(needsReceipt).length,
    [workOrders],
  );

  const statusStructureRows = useMemo(() => {
    const counts: Record<string, number> = {
      draft: 0,
      released: 0,
      in_progress: 0,
      completed: 0,
      cancelled: 0,
    };
    workOrders.forEach((row) => {
      const s = normStatus(row.status);
      if (s === 'draft' || s === '草稿') counts.draft += 1;
      else if (s === 'released' || s === '已下达') counts.released += 1;
      else if (s === 'in_progress' || s === '执行中') counts.in_progress += 1;
      else if (s === 'completed' || s === '已完成') counts.completed += 1;
      else if (s === 'cancelled' || s === '已取消') counts.cancelled += 1;
    });
    return [
      {
        key: 'draft',
        label: translateOutsourceWorkOrderLifecycleStatus(t, 'draft'),
        count: counts.draft,
        tone: 'default' as const,
      },
      {
        key: 'released',
        label: translateOutsourceWorkOrderLifecycleStatus(t, 'released'),
        count: counts.released,
        tone: 'processing' as const,
      },
      {
        key: 'in_progress',
        label: translateOutsourceWorkOrderLifecycleStatus(t, 'in_progress'),
        count: counts.in_progress,
        tone: 'warning' as const,
      },
      {
        key: 'completed',
        label: translateOutsourceWorkOrderLifecycleStatus(t, 'completed'),
        count: counts.completed,
        tone: 'success' as const,
      },
      {
        key: 'cancelled',
        label: translateOutsourceWorkOrderLifecycleStatus(t, 'cancelled'),
        count: counts.cancelled,
        tone: 'error' as const,
      },
    ].filter((row) => row.count > 0);
  }, [t, workOrders]);

  const kpis: ModuleKpiDef[] = useMemo(
    () => [
      {
        key: 'open-wo',
        title: t('app.kuaizhizao.outsourceDashboard.kpi.openWorkOrders'),
        value: openWoCount,
        subtitle: t('app.kuaizhizao.outsourceDashboard.kpi.openWorkOrdersSubtitle'),
        icon: <UnorderedListOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #1890ff 0%, #36cfc9 100%)',
        boxShadow: '0 4px 12px rgba(24, 144, 255, 0.15)',
        onClick: () => navigate(`${BASE}/outsource-work-orders`),
        sideMetrics: [
          {
            label: t('app.kuaizhizao.outsourceDashboard.kpi.draft'),
            value: draftWoCount,
          },
        ],
      },
      {
        key: 'open-process',
        title: t('app.kuaizhizao.outsourceDashboard.kpi.openProcessOrders'),
        value: openProcessCount,
        subtitle: t('app.kuaizhizao.outsourceDashboard.kpi.openProcessOrdersSubtitle'),
        icon: <PartitionOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient: 'linear-gradient(135deg, #722ed1 0%, #b37feb 100%)',
        boxShadow: '0 4px 12px rgba(114, 46, 209, 0.15)',
        onClick: () => navigate(`${BASE}/outsource-orders`),
        sideMetrics: [
          {
            label: t('app.kuaizhizao.outsourceDashboard.kpi.draft'),
            value: draftProcessCount,
          },
        ],
      },
      {
        key: 'overdue',
        title: t('app.kuaizhizao.outsourceDashboard.kpi.overdue'),
        value: overdueCount,
        subtitle:
          overdueCount > 0
            ? t('app.kuaizhizao.outsourceDashboard.kpi.overdueSubtitle', { count: overdueCount })
            : t('app.kuaizhizao.outsourceDashboard.kpi.overdueNone'),
        icon: <AlertOutlined style={{ fontSize: 24, color: '#fff' }} />,
        gradient:
          overdueCount > 0
            ? 'linear-gradient(135deg, #ff4d4f 0%, #ff7875 100%)'
            : 'linear-gradient(135deg, #52c41a 0%, #95de64 100%)',
        boxShadow:
          overdueCount > 0
            ? '0 4px 12px rgba(255, 77, 79, 0.15)'
            : '0 4px 12px rgba(82, 196, 26, 0.15)',
        onClick: () => navigate(`${BASE}/outsource-work-orders`),
        sideMetrics: [
          {
            label: t('app.kuaizhizao.outsourceDashboard.kpi.pendingReceipt'),
            value: pendingReceiptCount,
          },
        ],
      },
    ],
    [
      draftProcessCount,
      draftWoCount,
      navigate,
      openProcessCount,
      openWoCount,
      overdueCount,
      pendingReceiptCount,
      t,
    ],
  );

  const shortcuts: ModuleShortcutDef[] = useMemo(
    () => [
      {
        key: 'work-orders',
        title: t('app.kuaizhizao.outsourceWorkOrder.title'),
        icon: <UnorderedListOutlined style={{ fontSize: 22, color: '#1890ff' }} />,
        path: `${BASE}/outsource-work-orders`,
      },
      {
        key: 'process-orders',
        title: t('app.kuaizhizao.outsourceOrder.title'),
        icon: <PartitionOutlined style={{ fontSize: 22, color: '#722ed1' }} />,
        path: `${BASE}/outsource-orders`,
      },
      {
        key: 'issue',
        title: t('app.kuaizhizao.menu.outsource-management.outsource-issue'),
        icon: <ExportOutlined style={{ fontSize: 22, color: '#fa8c16' }} />,
        path: `${BASE}/outsource-issue`,
      },
      {
        key: 'receipt',
        title: t('app.kuaizhizao.menu.outsource-management.outsource-receipt'),
        icon: <ImportOutlined style={{ fontSize: 22, color: '#52c41a' }} />,
        path: `${BASE}/outsource-receipt`,
      },
      {
        key: 'material-return',
        title: t('app.kuaizhizao.menu.outsource-management.outsource-material-return'),
        icon: <RollbackOutlined style={{ fontSize: 22, color: '#13c2c2' }} />,
        path: `${BASE}/outsource-material-return`,
      },
      {
        key: 'product-return',
        title: t('app.kuaizhizao.menu.outsource-management.outsource-product-return'),
        icon: <RollbackOutlined style={{ fontSize: 22, color: '#ff4d4f' }} />,
        path: `${BASE}/outsource-product-return`,
      },
      {
        key: 'report-query',
        title: t('app.kuaizhizao.menu.reports.outsource-order-query'),
        icon: <FileSearchOutlined style={{ fontSize: 22, color: '#597ef7' }} />,
        path: `${BASE}/reports/outsource-order-query`,
      },
      {
        key: 'cost',
        title: t('app.kuaizhizao.menu.cost-management.outsource-cost'),
        icon: <AccountBookOutlined style={{ fontSize: 22, color: '#eb2f96' }} />,
        path: '/apps/kuaicaiwu/cost-management/cost-calculations?tab=outsource',
      },
    ],
    [t],
  );

  const formatEnd = useCallback((raw: string | null | undefined) => {
    if (!raw) return '—';
    const d = dayjs(raw);
    return d.isValid() ? formatDateTime(raw, 'MM-DD') : '—';
  }, []);

  const woColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.outsourceDashboard.colCode'),
        dataIndex: 'code',
        width: 128,
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) => (
          <a onClick={() => navigate(`${BASE}/outsource-work-orders`)}>{rowCode(record)}</a>
        ),
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colProduct'),
        dataIndex: 'product_name',
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) => productName(record),
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colSupplier'),
        dataIndex: 'supplier_name',
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) => supplierName(record),
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 80,
        render: (status: string) => (
          <StatusTag color={statusTagColor(status)}>
            {translateOutsourceWorkOrderLifecycleStatus(t, status)}
          </StatusTag>
        ),
      },
    ],
    [navigate, t],
  );

  const overdueColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.outsourceDashboard.colCode'),
        dataIndex: 'code',
        width: 128,
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) => (
          <a onClick={() => navigate(`${BASE}/outsource-work-orders`)}>{rowCode(record)}</a>
        ),
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colSupplier'),
        dataIndex: 'supplier_name',
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) => supplierName(record),
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colDueDate'),
        dataIndex: 'planned_end_date',
        width: 72,
        render: (_: unknown, record: OutsourceRow) => (
          <span style={{ whiteSpace: 'nowrap', color: '#ff4d4f' }}>
            {formatEnd(plannedEndRaw(record))}
          </span>
        ),
      },
    ],
    [formatEnd, navigate, t],
  );

  const processColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.outsourceDashboard.colCode'),
        dataIndex: 'code',
        width: 128,
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) => (
          <a onClick={() => navigate(`${BASE}/outsource-orders`)}>{rowCode(record)}</a>
        ),
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colSupplier'),
        dataIndex: 'supplier_name',
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) => supplierName(record),
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 80,
        render: (status: string) => (
          <StatusTag color={statusTagColor(status)}>
            {translateProcessOrderStatus(t, status)}
          </StatusTag>
        ),
      },
    ],
    [navigate, t],
  );

  const issueColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.outsourceDashboard.colIssueCode'),
        dataIndex: 'code',
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) => (
          <a onClick={() => navigate(`${BASE}/outsource-issue`)}>{rowCode(record)}</a>
        ),
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colWoCode'),
        dataIndex: 'outsource_work_order_code',
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) =>
          String(record.outsource_work_order_code ?? record.outsourceWorkOrderCode ?? '').trim() ||
          '—',
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colTime'),
        dataIndex: 'issued_at',
        width: 96,
        render: (_: unknown, record: OutsourceRow) => {
          const raw = String(record.issued_at ?? record.issuedAt ?? record.created_at ?? '');
          if (!raw) return '—';
          return <span style={{ whiteSpace: 'nowrap' }}>{formatDateTime(raw, 'MM-DD HH:mm')}</span>;
        },
      },
    ],
    [navigate, t],
  );

  const receiptColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.outsourceDashboard.colReceiptCode'),
        dataIndex: 'code',
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) => (
          <a onClick={() => navigate(`${BASE}/outsource-receipt`)}>{rowCode(record)}</a>
        ),
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colWoCode'),
        dataIndex: 'outsource_work_order_code',
        ellipsis: true,
        render: (_: unknown, record: OutsourceRow) =>
          String(record.outsource_work_order_code ?? record.outsourceWorkOrderCode ?? '').trim() ||
          '—',
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colTime'),
        dataIndex: 'received_at',
        width: 96,
        render: (_: unknown, record: OutsourceRow) => {
          const raw = String(record.received_at ?? record.receivedAt ?? record.created_at ?? '');
          if (!raw) return '—';
          return <span style={{ whiteSpace: 'nowrap' }}>{formatDateTime(raw, 'MM-DD HH:mm')}</span>;
        },
      },
    ],
    [navigate, t],
  );

  const statusStructureColumns = useMemo(
    () => [
      {
        title: t('common.status'),
        dataIndex: 'label',
        render: (label: string, row: { tone: 'default' | 'processing' | 'success' | 'error' | 'warning' }) => (
          <MarkerTag color={row.tone}>{label}</MarkerTag>
        ),
      },
      {
        title: t('app.kuaizhizao.outsourceDashboard.colCount'),
        dataIndex: 'count',
        width: 72,
      },
    ],
    [t],
  );

  const masonryLoading = woLoading || orderLoading || issueLoading || receiptLoading;
  const masonryEmptyFallback = resolveMasonryEmptyFallback(masonryLoading, [
    overdueWorkOrders.length > 0,
    openWorkOrders.length > 0,
    openProcessOrders.length > 0,
    pendingIssueRows.length > 0,
    pendingReceiptRows.length > 0,
    draftWorkOrders.length > 0,
    recentIssues.length > 0,
    recentReceipts.length > 0,
    statusStructureRows.length > 0,
  ]);

  return (
    <ModuleCenterLayout
      loading={(woLoading || orderLoading) && workOrders.length === 0 && processOrders.length === 0}
      kpiRow={<ModuleKpiRow items={kpis} />}
      shortcutRow={<ModuleShortcutGrid items={shortcuts} />}
      actionRow={
        <ModuleActionMasonry>
          {showMasonryCard(woLoading, overdueWorkOrders.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.outsourceDashboard.overdueTitle')}
              loading={woLoading}
              masonryWeight={masonryWeightFromRows(overdueWorkOrders.length)}
              extra={
                <a onClick={() => navigate(`${BASE}/outsource-work-orders`)}>
                  {t('app.kuaizhizao.outsourceDashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.uuid ?? r.code)}
                dataSource={overdueWorkOrders}
                columns={overdueColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(woLoading, openWorkOrders.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.outsourceDashboard.openWorkOrdersTitle')}
              loading={woLoading}
              masonryWeight={masonryWeightFromRows(openWorkOrders.length)}
              extra={
                <a onClick={() => navigate(`${BASE}/outsource-work-orders`)}>
                  {t('app.kuaizhizao.outsourceDashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.uuid ?? r.code)}
                dataSource={openWorkOrders}
                columns={woColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(orderLoading, openProcessOrders.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.outsourceDashboard.openProcessOrdersTitle')}
              loading={orderLoading}
              masonryWeight={masonryWeightFromRows(openProcessOrders.length)}
              extra={
                <a onClick={() => navigate(`${BASE}/outsource-orders`)}>
                  {t('app.kuaizhizao.outsourceDashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.uuid ?? r.code)}
                dataSource={openProcessOrders}
                columns={processColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(woLoading, pendingIssueRows.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.outsourceDashboard.pendingIssueTitle')}
              loading={woLoading}
              masonryWeight={masonryWeightFromRows(pendingIssueRows.length)}
              extra={
                <a onClick={() => navigate(`${BASE}/outsource-issue`)}>
                  {t('app.kuaizhizao.outsourceDashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.uuid ?? r.code)}
                dataSource={pendingIssueRows}
                columns={woColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(woLoading, pendingReceiptRows.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.outsourceDashboard.pendingReceiptTitle')}
              loading={woLoading}
              masonryWeight={masonryWeightFromRows(pendingReceiptRows.length)}
              extra={
                <a onClick={() => navigate(`${BASE}/outsource-receipt`)}>
                  {t('app.kuaizhizao.outsourceDashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.uuid ?? r.code)}
                dataSource={pendingReceiptRows}
                columns={woColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(woLoading, draftWorkOrders.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.outsourceDashboard.draftWorkOrdersTitle')}
              loading={woLoading}
              masonryWeight={masonryWeightFromRows(draftWorkOrders.length)}
              extra={
                <a onClick={() => navigate(`${BASE}/outsource-work-orders`)}>
                  {t('app.kuaizhizao.outsourceDashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.uuid ?? r.code)}
                dataSource={draftWorkOrders}
                columns={woColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(issueLoading, recentIssues.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.outsourceDashboard.recentIssuesTitle')}
              loading={issueLoading}
              masonryWeight={masonryWeightFromRows(recentIssues.length)}
              extra={
                <a onClick={() => navigate(`${BASE}/outsource-issue`)}>
                  {t('app.kuaizhizao.outsourceDashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.uuid ?? r.code)}
                dataSource={recentIssues}
                columns={issueColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(receiptLoading, recentReceipts.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.outsourceDashboard.recentReceiptsTitle')}
              loading={receiptLoading}
              masonryWeight={masonryWeightFromRows(recentReceipts.length)}
              extra={
                <a onClick={() => navigate(`${BASE}/outsource-receipt`)}>
                  {t('app.kuaizhizao.outsourceDashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey={(r) => String(r.id ?? r.uuid ?? r.code)}
                dataSource={recentReceipts}
                columns={receiptColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
          {showMasonryCard(woLoading, statusStructureRows.length > 0, masonryEmptyFallback) ? (
            <ModuleActionPanel
              layout="masonry"
              title={t('app.kuaizhizao.outsourceDashboard.statusStructureTitle')}
              loading={woLoading}
              masonryWeight={masonryWeightFromRows(statusStructureRows.length)}
              extra={
                <a onClick={() => navigate(`${BASE}/outsource-work-orders`)}>
                  {t('app.kuaizhizao.outsourceDashboard.viewAll')}
                </a>
              }
            >
              <Table
                size="small"
                tableLayout="fixed"
                pagination={false}
                rowKey="key"
                dataSource={statusStructureRows}
                columns={statusStructureColumns}
                locale={{ emptyText: t('common.noData') }}
              />
            </ModuleActionPanel>
          ) : null}
        </ModuleActionMasonry>
      }
    />
  );
};

export default OutsourceDashboard;
