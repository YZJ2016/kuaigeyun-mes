/**
 * 预付抵扣「选择预付款付款单」UniPullQuery 列
 */
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { getStatusDisplay } from '../../../../kuaizhizao/constants/documentStatus';
import type { PrepaymentPaymentPullCandidate } from '../../../services/finance/payment';
import { formatCurrencyAmount, formatDateTime } from '../../../../../utils/format';
import { formatPaymentMethod } from '../../../utils/financeSharedOptions';

const P = 'app.kuaicaiwu.payment';

export function buildPrepaymentPaymentPullQueryColumns(
  t: TFunction,
): ColumnsType<PrepaymentPaymentPullCandidate> {
  return [
    {
      title: t(`${P}.pullLines.col.prepaymentCode`),
      dataIndex: 'payment_code',
      width: 132,
      ellipsis: true,
      render: (v: unknown, record) => String(v || record.code || '—'),
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.orderCode'),
      dataIndex: 'purchase_order_code',
      width: 128,
      ellipsis: true,
      render: (v: unknown) => (v ? String(v) : '—'),
    },
    {
      title: t('app.kuaicaiwu.common.supplier'),
      dataIndex: 'supplier_name',
      width: 148,
      ellipsis: true,
    },
    {
      title: t(`${P}.pullCol.docStatus`),
      dataIndex: 'source_status',
      width: 92,
      align: 'center',
      render: (v: unknown, record) => {
        const raw = (v ?? record.status) as string | undefined;
        const { text, color } = getStatusDisplay(raw);
        return text === '-' ? '—' : <MarkerTag color={color}>{text}</MarkerTag>;
      },
    },
    {
      title: t(`${P}.col.paymentDate`),
      dataIndex: 'source_date',
      width: 108,
      render: (v: unknown) => (v ? formatDateTime(String(v), 'YYYY-MM-DD') : '—'),
    },
    {
      title: t(`${P}.col.paymentMethod`),
      dataIndex: 'payment_method',
      width: 96,
      ellipsis: true,
      render: (v: unknown) => formatPaymentMethod(String(v || ''), t),
    },
    {
      title: t(`${P}.col.totalAmount`),
      dataIndex: 'total_amount',
      width: 108,
      align: 'right',
      render: (v: unknown) => formatCurrencyAmount(v ?? 0),
    },
    {
      title: t(`${P}.col.settledAmount`),
      dataIndex: 'settled_amount',
      width: 108,
      align: 'right',
      render: (v: unknown) => formatCurrencyAmount(v ?? 0),
    },
    {
      title: t(`${P}.pullLines.col.unsettledBalance`),
      dataIndex: 'unsettled_amount',
      width: 108,
      align: 'right',
      render: (v: unknown, record) =>
        formatCurrencyAmount(v ?? record.remaining_amount ?? 0),
    },
  ];
}
