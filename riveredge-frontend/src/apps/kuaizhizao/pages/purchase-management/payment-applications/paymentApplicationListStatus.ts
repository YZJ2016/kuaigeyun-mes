import type { PaymentApplication } from '../../../services/payment-application';

export const PAYMENT_APPLICATION_APPROVAL_PHASE_VALUES = [
  'draft',
  'submitted',
  'pending_review',
  'approved',
  'rejected',
] as const;

export const PAYMENT_APPLICATION_SETTLEMENT_VALUES = ['unpaid', 'partial', 'paid'] as const;

export type PaymentApplicationApprovalPhase =
  (typeof PAYMENT_APPLICATION_APPROVAL_PHASE_VALUES)[number];

export type PaymentApplicationSettlement =
  (typeof PAYMENT_APPLICATION_SETTLEMENT_VALUES)[number];

/** 列表「审批状态」展示（与付款进度解耦，已付款仍显示已批准） */
export function resolvePaymentApplicationApprovalDisplay(
  record: PaymentApplication,
): { label: string; raw: string } {
  const status = String(record.status ?? '').trim();
  const review = String(record.reviewStatus ?? '').trim().toUpperCase();
  if (status === '已驳回' || review === 'REJECTED') {
    return { label: '已驳回', raw: '已驳回' };
  }
  if (status === '待审核' || review === 'PENDING') {
    return { label: '待审核', raw: '待审核' };
  }
  if (status === '已提交') {
    return { label: '已提交', raw: '已提交' };
  }
  if (
    review === 'APPROVED' ||
    status === '已批准' ||
    status === '部分付款' ||
    status === '已付款'
  ) {
    return { label: '已批准', raw: '已批准' };
  }
  if (status === '草稿' || review === 'DRAFT' || !status) {
    return { label: '草稿', raw: '草稿' };
  }
  return { label: status, raw: status };
}

/** 列表「付款状态」；仅审批通过后有值 */
export function resolvePaymentApplicationSettlementDisplay(
  record: PaymentApplication,
): { label: string; raw: string } | null {
  const status = String(record.status ?? '').trim();
  const review = String(record.reviewStatus ?? '').trim().toUpperCase();
  const approved =
    review === 'APPROVED' || ['已批准', '部分付款', '已付款'].includes(status);
  if (!approved) {
    return null;
  }
  if (status === '已付款') {
    return { label: '已付款', raw: '已付款' };
  }
  if (status === '部分付款') {
    return { label: '部分付款', raw: '部分付款' };
  }
  return { label: '未付款', raw: '未付款' };
}
