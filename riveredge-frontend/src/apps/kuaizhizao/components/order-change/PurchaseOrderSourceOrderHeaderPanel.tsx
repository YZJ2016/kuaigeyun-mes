import React, { useMemo } from 'react';
import { Descriptions, Spin, Typography } from 'antd';
import type { ProDescriptionsItemProps } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { LinkedDocumentCode } from '../../../../components/linked-document-code';
import { useDetailDrawerDescriptionItems } from '../../../../components/layout-templates';
import { AmountDisplay } from '../../../../components/permission';
import { KUAIZHIZAO_PURCHASE_ORDER_FIELD_RESOURCE as PO } from '../../constants/fieldPermissionResources';
import { renderDocumentPaymentMethodDisplay } from '../../components/PaymentMethodWithMixFormItems';
import {
  alignDescriptionColumns,
  GLOBAL_DOC_DETAIL_BASIC_FIELD_RANK,
} from '../../pages/sales-management/shared/documentFieldAlignment';
import { resolvePurchaseOrderDisplayAmount } from '../../pages/purchase-management/shared/purchaseOrderAmounts';
import { resolveDocumentCurrencyInputPrefix } from '../../utils/documentCurrencyDisplay';
import { partnerSettlementTermsLabel } from '../../../master-data/utils/partner-static-labels';
import { formatDateTime, formatQuantity } from '../../../../utils/format';
import type { PurchaseOrder } from '../../services/purchase';
import { renderDocumentStatusTag } from '../../../../utils/documentLifecycleStatusTag';
import { getPurchaseOrderLifecycle } from '../../utils/purchaseOrderLifecycle';
import { useAuditRequired } from '../../../../hooks/useAuditRequired';

export type PurchaseOrderSourceOrderHeaderPanelProps = {
  order: PurchaseOrder | null;
  loading?: boolean;
};

export const PurchaseOrderSourceOrderHeaderPanel: React.FC<PurchaseOrderSourceOrderHeaderPanelProps> = ({
  order,
  loading,
}) => {
  const { t } = useTranslation();
  const auditEnabled = useAuditRequired('purchase_order', false);

  const columns = useMemo(
    () =>
      alignDescriptionColumns(
        [
          {
            title: t('app.kuaizhizao.purchaseOrder.col.orderCode'),
            dataIndex: 'order_code',
            render: (_, record) =>
              record.id && record.order_code ? (
                <LinkedDocumentCode
                  documentType="purchase_order"
                  documentId={record.id}
                  code={record.order_code}
                />
              ) : (
                record.order_code || '—'
              ),
          },
          {
            title: t('app.kuaizhizao.purchaseOrder.col.orderDate'),
            dataIndex: 'order_date',
            render: (_, record) =>
              record.order_date ? formatDateTime(record.order_date, 'YYYY-MM-DD') : '—',
          },
          {
            title: t('app.kuaizhizao.purchaseOrder.col.deliveryDate'),
            dataIndex: 'delivery_date',
            render: (_, record) =>
              record.delivery_date ? formatDateTime(record.delivery_date, 'YYYY-MM-DD') : '—',
          },
          { title: t('app.kuaizhizao.purchaseOrder.col.supplier'), dataIndex: 'supplier_name' },
          { title: t('app.kuaizhizao.purchaseOrder.col.buyer'), dataIndex: 'buyer_name' },
          {
            title: t('common.status'),
            dataIndex: 'status',
            render: (_, record) => {
              const lifecycle = getPurchaseOrderLifecycle(record, auditEnabled, t);
              return renderDocumentStatusTag(lifecycle.currentStageName, lifecycle.currentStageCode);
            },
          },
          {
            title: t('app.kuaizhizao.purchaseOrder.paymentMethod'),
            dataIndex: 'payment_method_code',
            render: (_, record) =>
              renderDocumentPaymentMethodDisplay(
                t,
                record as Parameters<typeof renderDocumentPaymentMethodDisplay>[1],
              ),
          },
          {
            title: t('app.kuaizhizao.purchaseOrder.settlementTerms'),
            dataIndex: 'settlement_terms_code',
            render: (_, record) =>
              partnerSettlementTermsLabel(t, record.settlement_terms_code) ||
              record.settlement_terms_code ||
              '—',
          },
          {
            title: t('app.kuaizhizao.purchaseOrder.col.totalQuantity'),
            dataIndex: 'total_quantity',
            render: (_, record) =>
              record.total_quantity != null ? formatQuantity(record.total_quantity) : '—',
          },
          {
            title: t('app.kuaizhizao.purchaseOrder.col.orderAmount'),
            dataIndex: 'net_amount',
            render: (_, record) => {
              const prefix = resolveDocumentCurrencyInputPrefix(record.currency);
              return (
                <AmountDisplay
                  resource={PO}
                  fieldName="net_amount"
                  value={resolvePurchaseOrderDisplayAmount(record)}
                  prefix={prefix}
                />
              );
            },
          },
          { title: t('common.remark'), dataIndex: 'notes', span: 3 },
        ] as ProDescriptionsItemProps<PurchaseOrder>[],
        GLOBAL_DOC_DETAIL_BASIC_FIELD_RANK,
      ),
    [auditEnabled, t],
  );

  const descriptionItems = useDetailDrawerDescriptionItems(columns, order ?? undefined, 'purchase_order');

  return (
    <div style={{ marginBottom: 20 }}>
      <Typography.Text strong style={{ display: 'block', marginBottom: 12 }}>
        {t('app.kuaizhizao.purchaseOrderChange.sourceOrderHeaderTitle')}
      </Typography.Text>
      <Spin spinning={Boolean(loading && !order)}>
        {order ? (
          <Descriptions column={3} size="small" bordered items={descriptionItems} />
        ) : loading ? (
          <div style={{ minHeight: 88 }} />
        ) : (
          <Typography.Text type="secondary">
            {t('app.kuaizhizao.purchaseOrderChange.sourceOrderMissing')}
          </Typography.Text>
        )}
      </Spin>
    </div>
  );
};