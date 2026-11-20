/**
 * 付款申请「从采购订单取单」UniPullQuery 列（列表新建下拉与 FormModal 共用）
 */
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import { renderPullQueryDocStatus } from '../../../../../components/uni-pull-query';
import { purchaseOrderCapabilityReasonMessage } from '../../../../../hooks/useDocumentCapabilities';
import { formatBusinessDateOnly, formatCurrencyAmount } from '../../../../../utils/format';
import { normalizeUserDisplayName } from '../../../../../utils/userDisplay';
import type { PurchaseOrder } from '../../../services/purchase';
import { resolvePurchaseOrderDisplayAmount } from '../shared/purchaseOrderAmounts';

export type PaymentApplicationPoPullRow = {
  id: number;
  code: string;
  documentDate?: string | null;
  supplierId?: number;
  partnerName?: string;
  departmentName?: string;
  applicantName?: string;
  docAmount?: number;
  amount?: number;
  status?: string;
  pullable?: boolean;
  disableReason?: string;
};

export function buildPaymentApplicationPoPullQueryColumns(
  t: TFunction,
): ColumnsType<PaymentApplicationPoPullRow> {
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
    {
      title: t('app.kuaicaiwu.common.supplier'),
      dataIndex: 'partnerName',
      width: 160,
      ellipsis: true,
    },
    {
      title: t('app.kuaizhizao.purchaseRequisition.col.department'),
      dataIndex: 'departmentName',
      width: 120,
      ellipsis: true,
      render: (v?: string) => (v?.trim() ? v : '—'),
    },
    {
      title: t('app.kuaizhizao.paymentApplication.applicantName'),
      dataIndex: 'applicantName',
      width: 96,
      ellipsis: true,
      render: (v?: string) => (v?.trim() ? v : '—'),
    },
    {
      title: t('app.kuaicaiwu.payable.pullCol.docAmount'),
      dataIndex: 'docAmount',
      width: 120,
      align: 'right',
      render: (v?: number) => (v != null && v > 0 ? formatCurrencyAmount(v) : '—'),
    },
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

export function mapPurchaseOrderToPaymentApplicationPullRow(
  o: PurchaseOrder,
  t: TFunction,
): PaymentApplicationPoPullRow {
  const cap = o.capabilities?.push_payment_application;
  const prepay = Number(o.prepayment_amount ?? 0);
  const orderTotal = resolvePurchaseOrderDisplayAmount(o);
  // 仅展示预付额度，禁止用订单总额冒充可请款（否则「全部单据」上看似有金额却选不了）
  const displayAmount = prepay > 0 ? prepay : undefined;
  const reasonCode = cap?.reason ? String(cap.reason) : '';
  const orderDate = o.order_date ? String(o.order_date).slice(0, 10) : null;
  const departmentName = String(o.department_name ?? '').trim();
  const applicantName =
    normalizeUserDisplayName(o.created_by_name)
    || normalizeUserDisplayName(o.buyer_name);
  return {
    id: Number(o.id),
    code: String(o.order_code ?? o.id),
    documentDate: orderDate,
    supplierId: Number(o.supplier_id ?? 0) || undefined,
    partnerName: String(o.supplier_name ?? ''),
    departmentName: departmentName || undefined,
    applicantName: applicantName || undefined,
    docAmount: orderTotal > 0 ? orderTotal : undefined,
    amount: displayAmount > 0 ? displayAmount : undefined,
    status: String(o.status ?? o.review_status ?? ''),
    pullable: cap?.allowed === true,
    disableReason: reasonCode
      ? purchaseOrderCapabilityReasonMessage(reasonCode, t)
      : t('app.kuaizhizao.paymentApplication.pullFromPoNotSelectable'),
  };
}