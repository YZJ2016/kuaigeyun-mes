/**
 * 关联单据：送货单原版详情（只取数 + DeliveryNoticeDetailDrawer）
 */

import React, { useCallback, useEffect, useState } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  DeliveryNoticeDetailDrawer,
  type DeliveryNoticeDetailRecord,
} from '../../../apps/kuaizhizao/pages/warehouse-management/delivery-notes/components/DeliveryNoticeDetailDrawer';
import { deliveryNoticeApi } from '../../../apps/kuaizhizao/services/delivery-notice';

export type DeliveryNoticeLinkedDetailDrawerProps = {
  open: boolean;
  documentId: number;
  onClose: () => void;
  zIndex?: number;
};

export function DeliveryNoticeLinkedDetailDrawer({
  open,
  documentId,
  onClose,
  zIndex,
}: DeliveryNoticeLinkedDetailDrawerProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [notice, setNotice] = useState<DeliveryNoticeDetailRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    if (!open || documentId <= 0) {
      setNotice(null);
      setLoadError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    setNotice((prev) => (prev?.id === documentId ? prev : null));
    try {
      const detail = (await deliveryNoticeApi.get(String(documentId))) as DeliveryNoticeDetailRecord;
      setNotice(detail);
    } catch (e: unknown) {
      const err = e as { message?: string; detail?: string };
      const msg = err?.message || err?.detail || t('app.kuaizhizao.deliveryNote.msg.loadDetailFailed');
      setNotice(null);
      setLoadError(msg);
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [documentId, message, open, t]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <DeliveryNoticeDetailDrawer
      open={open}
      onClose={onClose}
      notice={notice}
      loading={loading}
      error={loadError}
      onRetry={() => setRefreshKey((k) => k + 1)}
      zIndex={zIndex}
      trackingRefreshKey={refreshKey}
    />
  );
}
