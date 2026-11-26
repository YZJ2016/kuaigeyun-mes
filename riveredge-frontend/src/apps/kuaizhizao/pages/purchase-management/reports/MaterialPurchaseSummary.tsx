/**
 * 存货采购汇总
 */
import React, { useMemo } from 'react';
import { ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import KuaizhizaoReport from '../../../components/KuaizhizaoReport';
import { formatQuantity } from '../../../../../utils/format';
import { reportPercent } from '../../../utils/reportPresentation';

const MaterialPurchaseSummary: React.FC = () => {
  const { t } = useTranslation();
  const columns: ProColumns[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.reports.materialCode'),
        dataIndex: 'material_code',
        width: 120,
      },
      {
        title: t('app.kuaizhizao.reports.materialName'),
        dataIndex: 'material_name',
        ellipsis: true,
        width: 180,
      },
      {
        title: t('app.kuaizhizao.reports.materialSpec'),
        dataIndex: 'material_spec',
        ellipsis: true,
        width: 140,
        hideInSearch: true,
      },
      {
        title: t('common.unit'),
        dataIndex: 'unit',
        width: 80,
        minWidth: 80,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.receiptLineCount'),
        dataIndex: 'receipt_count',
        valueType: 'digit',
        width: 90,
        hideInSearch: true,
        align: 'right',
      },
      {
        title: t('app.kuaizhizao.reports.totalQuantity'),
        dataIndex: 'total_quantity',
        width: 110,
        hideInSearch: true,
        align: 'right',
        render: formatQuantity,
      },
      {
        title: t('app.kuaizhizao.reports.totalAmount'),
        dataIndex: 'total_amount',
        valueType: 'money',
        width: 120,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.avgPrice'),
        dataIndex: 'avg_price',
        valueType: 'money',
        width: 100,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.reports.amountShare'),
        dataIndex: 'amount_share',
        width: 90,
        hideInSearch: true,
        align: 'right',
        render: (_, record) => reportPercent(record.amount_share),
      },
    ],
    [t],
  );

  return (
    <KuaizhizaoReport
      title={t('app.kuaizhizao.menu.reports.material-purchase-summary')}
      reportType="material-purchase-summary"
      summaryFields={['total_quantity', 'total_amount']}
      columnPersistenceId="apps.kuaizhizao.pages.purchase-management.reports.MaterialPurchaseSummary-v1"
      rowKey="material_code"
      columns={columns}
    />
  );
};

export default MaterialPurchaseSummary;
