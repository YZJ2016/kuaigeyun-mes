/**
 * 付款申请「从应付单取单」UniPullQuery 列（列表新建与 Form 添加明细共用，对齐采购订单取单）
 */
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import { renderPullQueryDocStatus } from '../../../../../components/uni-pull-query';
import { formatBusinessDateOnly, formatCurrencyAmount } from '../../../../../utils/format';
import { normalizeUserDisplayName } from '../../../../../utils/userDisplay';

export type PaymentApplicationPayablePullRow = {
  id: number;
  code: string;
  documentDate?: string | null;
  partnerName?: string;
  departmentName?: string;
  applicantName?: string;
  docAmount?: number;
  amount?: number;
  status?: string;
  pullable?: boolean;
  disableReason?: string;
};

export function buildPaymentApplicationPayablePullQueryColumns(
  t: TFunction,
): ColumnsType<PaymentApplicationPayablePullRow> {
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

export function mapPayablePullLineToPaymentApplicationPayableRow(
  row: Record<string, unknown>,
  disableReason: string,
): PaymentApplicationPayablePullRow {
  const payableId = Number(row.payable_id);
  const maxAmt = Number(row.max_request_amount ?? 0);
  const totalAmt = Number(row.total_amount ?? 0);
  const businessDate = row.business_date ?? row.due_date;
  const departmentName = String(row.department_name ?? '').trim();
  const applicantName =
    normalizeUserDisplayName(row.applicant_name)
    || String(row.applicant_name ?? '').trim();
  return {
    id: payableId,
    code: String(row.payable_code ?? payableId),
    documentDate: businessDate ? String(businessDate).slice(0, 10) : null,
    partnerName: String(row.supplier_name ?? ''),
    departmentName: departmentName || undefined,
    applicantName: applicantName || undefined,
    docAmount: totalAmt > 0 ? totalAmt : undefined,
    amount: maxAmt > 0 ? maxAmt : undefined,
    status: String(row.status ?? ''),
    pullable: payableId > 0 && maxAmt > 0,
    disableReason,
  };
}