import React, { useMemo } from 'react';
import { Descriptions, Spin, Typography } from 'antd';
import type { ProDescriptionsItemProps } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { LinkedDocumentCode } from '../../../../components/linked-document-code';
import { useDetailDrawerDescriptionItems } from '../../../../components/layout-templates';
import { AmountDisplay } from '../../../../components/permission';
import { KUAIZHIZAO_SALES_ORDER_FIELD_RESOURCE as SO } from '../../constants/fieldPermissionResources';
import { alignDescriptionColumns } from '../../pages/sales-management/shared/documentFieldAlignment';
import { resolveSalesOrderDisplayTotalAmount } from '../../utils/documentLineAmounts';
import { resolveDocumentCurrencyInputPrefix } from '../../utils/documentCurrencyDisplay';
import { partnerDefaultPaymentMethodLabel, partnerSettlementTermsLabel } from '../../../master-data/utils/partner-static-labels';
import { formatDateTime, formatQuantity } from '../../../../utils/format';
import type { SalesOrder } from '../../services/sales-order';
import { renderDocumentStatusTag } from '../../../../utils/documentLifecycleStatusTag';
import { getSalesOrderLifecycle } from '../../utils/salesOrderLifecycle';
import { useAuditRequired } from '../../../../hooks/useAuditRequired';

export type SalesOrderSourceOrderHeaderPanelProps = {
  order: SalesOrder | null;
  loading?: boolean;
};

export const SalesOrderSourceOrderHeaderPanel: React.FC<SalesOrderSourceOrderHeaderPanelProps> = ({
  order,
  loading,
}) => {
  const { t } = useTranslation();
  const auditEnabled = useAuditRequired('kuaizhizao', 'sales-order');

  const columns = useMemo(
    () =>
      alignDescriptionColumns<SalesOrder>([
        {
          title: t('app.kuaizhizao.salesOrder.orderCode'),
          dataIndex: 'order_code',
          render: (_, record) =>
            record.id && record.order_code ? (
              <LinkedDocumentCode
                documentType="sales_order"
                documentId={record.id}
                code={record.order_code}
              />
            ) : (
              record.order_code || '—'
            ),
        },
        {
          title: t('app.kuaizhizao.salesOrder.orderDate'),
          dataIndex: 'order_date',
          render: (_, record) =>
            record.order_date ? formatDateTime(record.order_date, 'YYYY-MM-DD') : '—',
        },
        {
          title: t('app.kuaizhizao.salesOrder.deliveryDate'),
          dataIndex: 'delivery_date',
          render: (_, record) =>
            record.delivery_date ? formatDateTime(record.delivery_date, 'YYYY-MM-DD') : '—',
        },
        { title: t('app.kuaizhizao.salesOrder.customerName'), dataIndex: 'customer_name' },
        { title: t('app.kuaizhizao.salesOrder.salesman'), dataIndex: 'salesman_name' },
        {
          title: t('common.status'),
          dataIndex: 'status',
          render: (_, record) => {
            const lifecycle = getSalesOrderLifecycle(record, auditEnabled, t);
            return renderDocumentStatusTag(lifecycle.currentStageName, lifecycle.currentStageCode);
          },
        },
        {
          title: t('app.kuaizhizao.salesOrder.paymentMethod'),
          dataIndex: 'payment_method_code',
          render: (_, record) =>
            partnerDefaultPaymentMethodLabel(t, record.payment_method_code) || record.payment_method_code || '—',
        },
        {
          title: t('app.kuaizhizao.salesOrder.settlementTerms'),
          dataIndex: 'settlement_terms_code',
          render: (_, record) =>
            partnerSettlementTermsLabel(t, record.settlement_terms_code) || record.settlement_terms_code || '—',
        },
        {
          title: t('app.kuaizhizao.salesOrder.totalQuantity'),
          dataIndex: 'total_quantity',
          render: (_, record) =>
            record.total_quantity != null ? formatQuantity(record.total_quantity) : '—',
        },
        {
          title: t('app.kuaizhizao.salesOrder.totalAmountLabel'),
          dataIndex: 'total_amount',
          render: (_, record) => {
            const prefix = resolveDocumentCurrencyInputPrefix(record.currency_code);
            return (
              <AmountDisplay
                resource={SO}
                fieldName="total_amount"
                value={resolveSalesOrderDisplayTotalAmount(record)}
                prefix={prefix}
              />
            );
          },
        },
        { title: t('app.kuaizhizao.salesOrder.shippingAddress'), dataIndex: 'shipping_address', span: 3 },
        { title: t('common.remark'), dataIndex: 'notes', span: 3 },
      ] as ProDescriptionsItemProps<SalesOrder>[]),
    [auditEnabled, t],
  );

  const descriptionItems = useDetailDrawerDescriptionItems(columns, order ?? undefined, 'sales_order');

  return (
    <div style={{ marginBottom: 20 }}>
      <Typography.Text strong style={{ display: 'block', marginBottom: 12 }}>
        {t('app.kuaizhizao.salesOrderChange.sourceOrderHeaderTitle')}
      </Typography.Text>
      <Spin spinning={Boolean(loading && !order)}>
        {order ? (
          <Descriptions column={3} size="small" bordered items={descriptionItems} />
        ) : loading ? (
          <div style={{ minHeight: 88 }} />
        ) : (
          <Typography.Text type="secondary">{t('app.kuaizhizao.salesOrderChange.sourceOrderMissing')}</Typography.Text>
        )}
      </Spin>
    </div>
  );
};