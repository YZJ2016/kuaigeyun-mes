/**
 * 送货单原版详情抽屉（列表 / 关联嵌套共用）。
 */

import React, { useMemo } from 'react';
import { Descriptions, Empty, Result, Spin, Table, Tag, Typography } from 'antd';
import type { ProDescriptionsItemProps } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import {
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  WAREHOUSE_DETAIL_TABLE_STYLES,
  detailDrawerBasicColumn,
  useDetailDrawerDescriptionItems,
} from '../../../../../../components/layout-templates';
import { UniLifecycleStepper } from '../../../../../../components/uni-lifecycle';
import { DocumentTrackingTimelineBody, useDocumentTracking } from '../../../../../../components/document-tracking-panel';
import { alignDescriptionColumns } from '../../../sales-management/shared/documentFieldAlignment';
import { formatQuantity } from '../../../../../../utils/format';
import { getDeliveryNoticeLifecycle } from '../../../../utils/deliveryNoticeLifecycle';

export type DeliveryNoticeDetailRecord = {
  id?: number;
  notice_code?: string;
  sales_delivery_id?: number;
  sales_delivery_code?: string;
  sales_order_id?: number;
  sales_order_code?: string;
  customer_id?: number;
  customer_name?: string;
  customer_contact?: string;
  customer_phone?: string;
  planned_delivery_date?: string;
  carrier?: string;
  tracking_number?: string;
  shipping_address?: string;
  status?: string;
  sent_at?: string;
  notes?: string;
  items?: Array<{
    id?: number;
    material_code?: string;
    material_name?: string;
    material_unit?: string;
    notice_quantity?: number;
    unit_price?: number;
    total_amount?: number;
  }>;
};

const STATUS_MAP: Record<string, { text: string; color: string }> = {
  待发送: { text: '待发送', color: 'default' },
  已发送: { text: '已发送', color: 'processing' },
  已签收: { text: '已签收', color: 'success' },
};

export type DeliveryNoticeDetailDrawerProps = {
  open: boolean;
  onClose: () => void;
  notice: DeliveryNoticeDetailRecord | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  zIndex?: number;
  trackingRefreshKey?: number;
  extra?: React.ReactNode;
  collaboration?: React.ReactNode;
};

export const DeliveryNoticeDetailDrawer: React.FC<DeliveryNoticeDetailDrawerProps> = ({
  open,
  onClose,
  notice,
  loading = false,
  error = null,
  onRetry,
  zIndex,
  trackingRefreshKey = 0,
  extra,
  collaboration: collaborationOverride,
}) => {
  const { t } = useTranslation();
  const contentReady = Boolean(notice?.id);
  const showError = Boolean(error) && !contentReady && !loading;
  const showLoading = loading || (!contentReady && !showError);

  const deliveryTracking = useDocumentTracking(
    open && contentReady ? 'delivery_notice' : undefined,
    notice?.id,
    trackingRefreshKey,
  );

  const detailColumns = useMemo(
    () =>
      alignDescriptionColumns([
        { title: t('app.kuaizhizao.deliveryNote.col.noticeCode'), dataIndex: 'notice_code' },
        {
          title: t('app.kuaizhizao.deliveryNote.col.salesDeliveryCode'),
          dataIndex: 'sales_delivery_code',
        },
        {
          title: t('app.kuaizhizao.deliveryNote.col.salesOrderCode'),
          dataIndex: 'sales_order_code',
        },
        { title: t('app.kuaizhizao.deliveryNote.field.customer'), dataIndex: 'customer_name' },
        { title: t('app.kuaizhizao.deliveryNote.field.contact'), dataIndex: 'customer_contact' },
        { title: t('app.kuaizhizao.deliveryNote.field.phone'), dataIndex: 'customer_phone' },
        {
          title: t('app.kuaizhizao.deliveryNote.col.plannedDelivery'),
          dataIndex: 'planned_delivery_date',
          valueType: 'date',
        },
        { title: t('app.kuaizhizao.deliveryNote.col.carrier'), dataIndex: 'carrier' },
        { title: t('app.kuaizhizao.deliveryNote.col.trackingNumber'), dataIndex: 'tracking_number' },
        { title: t('app.kuaizhizao.deliveryNote.field.shippingAddress'), dataIndex: 'shipping_address', span: 3 },
        {
          title: t('common.status'),
          dataIndex: 'status',
          render: (s) => {
            const c = STATUS_MAP[(s as string) || ''] || { text: (s as string) || '-', color: 'default' };
            return <Tag color={c.color}>{c.text}</Tag>;
          },
        },
        { title: t('app.kuaizhizao.deliveryNote.col.sentAt'), dataIndex: 'sent_at', valueType: 'dateTime' },
        { title: t('common.remark'), dataIndex: 'notes', span: 3 },
      ] as ProDescriptionsItemProps<DeliveryNoticeDetailRecord>[]),
    [t],
  );

  const detailItemColumns = useMemo(
    () => [
      { title: t('app.kuaizhizao.warehouseOutbound.col.materialCode'), dataIndex: 'material_code', width: 120 },
      { title: t('app.kuaizhizao.warehouseOutbound.col.materialName'), dataIndex: 'material_name', width: 150 },
      { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
      {
        title: t('common.quantity'),
        dataIndex: 'notice_quantity',
        width: 90,
        align: 'right' as const,
        render: formatQuantity,
      },
      { title: t('app.kuaizhizao.warehouseOutbound.field.unitPrice'), dataIndex: 'unit_price', width: 90, align: 'right' as const },
      { title: t('app.kuaizhizao.warehouseOutbound.field.amount'), dataIndex: 'total_amount', width: 100, align: 'right' as const },
    ],
    [t],
  );

  const basicItems = useDetailDrawerDescriptionItems(detailColumns, notice, 'delivery_note');

  const collaboration = useMemo(() => {
    if (collaborationOverride !== undefined) return collaborationOverride;
    if (!notice) return undefined;
    const lc = getDeliveryNoticeLifecycle(notice as Record<string, unknown>, t);
    const mainStages = lc.mainStages ?? [];
    if (mainStages.length === 0) return undefined;
    return (
      <UniLifecycleStepper
        steps={mainStages}
        showLabels
        status={lc.status}
        nextStepSuggestions={lc.nextStepSuggestions}
      />
    );
  }, [collaborationOverride, notice, t]);

  if (showError) {
    return (
      <DetailDrawerTemplate
        title={t('app.kuaizhizao.deliveryNote.detailTitle')}
        open={open}
        onClose={onClose}
        size={DRAWER_CONFIG.HALF_WIDTH}
        zIndex={zIndex}
        plainBody={
          <Result
            status="error"
            title={error}
            extra={
              onRetry ? (
                <Typography.Link onClick={onRetry}>{t('common.retry')}</Typography.Link>
              ) : null
            }
          />
        }
      />
    );
  }

  return (
    <DetailDrawerTemplate
      title={`${t('app.kuaizhizao.deliveryNote.detailTitle')}${notice?.notice_code ? ` - ${notice.notice_code}` : ''}`}
      open={open}
      loading={showLoading}
      onClose={onClose}
      size={DRAWER_CONFIG.HALF_WIDTH}
      zIndex={zIndex}
      extra={extra}
      basic={
        notice ? (
          <Descriptions column={detailDrawerBasicColumn(false)} size="small" items={basicItems} />
        ) : undefined
      }
      collaboration={collaboration}
      linesTitle={t('app.kuaizhizao.deliveryNote.section.lineDetails')}
      lines={
        notice?.items && notice.items.length > 0 ? (
          <>
            <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
            <Table
              className="warehouse-detail-table"
              size="small"
              rowKey={(row: Record<string, unknown>, idx = 0) =>
                String((row as { id?: React.Key }).id ?? `${notice?.id ?? 'dn'}-${idx}`)
              }
              columns={detailItemColumns}
              dataSource={notice.items}
              pagination={false}
            />
          </>
        ) : notice ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.deliveryNote.msg.noLineDetails')} />
        ) : undefined
      }
      timeline={
        notice?.id != null ? (
          <>
            {deliveryTracking.loading && (
              <div style={{ textAlign: 'center', padding: 24 }}>
                <Spin />
              </div>
            )}
            {deliveryTracking.error && !deliveryTracking.loading && (
              <Typography.Text type="danger">{deliveryTracking.error}</Typography.Text>
            )}
            {deliveryTracking.data && !deliveryTracking.loading && (
              <DocumentTrackingTimelineBody data={deliveryTracking.data} />
            )}
            {!deliveryTracking.loading && !deliveryTracking.data && !deliveryTracking.error && (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.deliveryNote.msg.noOperationLog')} />
            )}
          </>
        ) : undefined
      }
      traceDocument={
        notice?.id != null
          ? {
              documentType: 'delivery_notice',
              documentId: notice.id,
              selfDocumentId: notice.id,
            }
          : undefined
      }
    />
  );
};
