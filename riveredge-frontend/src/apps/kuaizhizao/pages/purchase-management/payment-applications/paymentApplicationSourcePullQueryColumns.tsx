/**
 * 付款申请来源取单 UniPullQuery 列（对账单/入库/其他费用/应付等列表与表单共用）
 */
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import { renderPullQueryDocStatus } from '../../../../../components/uni-pull-query';
import { formatBusinessDateOnly, formatCurrencyAmount } from '../../../../../utils/format';

export type PaymentApplicationSourcePullRow = {
  id: number;
  code: string;
  documentDate?: string | null;
  supplierId?: number;
  partnerName?: string;
  amount?: number;
  status?: string;
  pullable?: boolean;
  disableReason?: string;
};

export function buildPaymentApplicationSourcePullQueryColumns(
  t: TFunction,
): ColumnsType<PaymentApplicationSourcePullRow> {
  return [
    { title: t('common.code'), dataIndex: 'code', width: 160, ellipsis: true },
    {
      title: t('components.uniPullQuery.documentDateColumn'),
      dataIndex: 'documentDate',
      width: 112,
      sorter: (a, b) =>
        String(a.documentDate || '').localeCompare(String(b.documentDate || '')),
      defaultSortOrder: 'descend',
      render: (v?: string | null) => (v ? formatBusinessDateOnly(String(v)) : '—'),
    },
    { title: t('app.kuaicaiwu.common.supplier'), dataIndex: 'partnerName', ellipsis: true },
    {
      title: t('app.kuaizhizao.paymentApplication.requestAmount'),
      dataIndex: 'amount',
      width: 120,
      align: 'right',
      render: (v?: number) => (v != null && v > 0 ? formatCurrencyAmount(v) : '—'),
    },
    {
      title: t('common.status'),
      dataIndex: 'status',
      width: 100,
      render: (v) => renderPullQueryDocStatus(t, v),
    },
  ];
}
