/**
 * SyncPushHub「同步记录」Tab：只读展示 core_sync_run_logs（入站 + 外推）。
 * 数据：GET /apps/kuaizhizao/document-push/run-history
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Space, Table, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import {
  listDocumentPushRunHistory,
  type DocumentPushRunHistoryItem,
  type ListSyncRunHistoryFn,
} from '../../apps/kuaizhizao/services/document-push';

export type { ListSyncRunHistoryFn };
import { MarkerTag } from '../../constants/statusBadges';
import { formatDateTimeBySiteSetting } from '../../utils/format';

export interface SyncRunHistoryPanelProps {
  active: boolean;
  sourceType: string;
  targetProfiles?: string[];
  /** 主数据等入站同步走自有 API 时传入 */
  listHistory?: ListSyncRunHistoryFn;
  /** 同步成功后递增，触发列表重载 */
  refreshNonce?: number;
}

const DEFAULT_PAGE_SIZE = 10;

function statusMarkerColor(status: string): 'success' | 'warning' | 'error' | 'default' {
  if (status === 'success') return 'success';
  if (status === 'partial') return 'warning';
  if (status === 'failed') return 'error';
  return 'default';
}

function formatInboundSyncRunStats(
  record: DocumentPushRunHistoryItem,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const parts = [
    t('components.syncPushHub.historyStatsFetched', { n: record.fetched ?? 0 }),
    t('components.syncPushHub.historyStatsCreated', { n: record.created ?? 0 }),
    t('components.syncPushHub.historyStatsUpdated', { n: record.updated ?? 0 }),
    t('components.syncPushHub.historyStatsSkipped', { n: record.skipped ?? 0 }),
  ];
  if ((record.failed ?? 0) > 0) {
    parts.push(t('components.syncPushHub.historyStatsFailed', { n: record.failed ?? 0 }));
  }
  if (record.truncated) {
    parts.push(t('components.syncPushHub.historyStatsTruncated'));
  }
  return parts.join(' ');
}

export const SyncRunHistoryPanel: React.FC<SyncRunHistoryPanelProps> = ({
  active,
  sourceType,
  targetProfiles,
  listHistory,
  refreshNonce = 0,
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<DocumentPushRunHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [loadError, setLoadError] = useState<string | null>(null);

  const profilesKey = (targetProfiles || []).join(',');

  const load = useCallback(async () => {
    if (!active || !sourceType) return;
    setLoading(true);
    setLoadError(null);
    try {
      const fetchHistory = listHistory ?? listDocumentPushRunHistory;
      const result = await fetchHistory({
        sourceType,
        targetProfiles: targetProfiles?.length ? targetProfiles : undefined,
        skip: (page - 1) * pageSize,
        limit: pageSize,
      });
      setRows(result?.data ?? []);
      setTotal(result?.total ?? 0);
    } catch (error: unknown) {
      const message =
        error && typeof error === 'object' && 'message' in error
          ? String((error as { message?: unknown }).message || '')
          : '';
      setLoadError(message || t('components.syncPushHub.historyLoadFailed'));
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [active, listHistory, page, pageSize, profilesKey, refreshNonce, sourceType, t, targetProfiles]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (active) setPage(1);
  }, [active, sourceType, profilesKey]);

  const columns: ColumnsType<DocumentPushRunHistoryItem> = useMemo(
    () => [
      {
        title: t('components.syncPushHub.historyColStartedAt'),
        dataIndex: 'started_at',
        key: 'started_at',
        width: 170,
        render: (value?: string | null, record?: DocumentPushRunHistoryItem) => {
          const raw = value || record?.created_at;
          return raw ? formatDateTimeBySiteSetting(raw) : '-';
        },
      },
      {
        title: t('components.syncPushHub.historyColMode'),
        dataIndex: 'mode',
        key: 'mode',
        width: 90,
        render: (value: string) => {
          if (value === 'push') return t('components.syncPushHub.historyModePush');
          if (value === 'incremental') return t('components.syncPushHub.historyModeIncremental');
          return t('components.syncPushHub.historyModeFull');
        },
      },
      {
        title: t('components.syncPushHub.historyColStatus'),
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (value: string) => (
          <MarkerTag color={statusMarkerColor(value)} style={{ marginInlineEnd: 0 }}>
            {value === 'success'
              ? t('components.syncPushHub.historyStatusSuccess')
              : value === 'partial'
                ? t('components.syncPushHub.historyStatusPartial')
                : t('components.syncPushHub.historyStatusFailed')}
          </MarkerTag>
        ),
      },
      {
        title: t('components.syncPushHub.historyColProfile'),
        dataIndex: 'target_profile',
        key: 'target_profile',
        width: 160,
        ellipsis: true,
        render: (value?: string | null) => value || '-',
      },
      {
        title: t('components.syncPushHub.historyColDuration'),
        dataIndex: 'duration_ms',
        key: 'duration_ms',
        width: 90,
        align: 'right',
        render: (value?: number) => {
          if (!value || value <= 0) return '-';
          if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
          return `${value}ms`;
        },
      },
      {
        title: t('components.syncPushHub.historyColSummary'),
        dataIndex: 'error_summary',
        key: 'error_summary',
        ellipsis: true,
        render: (value?: string | null, record?: DocumentPushRunHistoryItem) => {
          if (!record) return '-';
          const isPush = record.entity_type === 'document_push' || record.mode === 'push';
          const stats = isPush ? '' : formatInboundSyncRunStats(record, t);
          const detail = (value || '').trim();
          const text = detail ? (stats ? `${stats} ${detail}` : detail) : stats;
          if (!text) return '-';
          const shown = text.length > 96 ? `${text.slice(0, 96)}…` : text;
          const danger = record.status === 'failed' || record.status === 'partial';
          return (
            <Tooltip title={text}>
              <Typography.Text type={danger ? 'danger' : undefined} style={{ fontSize: 12 }}>
                {shown}
              </Typography.Text>
            </Tooltip>
          );
        },
      },
    ],
    [t],
  );

  return (
    <Space orientation="vertical" size={12} style={{ width: '100%' }}>
      {loadError ? <Typography.Text type="danger">{loadError}</Typography.Text> : null}
      <Table<DocumentPushRunHistoryItem>
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: ['10', '20', '50'],
          showTotal: (n) => t('components.syncPushHub.historyTotal', { total: n }),
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPage);
            setPageSize(nextPageSize);
          },
        }}
      />
    </Space>
  );
};

export default SyncRunHistoryPanel;
