/**
 * 关联单据：出库 hub（生产领料 / 委外发料等）→ OutboundDetailDrawer
 */

import React, { useCallback, useEffect, useState } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  OutboundDetailDrawer,
  type OutboundDetailRecord,
} from '../../../apps/kuaizhizao/pages/warehouse-management/outbound/components/OutboundDetailDrawer';
import { mapOutsourceIssueToOutbound } from '../../../apps/kuaizhizao/pages/warehouse-management/outbound/outboundHubTypes';
import { warehouseApi, outsourceMaterialIssueApi } from '../../../apps/kuaizhizao/services/production';

export type HubOutboundLinkedDetailDrawerProps = {
  open: boolean;
  documentType: 'production_picking' | 'outsource_issue' | 'purchase_return';
  documentId: number;
  onClose: () => void;
  zIndex?: number;
};

export function HubOutboundLinkedDetailDrawer({
  open,
  documentType,
  documentId,
  onClose,
  zIndex,
}: HubOutboundLinkedDetailDrawerProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [order, setOrder] = useState<OutboundDetailRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    if (!open || documentId <= 0) {
      setOrder(null);
      setLoadError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    setOrder((prev) => (prev?.id === documentId ? prev : null));
    try {
      let detail: OutboundDetailRecord;
      if (documentType === 'production_picking') {
        const raw = (await warehouseApi.productionPicking.get(String(documentId))) as OutboundDetailRecord;
        detail = { ...raw, outbound_type: 'production_picking' };
      } else if (documentType === 'outsource_issue') {
        const raw = await outsourceMaterialIssueApi.get(String(documentId));
        detail = {
          ...mapOutsourceIssueToOutbound(raw as Record<string, unknown>),
          outbound_type: 'outsource_issue',
        } as OutboundDetailRecord;
      } else {
        const raw = (await warehouseApi.purchaseReturn.get(String(documentId))) as OutboundDetailRecord;
        detail = { ...raw, outbound_type: 'purchase_return' };
      }
      setOrder(detail);
    } catch (e: unknown) {
      const err = e as { message?: string; detail?: string };
      const msg =
        err?.message || err?.detail || t('app.kuaizhizao.warehouseOutbound.msg.loadDetailFailed');
      setOrder(null);
      setLoadError(msg);
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [documentId, documentType, message, open, t]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <OutboundDetailDrawer
      open={open}
      onClose={onClose}
      order={order}
      loading={loading}
      error={loadError}
      onRetry={() => setRefreshKey((k) => k + 1)}
      zIndex={zIndex}
      trackingRefreshKey={refreshKey}
    />
  );
}
