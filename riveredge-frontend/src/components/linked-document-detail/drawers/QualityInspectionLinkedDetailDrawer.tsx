/**
 * 关联单据：来料 / 成品检验 → QualityInspectionDetailDrawer
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { App } from 'antd';
import type { ProDescriptionsItemProps } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { QualityInspectionDetailDrawer } from '../../../apps/kuaizhizao/pages/quality-management/components/QualityInspectionDetailDrawer';
import {
  buildQualityInspectionDetailCodeColumn,
  buildQualityInspectionDetailMaterialColumns,
  buildQualityInspectionDetailNotesColumn,
  buildQualityInspectionDetailPeopleColumns,
  buildQualityInspectionDetailQuantityStatusColumns,
} from '../../../apps/kuaizhizao/pages/quality-management/components/qualityDetailColumns';
import { renderQualityInspectionPlanSummary } from '../../../apps/kuaizhizao/pages/quality-management/components/QualityInspectionDetailSupplement';
import { qualityApi } from '../../../apps/kuaizhizao/services/quality-execution';
import { useDocumentTracking } from '../../document-tracking-panel';

export type QualityInspectionLinkedDetailDrawerProps = {
  open: boolean;
  documentType: 'incoming_inspection' | 'finished_goods_inspection';
  documentId: number;
  onClose: () => void;
  zIndex?: number;
};

export function QualityInspectionLinkedDetailDrawer({
  open,
  documentType,
  documentId,
  onClose,
  zIndex,
}: QualityInspectionLinkedDetailDrawerProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [inspection, setInspection] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const tracking = useDocumentTracking(
    open && inspection?.id ? documentType : undefined,
    Number(inspection?.id),
    refreshKey,
  );

  const load = useCallback(async () => {
    if (!open || documentId <= 0) {
      setInspection(null);
      setLoadError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    setInspection((prev) => (Number(prev?.id) === documentId ? prev : null));
    try {
      const detail =
        documentType === 'incoming_inspection'
          ? await qualityApi.incomingInspection.get(String(documentId))
          : await qualityApi.finishedGoodsInspection.get(String(documentId));
      setInspection(detail as Record<string, unknown>);
    } catch (e: unknown) {
      const err = e as { message?: string; detail?: string };
      const msg = err?.message || err?.detail || t('app.kuaizhizao.quality.common.messages.loadDetailFailed');
      setInspection(null);
      setLoadError(msg);
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [documentId, documentType, message, open, t]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const basicColumns = useMemo((): ProDescriptionsItemProps<Record<string, unknown>>[] => {
    const common = [
      buildQualityInspectionDetailCodeColumn<Record<string, unknown>>(t),
      {
        title: t('app.kuaizhizao.quality.common.columns.inspectionKind'),
        key: 'inspection_plan_summary',
        render: (_, row) => renderQualityInspectionPlanSummary(row, t),
      },
      ...buildQualityInspectionDetailMaterialColumns<Record<string, unknown>>(t),
      ...buildQualityInspectionDetailQuantityStatusColumns<Record<string, unknown>>(t),
      ...buildQualityInspectionDetailPeopleColumns<Record<string, unknown>>(t),
      buildQualityInspectionDetailNotesColumn<Record<string, unknown>>(t),
    ];
    if (documentType === 'incoming_inspection') {
      return [
        ...common.slice(0, 3),
        {
          title: t('app.kuaizhizao.quality.common.columns.purchaseReceiptCode'),
          dataIndex: 'purchase_receipt_code',
        },
        { title: t('app.kuaizhizao.quality.common.columns.supplier'), dataIndex: 'supplier_name' },
        ...common.slice(3),
      ];
    }
    return [
      ...common.slice(0, 3),
      { title: t('app.kuaizhizao.workOrder.code'), dataIndex: 'work_order_code' },
      ...common.slice(3),
    ];
  }, [documentType, t]);

  const title = t('app.kuaizhizao.quality.common.modal.detailTitle', {
    code: String(inspection?.inspection_code ?? ''),
  });

  return (
    <QualityInspectionDetailDrawer
      open={open}
      onClose={onClose}
      title={title}
      inspection={inspection}
      documentType={documentType}
      zIndex={zIndex}
      basicColumns={basicColumns}
      tracking={tracking}
      loading={loading}
      error={loadError}
      onRetry={() => setRefreshKey((k) => k + 1)}
    />
  );
}
