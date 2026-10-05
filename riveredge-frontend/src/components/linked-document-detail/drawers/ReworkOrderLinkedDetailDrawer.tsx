import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Descriptions, Result, Typography } from 'antd';
import type { ProDescriptionsItemProps } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import {
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  detailDrawerBasicColumn,
  useDetailDrawerDescriptionItems,
} from '../../layout-templates';
import { alignDescriptionColumns } from '../../../apps/kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { reworkOrderApi } from '../../../apps/kuaizhizao/services/production';

export function ReworkOrderLinkedDetailDrawer({
  open,
  documentId,
  onClose,
  zIndex,
}: {
  open: boolean;
  documentId: number;
  onClose: () => void;
  zIndex?: number;
}) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [record, setRecord] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    if (!open || documentId <= 0) {
      setRecord(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setRecord((await reworkOrderApi.get(String(documentId))) as Record<string, unknown>);
    } catch (e: unknown) {
      const err = e as { message?: string };
      const msg = err?.message || t('app.kuaizhizao.reworkOrder.loadDetailFailed');
      setRecord(null);
      setError(msg);
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [documentId, message, open, t]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const columns = useMemo(
    () =>
      alignDescriptionColumns([
        { title: t('app.kuaizhizao.reworkOrder.reworkCode'), dataIndex: 'rework_code' },
        { title: t('app.kuaizhizao.reworkOrder.productName'), dataIndex: 'product_name' },
        { title: t('common.status'), dataIndex: 'status' },
      ] as ProDescriptionsItemProps<Record<string, unknown>>[]),
    [t],
  );

  const basicItems = useDetailDrawerDescriptionItems(columns, record, 'rework_order');
  const code = String(record?.rework_code ?? record?.code ?? '');

  if (error && !record && !loading) {
    return (
      <DetailDrawerTemplate
        open={open}
        onClose={onClose}
        size={DRAWER_CONFIG.HALF_WIDTH}
        zIndex={zIndex}
        title={t('app.kuaizhizao.reworkOrder.detailTitle')}
        plainBody={
          <Result
            status="error"
            title={error}
            extra={<Typography.Link onClick={() => setRefreshKey((k) => k + 1)}>{t('common.retry')}</Typography.Link>}
          />
        }
      />
    );
  }

  return (
    <DetailDrawerTemplate
      open={open}
      loading={loading}
      onClose={onClose}
      size={DRAWER_CONFIG.HALF_WIDTH}
      zIndex={zIndex}
      title={`${t('app.kuaizhizao.reworkOrder.detailTitle')}${code ? ` - ${code}` : ''}`}
      basic={
        record ? (
          <Descriptions column={detailDrawerBasicColumn(false)} size="small" items={basicItems} />
        ) : undefined
      }
      traceDocument={
        record?.id != null
          ? { documentType: 'rework_order', documentId: Number(record.id), selfDocumentId: Number(record.id) }
          : undefined
      }
    />
  );
}
