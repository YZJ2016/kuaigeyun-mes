/**
 * 付款单「从应付单取单」UniPullQuery 列（列表工具栏与 FormModal 共用）
 */
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import { renderPullQueryReviewStatus } from '../../../../../components/uni-pull-query';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { getStatusDisplay } from '../../../../kuaizhizao/constants/documentStatus';
import type { PaymentPullCandidate } from '../../../services/finance/payment';
import { formatCurrencyAmount, formatDateTime } from '../../../../../utils/format';

const PAYMENT_I18N = 'app.kuaicaiwu.payment';
const PAYABLE_I18N = 'app.kuaicaiwu.payable';

export function buildPaymentPayablePullQueryColumns(
  t: TFunction,
  options?: { includeExpectedPaymentDate?: boolean },
): ColumnsType<PaymentPullCandidate> {
  const columns: ColumnsType<PaymentPullCandidate> = [
    {
      title: t(`${PAYMENT_I18N}.pullCol.payableCode`),
      dataIndex: 'payable_code',
      width: 148,
      ellipsis: true,
      render: (v: unknown, record) => String(v || record.code || '—'),
    },
    {
      title: t('app.kuaicaiwu.common.supplier'),
      dataIndex: 'supplier_name',
      width: 160,
      ellipsis: true,
    },
    {
      title: t(`${PAYMENT_I18N}.pullCol.docStatus`),
      dataIndex: 'source_status',
      width: 100,
      align: 'center',
      render: (v: unknown) => {
        const { text, color } = getStatusDisplay(v);
        return text === '-' ? '—' : <MarkerTag color={color}>{text}</MarkerTag>;
      },
    },
    {
      title: t('app.kuaicaiwu.common.reviewStatus'),
      dataIndex: 'review_status',
      width: 100,
      align: 'center',
      render: (v) => renderPullQueryReviewStatus(t, v),
    },
    {
      title: t('app.kuaicaiwu.common.dueDate'),
      dataIndex: 'source_date',
      width: 112,
      render: (v: unknown) => (v ? formatDateTime(String(v), 'YYYY-MM-DD') : '—'),
    },
    {
      title: t(`${PAYABLE_I18N}.pullCol.docAmount`),
      dataIndex: 'amount',
      width: 120,
      align: 'right',
      render: (v: unknown) => formatCurrencyAmount(v ?? 0),
    },
    {
      title: t(`${PAYABLE_I18N}.col.remainingAmount`),
      dataIndex: 'remaining_amount',
      width: 120,
      align: 'right',
      render: (v: unknown) => formatCurrencyAmount(v ?? 0),
    },
  ];
  if (options?.includeExpectedPaymentDate) {
    columns.splice(5, 0, {
      title: t('app.kuaizhizao.paymentApplication.expectedPaymentDate'),
      dataIndex: 'expected_payment_date',
      width: 120,
      render: (v: unknown) => (v ? formatDateTime(String(v), 'YYYY-MM-DD') : '—'),
    });
  }
  return columns;
}
