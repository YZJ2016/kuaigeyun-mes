/**
 * SyncPushHub「同步对账」Tab：对比当前页/勾选本地单据与金蝶 IM 单。
 * 数据：POST /apps/kuaizhizao/document-push/reconcile
 */
import React, { useCallback, useMemo, useState } from 'react';
import { Alert, Button, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  reconcileDocumentPush,
  type DocumentPushReconcileRow,
} from '../../apps/kuaizhizao/services/document-push';
import { MarkerTag } from '../../constants/statusBadges';
import { getApiErrorMessage } from '../../utils/errorHandler';

export interface SyncReconcilePanelProps {
  active: boolean;
  sourceType: string;
  /** 当前页或勾选的本地单据 ID；每次对账时重新取值 */
  getDocumentIds: () => number[];
}

function resultMarkerColor(
  result: string,
): 'success' | 'warning' | 'error' | 'default' {
  if (result === 'matched') return 'success';
  if (result === 'mismatch' || result === 'remote_missing') return 'warning';
  if (result === 'error' || result === 'local_missing') return 'error';
  return 'default';
}

export const SyncReconcilePanel: React.FC<SyncReconcilePanelProps> = ({
  active,
  sourceType,
  getDocumentIds,
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<DocumentPushReconcileRow[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [docLabel, setDocLabel] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [idCount, setIdCount] = useState(0);

  const run = useCallback(async () => {
    if (!active || !sourceType) return;
    const ids = (getDocumentIds() || [])
      .map((id) => Number(id))
      .filter((id) => Number.isFinite(id) && id > 0);
    setIdCount(ids.length);
    if (!ids.length) {
      setRows([]);
      setSummary({});
      setLoadError(t('components.syncPushHub.reconcileNeedIds'));
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const result = await reconcileDocumentPush({
        sourceType,
        sourceIds: ids,
      });
      setRows(result?.rows ?? []);
      setSummary(result?.summary ?? {});
      setDocLabel(String(result?.doc_label || ''));
    } catch (error: unknown) {
      setLoadError(
        getApiErrorMessage(error, t('components.syncPushHub.reconcileLoadFailed')),
      );
      setRows([]);
      setSummary({});
    } finally {
      setLoading(false);
    }
  }, [active, getDocumentIds, sourceType, t]);

  const columns: ColumnsType<DocumentPushReconcileRow> = useMemo(
    () => [
      {
        title: t('components.syncPushHub.reconcileColLocalCode'),
        dataIndex: 'local_code',
        key: 'local_code',
        width: 140,
        ellipsis: true,
      },
      {
        title: t('components.syncPushHub.reconcileColLocalStatus'),
        dataIndex: 'local_status',
        key: 'local_status',
        width: 96,
        ellipsis: true,
      },
      {
        title: t('components.syncPushHub.reconcileColLocalQty'),
        dataIndex: 'local_qty',
        key: 'local_qty',
        width: 88,
        align: 'right',
      },
      {
        title: t('components.syncPushHub.reconcileColRemoteBillno'),
        dataIndex: 'remote_billno',
        key: 'remote_billno',
        width: 140,
        ellipsis: true,
        render: (v: string | null | undefined) => v || '-',
      },
      {
        title: t('components.syncPushHub.reconcileColRemoteStatus'),
        dataIndex: 'remote_status',
        key: 'remote_status',
        width: 110,
        ellipsis: true,
        render: (v: string | null | undefined) => v || '-',
      },
      {
        title: t('components.syncPushHub.reconcileColRemoteQty'),
        dataIndex: 'remote_qty',
        key: 'remote_qty',
        width: 88,
        align: 'right',
        render: (v: string | null | undefined) => v || '-',
      },
      {
        title: t('components.syncPushHub.reconcileColResult'),
        dataIndex: 'result',
        key: 'result',
        width: 120,
        fixed: 'right',
        render: (result: string, record) => {
          const labelKey = `components.syncPushHub.reconcileResult.${result}`;
          const label = t(labelKey);
          const text = label === labelKey ? result : label;
          const fields = (record.mismatch_fields || []).join('、');
          return (
            <Space size={4}>
              <MarkerTag color={resultMarkerColor(result)}>{text}</MarkerTag>
              {fields ? (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {fields}
                </Typography.Text>
              ) : null}
            </Space>
          );
        },
      },
    ],
    [t],
  );

  const summaryText = useMemo(() => {
    const parts = [
      t('components.syncPushHub.reconcileSummaryMatched', {
        n: summary.matched ?? 0,
      }),
      t('components.syncPushHub.reconcileSummaryMismatch', {
        n: summary.mismatch ?? 0,
      }),
      t('components.syncPushHub.reconcileSummaryNotPushed', {
        n: summary.not_pushed ?? 0,
      }),
      t('components.syncPushHub.reconcileSummaryRemoteMissing', {
        n: summary.remote_missing ?? 0,
      }),
    ];
    if ((summary.error ?? 0) > 0) {
      parts.push(
        t('components.syncPushHub.reconcileSummaryError', { n: summary.error }),
      );
    }
    return parts.join(' ');
  }, [summary, t]);

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        title={
          docLabel
            ? t('components.syncPushHub.reconcileHintNamed', { name: docLabel })
            : t('components.syncPushHub.reconcileHint')
        }
      />
      <Space style={{ marginBottom: 12 }} wrap>
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => void run()}
        >
          {t('components.syncPushHub.reconcileRun')}
        </Button>
        <Typography.Text type="secondary">
          {t('components.syncPushHub.reconcileIdCount', { n: idCount })}
        </Typography.Text>
        {rows.length > 0 ? (
          <Typography.Text type="secondary">{summaryText}</Typography.Text>
        ) : null}
      </Space>
      {loadError ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          title={loadError}
        />
      ) : null}
      <Table<DocumentPushReconcileRow>
        size="small"
        rowKey={(r) => String(r.source_id)}
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={false}
        scroll={{ x: 900, y: 360 }}
      />
    </div>
  );
};

export default SyncReconcilePanel;
