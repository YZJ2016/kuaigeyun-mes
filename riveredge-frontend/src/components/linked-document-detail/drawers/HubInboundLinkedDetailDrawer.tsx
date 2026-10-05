/**
 * 关联单据：入库 hub 多类型 → InboundDetailDrawer
 */

import React, { useCallback, useEffect, useState } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  InboundDetailDrawer,
  type InboundDetailRecord,
} from '../../../apps/kuaizhizao/pages/warehouse-management/inbound/components/InboundDetailDrawer';
import {
  warehouseApi,
  outsourceMaterialReceiptApi,
  outsourceMaterialReturnApi,
  outsourceProductReturnApi,
} from '../../../apps/kuaizhizao/services/production';

export type HubInboundLinkedDocumentType =
  | 'finished_goods_receipt'
  | 'production_return'
  | 'purchase_receipt'
  | 'sales_return'
  | 'outsource_receipt'
  | 'outsource_material_return'
  | 'outsource_product_return';

export type HubInboundLinkedDetailDrawerProps = {
  open: boolean;
  documentType: HubInboundLinkedDocumentType;
  documentId: number;
  onClose: () => void;
  zIndex?: number;
};

function mapReceiptType(documentType: HubInboundLinkedDocumentType): InboundDetailRecord['receipt_type'] {
  switch (documentType) {
    case 'finished_goods_receipt':
      return 'finished_goods';
    case 'production_return':
      return 'production_return';
    case 'purchase_receipt':
      return 'purchase';
    case 'sales_return':
      return 'sales_return';
    case 'outsource_receipt':
      return 'outsource_receipt';
    case 'outsource_material_return':
      return 'outsource_material_return';
    case 'outsource_product_return':
      return 'outsource_product_return';
    default:
      return undefined;
  }
}

export function HubInboundLinkedDetailDrawer({
  open,
  documentType,
  documentId,
  onClose,
  zIndex,
}: HubInboundLinkedDetailDrawerProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [order, setOrder] = useState<InboundDetailRecord | null>(null);
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
      let raw: Record<string, unknown>;
      if (documentType === 'finished_goods_receipt') {
        raw = (await warehouseApi.finishedGoodsReceipt.get(String(documentId))) as Record<string, unknown>;
      } else if (documentType === 'production_return') {
        raw = (await warehouseApi.productionReturn.get(String(documentId))) as Record<string, unknown>;
      } else if (documentType === 'purchase_receipt') {
        raw = (await warehouseApi.purchaseReceipt.get(String(documentId))) as Record<string, unknown>;
      } else if (documentType === 'sales_return') {
        raw = (await warehouseApi.salesReturn.get(String(documentId))) as Record<string, unknown>;
      } else if (documentType === 'outsource_receipt') {
        raw = (await outsourceMaterialReceiptApi.get(String(documentId))) as Record<string, unknown>;
      } else if (documentType === 'outsource_material_return') {
        raw = (await outsourceMaterialReturnApi.get(String(documentId))) as Record<string, unknown>;
      } else {
        raw = (await outsourceProductReturnApi.get(String(documentId))) as Record<string, unknown>;
      }
      const receiptType = mapReceiptType(documentType);
      setOrder({ ...raw, receipt_type: receiptType ?? raw.receipt_type } as InboundDetailRecord);
    } catch (e: unknown) {
      const err = e as { message?: string; detail?: string };
      const msg =
        err?.message || err?.detail || t('app.kuaizhizao.warehouseInbound.msg.loadDetailFailed');
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
    <InboundDetailDrawer
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
