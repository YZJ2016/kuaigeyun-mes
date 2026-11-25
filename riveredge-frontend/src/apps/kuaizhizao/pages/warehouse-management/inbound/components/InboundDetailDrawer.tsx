/**
 * 入库单原版详情抽屉（列表 / 关联嵌套共用）。
 * 单一 DetailDrawerTemplate：加载中遮罩，失败 Result+重试。
 */

import React, { useMemo } from 'react';
import { Alert, Button, Descriptions, Empty, Result, Space, Table, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { ProDescriptionsItemProps } from '@ant-design/pro-components';
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
import {
  formatCurrencyAmount,
  formatDateBySiteSetting,
  formatDateTimeBySiteSetting,
  formatQuantity,
} from '../../../../../../utils/format';
import {
  buildDocumentLineAttachmentsDrawerColumn,
  DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY,
} from '../../../../components/documentLineAttachmentsColumns';
import { partnerDefaultPaymentMethodLabel } from '../../../../../master-data/utils/partner-static-labels';
import {
  KUAIZHIZAO_INBOUND_FIELD_RESOURCE,
  renderWarehousePartyNameDisplay,
} from '../../shared/warehouseAmountDisplay';
import { payableLedgerRecognitionLabel } from '../../../../../../utils/documentLedgerRecognition';
import { getInboundLifecycle } from '../../../../utils/inboundLifecycle';
import { renderInboundReceiptTypeMarkerTag } from '../../shared/warehouseMarkerTags';
import { buildPurchaseReceiptDetailFinanceColumns } from '../../shared/warehouseLineDetailColumns';
import {
  inboundDocumentTrackingType,
  resolveInboundHubOperator,
  type InboundHubOrder,
} from '../inboundHubTypes';
import { resolveInboundHubLineQuantity } from '../inboundHubNormalize';

export type InboundDetailRecord = InboundHubOrder & {
  workshop_name?: string;
  notes?: string;
  items?: unknown[];
};

const PLACEHOLDER: InboundDetailRecord = { id: 0 };

function formatInboundDateDisplay(record: InboundDetailRecord): string {
  const dateOnly = record.receipt_date ?? record.registration_date;
  if (dateOnly) return formatDateBySiteSetting(String(dateOnly));
  const timeValue =
    record.receipt_time ?? record.return_time ?? record.received_at ?? record.returned_at;
  if (timeValue) return formatDateTimeBySiteSetting(String(timeValue));
  return '-';
}

export type InboundDetailDrawerProps = {
  open: boolean;
  onClose: () => void;
  order: InboundDetailRecord | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  zIndex?: number;
  trackingRefreshKey?: number;
  extra?: React.ReactNode;
  supplementary?: React.ReactNode;
  lines?: React.ReactNode;
  linesTitle?: string;
  timeline?: React.ReactNode;
  traceDocument?: React.ComponentProps<typeof DetailDrawerTemplate>['traceDocument'];
  showReadonlyActions?: boolean;
  editMode?: boolean;
  /** 目标「是否推送」关闭时隐藏外推状态与时间线中的外推记录 */
  showExternalPushRecords?: boolean;
};

export const InboundDetailDrawer: React.FC<InboundDetailDrawerProps> = ({
  open,
  onClose,
  order,
  loading = false,
  error = null,
  onRetry,
  zIndex,
  trackingRefreshKey = 0,
  extra,
  supplementary,
  lines,
  linesTitle,
  timeline,
  traceDocument,
  editMode = false,
  showExternalPushRecords = true,
}) => {
  const { t } = useTranslation();

  const contentReady = Boolean(order);
  const showError = Boolean(error) && !contentReady && !loading;
  const showLoading = loading || (!contentReady && !showError);
  const effective = order ?? PLACEHOLDER;
  const trackingType = inboundDocumentTrackingType(effective);
  const tracking = useDocumentTracking(
    open && contentReady ? trackingType : undefined,
    effective.id,
    trackingRefreshKey,
  );

  const lifecycle = useMemo(
    () => (contentReady ? getInboundLifecycle(effective as Record<string, unknown>, t) : null),
    [contentReady, effective, t],
  );
  const nextSteps = lifecycle?.nextStepSuggestions;

  const code = String(effective.receipt_code || effective.return_code || '').trim();
  const title = editMode
    ? `${t('common.edit')}${code ? ` - ${code}` : ''}`
    : `${
        effective.receipt_type === 'production_return'
          ? t('app.kuaizhizao.warehouseInbound.detail.productionReturnTitle')
          : t('app.kuaizhizao.warehouseInbound.detail.title')
      }${code ? ` - ${code}` : ''}`;

  const basicColumns = useMemo(
    () =>
      alignDescriptionColumns([
        {
          title: t('app.kuaizhizao.warehouseInbound.col.docNo'),
          dataIndex: 'receipt_code',
          render: (_, record) => {
            const display = String(record.receipt_code || record.return_code || '').trim();
            return (
              <Typography.Text copyable={display ? { text: display } : undefined}>
                {display || '-'}
              </Typography.Text>
            );
          },
        },
        {
          title: t('app.kuaizhizao.warehouse.field.kingdeeBillNo'),
          key: 'kingdee_bill_no',
          dataIndex: 'kingdee_bill_no',
          render: (_, record) => {
            const display = String(record.kingdee_bill_no || '').trim();
            return display ? (
              <Typography.Text copyable={{ text: display }}>{display}</Typography.Text>
            ) : (
              '—'
            );
          },
        },
        {
          title: t('app.kuaizhizao.warehouseInbound.field.type'),
          dataIndex: 'receipt_type',
          render: (_, record) => renderInboundReceiptTypeMarkerTag(t, record.receipt_type),
        },
        ...(effective.customer_name
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.col.customer'),
                dataIndex: 'customer_name' as const,
                render: (_: unknown, record: InboundDetailRecord) =>
                  renderWarehousePartyNameDisplay(
                    record.customer_name,
                    KUAIZHIZAO_INBOUND_FIELD_RESOURCE,
                    'customer_name',
                  ),
              },
            ]
          : []),
        ...(effective.supplier_name
          ? [
              {
                title:
                  effective.receipt_type === 'outsource_receipt'
                    ? t('app.kuaizhizao.warehouseInbound.field.outsourceSupplier')
                    : t('app.kuaizhizao.warehouseInbound.field.supplier'),
                dataIndex: 'supplier_name' as const,
                render: (_: unknown, record: InboundDetailRecord) =>
                  renderWarehousePartyNameDisplay(
                    record.supplier_name,
                    KUAIZHIZAO_INBOUND_FIELD_RESOURCE,
                    'supplier_name',
                  ),
              },
            ]
          : []),
        ...(effective.outsource_work_order_code
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.outsourceWoCode'),
                dataIndex: 'outsource_work_order_code' as const,
              },
            ]
          : []),
        ...(effective.purchase_order_code
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.purchaseOrderCode'),
                dataIndex: 'purchase_order_code' as const,
              },
            ]
          : []),
        ...(effective.work_order_code
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.workOrderCode'),
                dataIndex: 'work_order_code' as const,
                key: 'linked_work_order_code',
              },
            ]
          : []),
        ...(effective.picking_code
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.pickingCode'),
                dataIndex: 'picking_code' as const,
                key: 'linked_picking_code',
              },
            ]
          : []),
        ...(effective.workshop_name
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.workshop'),
                dataIndex: 'workshop_name' as const,
              },
            ]
          : []),
        {
          title: t('app.kuaizhizao.warehouseInbound.field.warehouse'),
          dataIndex: 'warehouse_name',
        },
        {
          title: t('app.kuaizhizao.warehouseInbound.field.date'),
          dataIndex: 'receipt_date',
          render: (_, record) => formatInboundDateDisplay(record),
        },
        {
          title: t('app.kuaizhizao.warehouseInbound.field.operator'),
          dataIndex: 'operator_name',
          render: (_, record) => resolveInboundHubOperator(record) || '-',
        },
        ...(effective.receipt_type === 'purchase'
          ? [
              {
                title: t('app.kuaizhizao.purchaseReceipt.field.orderType'),
                key: 'purchase_receipt_order_type',
                render: (_: unknown, record: InboundDetailRecord) => {
                  const raw = String(
                    (record as { order_type?: string }).order_type ?? '标准采购',
                  ).trim();
                  if (raw === '资产采购') {
                    return t('app.kuaizhizao.purchaseReceipt.orderTypeAsset');
                  }
                  return t('app.kuaizhizao.purchaseReceipt.orderTypeStandard');
                },
              },
              {
                title: t('field.document.ledgerRecognition'),
                key: 'payable_recognition',
                render: (_: unknown, record: InboundDetailRecord) =>
                  payableLedgerRecognitionLabel(
                    t,
                    (record as { payable_recognition?: string; payableRecognition?: string })
                      .payable_recognition ??
                      (record as { payableRecognition?: string }).payableRecognition,
                  ),
              },
              {
                title: t('app.kuaizhizao.purchaseOrder.col.exclAmount'),
                key: 'purchase_receipt_excl',
                render: (_: unknown, record: InboundDetailRecord) =>
                  formatCurrencyAmount(
                    (record as { total_amount?: number }).total_amount ?? 0,
                  ),
              },
              {
                title: t('app.kuaizhizao.purchaseOrder.col.inclTotal'),
                key: 'purchase_receipt_incl',
                render: (_: unknown, record: InboundDetailRecord) =>
                  formatCurrencyAmount(
                    (record as { net_amount?: number; total_amount?: number }).net_amount ??
                      (record as { total_amount?: number }).total_amount ??
                      0,
                  ),
              },
            ]
          : []),
        ...(effective.receipt_type === 'purchase' && effective.buyer_name
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.buyer'),
                dataIndex: 'buyer_name' as const,
              },
            ]
          : []),
        ...(effective.receipt_type === 'purchase' && effective.receiver_name
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.acceptor'),
                dataIndex: 'receiver_name' as const,
              },
            ]
          : []),
        ...(effective.receipt_type === 'purchase' && effective.pay_mode
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.payMode'),
                dataIndex: 'pay_mode' as const,
                render: (_: unknown, record: InboundDetailRecord) => {
                  const raw = String(record.pay_mode || '').trim();
                  if (!raw) return '-';
                  const upper = raw.toUpperCase();
                  // 历史金蝶值：仅展示，新建已改为客商付款方式码
                  if (upper === 'CREDIT') return t('app.kuaizhizao.warehouseInbound.payMode.credit');
                  if (upper === 'CASH') {
                    return partnerDefaultPaymentMethodLabel(t, 'cash');
                  }
                  return partnerDefaultPaymentMethodLabel(t, raw);
                },
              },
            ]
          : []),
        ...(effective.receipt_type === 'purchase' &&
        String(effective.pay_mode ?? '') === 'employee_advance' &&
        String((effective as { advance_payee_name?: string }).advance_payee_name ?? '').trim()
          ? [
              {
                title: t('app.kuaicaiwu.payment.advancePayee'),
                dataIndex: 'advance_payee_name' as const,
              },
            ]
          : []),
        ...(effective.receipt_type === 'purchase' && effective.tax_rate != null
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.taxRate'),
                dataIndex: 'tax_rate' as const,
                render: (_: unknown, record: InboundDetailRecord) =>
                  record.tax_rate != null ? `${record.tax_rate}%` : '-',
              },
            ]
          : []),
        ...(effective.receipt_type === 'purchase' && effective.currency
          ? [
              {
                title: t('app.kuaizhizao.warehouseInbound.field.currency'),
                dataIndex: 'currency' as const,
              },
            ]
          : []),
        ...(effective.notes
          ? [
              {
                title: t('common.remark'),
                dataIndex: 'notes' as const,
                span: 3,
              },
            ]
          : []),
      ] as ProDescriptionsItemProps<InboundDetailRecord>[]),
    [
      effective.buyer_name,
      effective.currency,
      effective.customer_name,
      effective.notes,
      effective.outsource_work_order_code,
      effective.pay_mode,
      effective.picking_code,
      effective.purchase_order_code,
      effective.receipt_type,
      effective.receiver_name,
      effective.supplier_name,
      effective.tax_rate,
      effective.work_order_code,
      effective.workshop_name,
      t,
    ],
  );

  const defaultLinesTitle =
    effective.receipt_type === 'production_return'
      ? t('app.kuaizhizao.warehouseInbound.section.returnDetails')
      : t('app.kuaizhizao.warehouseInbound.section.detailInfo');

  const items = (Array.isArray(effective.items) ? effective.items : []) as Array<Record<string, unknown>>;

  const defaultLines = (
    <>
      <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
      {items.length > 0 ? (
        <Table
          className="warehouse-detail-table"
          size="small"
          rowKey={(r, idx) => String(r.id ?? r.material_id ?? idx)}
          pagination={false}
          scroll={{ x: effective.receipt_type === 'purchase' ? 1420 : 900 }}
          dataSource={items}
          columns={[
            {
              title: t('app.kuaizhizao.warehouseInbound.col.materialCode'),
              dataIndex: 'material_code',
              width: 120,
            },
            {
              title: t('app.kuaizhizao.warehouseInbound.col.materialName'),
              dataIndex: 'material_name',
              width: 150,
            },
            {
              title: t('app.kuaizhizao.warehouseInbound.col.spec'),
              dataIndex: 'material_spec',
              width: 120,
              ellipsis: true,
              render: (v) => (v != null && String(v).trim() ? String(v) : '—'),
            },
            {
              title: t('app.kuaizhizao.warehouseInbound.col.model'),
              dataIndex: 'material_model',
              width: 100,
              ellipsis: true,
              render: (v) => (v != null && String(v).trim() ? String(v) : '—'),
            },
            {
              title: t('app.kuaizhizao.warehouseInbound.col.actualQty'),
              dataIndex: 'receipt_quantity',
              width: 100,
              align: 'right',
              render: (v, row) =>
                formatQuantity(
                  resolveInboundHubLineQuantity(row as Record<string, unknown>) ?? v ?? undefined,
                ),
            },
            {
              title: t('common.unit'),
              dataIndex: 'material_unit',
              width: 60,
              render: (v, row) => String(v ?? row.unit ?? '-'),
            },
            {
              title: t('app.kuaizhizao.warehouseInbound.col.batchNo'),
              dataIndex: 'batch_number',
              width: 100,
              render: (v) => (v != null && String(v).trim() ? String(v) : '—'),
            },
            ...(effective.receipt_type === 'purchase'
              ? buildPurchaseReceiptDetailFinanceColumns(
                  t,
                  (effective as { tax_rate?: number }).tax_rate ?? null,
                )
              : []),
            ...(effective.receipt_type === 'purchase'
              ? [
                  buildDocumentLineAttachmentsDrawerColumn(
                    t,
                    DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.purchaseReceipt,
                  ),
                ]
              : []),
          ]}
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('app.kuaizhizao.warehouseInbound.detail.noDetails')}
        />
      )}
    </>
  );

  const externalPushRows = useMemo(() => {
    const timeline = Array.isArray(tracking.data?.timeline) ? tracking.data.timeline : [];
    const rows: Array<{
      key: string;
      targetType: string;
      targetCode: string;
      at?: string;
      auto?: boolean;
      repush?: boolean;
    }> = [];
    for (const item of timeline) {
      if (item?.type !== 'push') continue;
      const targetType = String(item.target_type || '').trim();
      if (!targetType) continue;
      // 只展示外部系统外推（金蝶等），应付等业务下推仍看操作记录
      if (!targetType.startsWith('kingdee_') && !targetType.includes('oa_') && targetType !== 'feishu_im_notify') {
        continue;
      }
      const targetCode = String(item.target_code || item.target_id || '').trim();
      rows.push({
        key: `${targetType}:${targetCode}:${item.at || rows.length}`,
        targetType,
        targetCode,
        at: item.at ? String(item.at) : undefined,
        auto: Boolean(item.is_auto_created),
        repush: Boolean(item.is_repush) || String(item.relation_desc || '').includes('二次推送'),
      });
    }
    return rows;
  }, [tracking.data]);

  const pushStatusBlock =
    showExternalPushRecords && contentReady && effective.receipt_type === 'purchase' ? (
      <Alert
        type={externalPushRows.length ? 'success' : 'info'}
        showIcon
        style={{ marginBottom: 12 }}
        title={t('app.kuaizhizao.warehouseInbound.detail.externalPushStatus')}
        description={
          externalPushRows.length ? (
            <Space orientation="vertical" size={4} style={{ width: '100%' }}>
              {externalPushRows.map((row) => (
                <Space key={row.key} wrap size={8}>
                  <Typography.Text>
                    {t(`app.kuaizhizao.documentPush.profile.${row.targetType}`, {
                      defaultValue: t(`components.documentTrackingPanel.docType.${row.targetType}`, {
                        defaultValue: row.targetType,
                      }),
                    })}
                    {row.targetCode ? `（${row.targetCode}）` : ''}
                  </Typography.Text>
                  <Tag color="success">
                    {t('app.kuaizhizao.warehouseInbound.msg.externalPushSuccess')}
                  </Tag>
                  {row.repush ? (
                    <Tag color="orange">{t('components.documentTrackingPanel.repush')}</Tag>
                  ) : null}
                  {row.auto ? (
                    <Tag color="blue">{t('components.documentTrackingPanel.autoGenerated')}</Tag>
                  ) : null}
                </Space>
              ))}
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('app.kuaizhizao.warehouseInbound.detail.externalPushStatusHint')}
              </Typography.Text>
            </Space>
          ) : (
            <Typography.Text type="secondary">
              {t('app.kuaizhizao.warehouseInbound.detail.externalPushNotYet')}
            </Typography.Text>
          )
        }
      />
    ) : null;

  const trackingDataForTimeline = useMemo(() => {
    if (!tracking.data) return tracking.data;
    if (showExternalPushRecords) return tracking.data;
    const timeline = Array.isArray(tracking.data.timeline) ? tracking.data.timeline : [];
    const filtered = timeline.filter((item) => {
      if (item?.type !== 'push') return true;
      const targetType = String(item.target_type || '').trim();
      if (!targetType) return true;
      if (
        targetType.startsWith('kingdee_') ||
        targetType.includes('oa_') ||
        targetType === 'feishu_im_notify'
      ) {
        return false;
      }
      return true;
    });
    return { ...tracking.data, timeline: filtered };
  }, [showExternalPushRecords, tracking.data]);

  const defaultTimeline =
    contentReady && effective.id != null ? (
      <>
        {pushStatusBlock}
        {trackingDataForTimeline && !tracking.loading ? (
          <DocumentTrackingTimelineBody data={trackingDataForTimeline} />
        ) : tracking.error ? (
          <Typography.Text type="danger">{tracking.error}</Typography.Text>
        ) : null}
      </>
    ) : null;

  const defaultTrace =
    contentReady && effective.id != null && trackingType
      ? {
          documentType: trackingType,
          documentId: Number(effective.id),
          selfDocumentId: Number(effective.id),
        }
      : undefined;

  const timeconfigBasicItems = useDetailDrawerDescriptionItems(
    basicColumns, effective,
    'inbound',
  );

  if (!open) return null;

  return (
    <DetailDrawerTemplate
      title={title}
      open={open}
      onClose={onClose}
      size={DRAWER_CONFIG.HALF_WIDTH}
      collaborationPlacement="afterLines"
      zIndex={zIndex}
      loading={showLoading}
      plainBody={
        showError ? (
          <Result
            status="error"
            title={error}
            extra={
              onRetry ? (
                <Button type="primary" onClick={onRetry}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : null
            }
          />
        ) : undefined
      }
      extra={contentReady ? extra ?? null : null}
      collaborationTitleSuffix={
        contentReady && nextSteps?.length ? (
          <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
            {t('common.next')}：
            {nextSteps.join(t('components.uniLifecycle.nextStepSeparator'))}
          </Typography.Text>
        ) : undefined
      }
      collaborationAuditRecord={contentReady ? (effective as Record<string, unknown>) : null}
      basic={
        contentReady ? (
          <Descriptions
            column={detailDrawerBasicColumn(false)}
            size="small"
            items={timeconfigBasicItems}
          />
        ) : showError ? null : (
          <div style={{ minHeight: 80 }} />
        )
      }
      collaboration={
        contentReady && lifecycle && (lifecycle.mainStages ?? []).length > 0 ? (
          <UniLifecycleStepper
            steps={lifecycle.mainStages ?? []}
            status={lifecycle.status}
            showLabels
            nextStepSuggestions={lifecycle.nextStepSuggestions}
            hideNextStepSuggestions
          />
        ) : null
      }
      supplementary={contentReady ? supplementary : undefined}
      linesTitle={linesTitle ?? defaultLinesTitle}
      lines={contentReady ? (lines ?? defaultLines) : undefined}
      timeline={contentReady ? (timeline ?? defaultTimeline) : undefined}
      traceDocument={contentReady ? (traceDocument ?? defaultTrace) : undefined}
    />
  );
};
