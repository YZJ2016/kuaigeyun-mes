/**
 * 采购入库明细表
 */
import React, { useMemo } from 'react';
import { ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import KuaizhizaoReport from '../../../components/KuaizhizaoReport';
import {
  buildDocumentLineAttachmentsReportColumn,
  DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY,
} from '../../../components/documentLineAttachmentsColumns';
import { purchaseOrderStatusEnum, reportDocumentStatusText } from '../../../utils/reportPresentation';

const PurchaseReceiptDetail: React.FC = () => {
  const { t } = useTranslation();
  const columns: ProColumns[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.reports.receiptCode'),
        dataIndex: 'receipt_code',
        width: 150,
      },
      {
        title: t('app.kuaizhizao.reports.receiptDate'),
        dataIndex: 'receipt_date',
        valueType: 'date',
        width: 110,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.supplierCode'),
        dataIndex: 'supplier_code',
        width: 120,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.purchaseReports.colSupplier'),
        dataIndex: 'supplier_name',
        ellipsis: true,
        width: 150,
      },
      {
        title: t('app.kuaizhizao.purchaseReports.colOrderCode'),
        dataIndex: 'purchase_order_code',
        width: 140,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.materialCode'),
        dataIndex: 'material_code',
        width: 120,
      },
      {
        title: t('app.kuaizhizao.reports.materialName'),
        dataIndex: 'material_name',
        ellipsis: true,
        width: 160,
      },
      {
        title: t('app.kuaizhizao.reports.materialSpec'),
        dataIndex: 'material_spec',
        ellipsis: true,
        width: 120,
        hideInSearch: true,
      },
      {
        title: t('common.unit'),
        dataIndex: 'material_unit',
        width: 80,
        minWidth: 80,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.batchNumber'),
        dataIndex: 'batch_number',
        width: 110,
        hideInSearch: true,
      },
      {
        title: t('common.quantity'),
        dataIndex: 'quantity',
        valueType: 'digit',
        width: 90,
        hideInSearch: true,
        align: 'right',
      },
      {
        title: t('app.kuaizhizao.reports.unitPrice'),
        dataIndex: 'unit_price',
        valueType: 'money',
        width: 100,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.amount'),
        dataIndex: 'amount',
        valueType: 'money',
        width: 110,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.payableQuantity'),
        dataIndex: 'payable_quantity',
        width: 90,
        hideInSearch: true,
        align: 'right',
      },
      {
        title: t('app.kuaizhizao.reports.payableAmount'),
        dataIndex: 'payable_amount',
        valueType: 'money',
        width: 110,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.invoicedQuantity'),
        dataIndex: 'invoice_quantity',
        width: 90,
        hideInSearch: true,
        align: 'right',
      },
      {
        title: t('app.kuaizhizao.reports.invoicedAmount'),
        dataIndex: 'invoice_amount',
        valueType: 'money',
        width: 110,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.paidQuantity'),
        dataIndex: 'paid_quantity',
        width: 90,
        hideInSearch: true,
        align: 'right',
      },
      {
        title: t('app.kuaizhizao.reports.paidAmount'),
        dataIndex: 'paid_amount',
        valueType: 'money',
        width: 110,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.warehouse'),
        dataIndex: 'warehouse_name',
        width: 120,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.documentStatus'),
        dataIndex: 'status',
        width: 90,
        hideInSearch: true,
        valueEnum: purchaseOrderStatusEnum(t),
        render: (_, record) => reportDocumentStatusText(t, record.status),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.receiver'),
        dataIndex: 'receiver_name',
        width: 100,
        hideInSearch: true,
      },
      buildDocumentLineAttachmentsReportColumn(
        t,
        DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.purchaseReceipt,
      ),
    ],
    [t],
  );

  return (
    <KuaizhizaoReport
      title={t('app.kuaizhizao.menu.reports.purchase-receipt-detail')}
      reportType="purchase-receipt-detail"
      summaryFields={['quantity', 'amount']}
      columnPersistenceId="apps.kuaizhizao.pages.purchase-management.reports.PurchaseReceiptDetail-v3"
      rowKey="id"
      columns={columns}
    />
  );
};

export default PurchaseReceiptDetail;
