/**
 * Shared select options and display formatters for finance management pages.
 * Backend values remain Chinese; labels are translated via i18n.
 */
import type { TFunction } from 'i18next';

/** 按采购付款常用程度排序（银行转账默认；「其他」垫底） */
const PAYMENT_METHOD_I18N: Record<string, string> = {
  银行转账: 'app.kuaicaiwu.financeUi.paymentMethod.bankTransfer',
  预付抵扣: 'app.kuaicaiwu.financeUi.paymentMethod.prepaymentOffset',
  票据: 'app.kuaicaiwu.financeUi.paymentMethod.note',
  现金: 'app.kuaicaiwu.financeUi.paymentMethod.cash',
  员工垫付: 'app.kuaicaiwu.financeUi.paymentMethod.employeeAdvance',
  在线支付: 'app.kuaicaiwu.financeUi.paymentMethod.online',
  其他: 'app.kuaicaiwu.financeUi.paymentMethod.other',
};

export function getPaymentMethodOptions(t: TFunction) {
  return Object.entries(PAYMENT_METHOD_I18N).map(([value, key]) => ({
    label: t(key),
    value,
  }));
}

export function formatPaymentMethod(value: string | null | undefined, t: TFunction): string {
  if (!value) return '—';
  const key = PAYMENT_METHOD_I18N[value];
  return key ? t(key) : value;
}

/** 与后端收款/付款单 payment_method 存值一致 */
export const BANK_TRANSFER_PAYMENT_METHOD = '银行转账';
export const CASH_PAYMENT_METHOD = '现金';
/** 收/付款方式「票据」：关联应收/应付票据台账（票种在台账内区分） */
export const NOTE_PAYMENT_METHOD = '票据';
/** 用供应商预付余额抵扣应付，无实际出账 */
export const PREPAYMENT_OFFSET_PAYMENT_METHOD = '预付抵扣';
export const EMPLOYEE_ADVANCE_PAYMENT_METHOD = '员工垫付';

export function isEmployeeAdvancePaymentMethod(method: string | null | undefined): boolean {
  return String(method || '').trim() === EMPLOYEE_ADVANCE_PAYMENT_METHOD;
}

export function isPrepaymentOffsetPaymentMethod(method: string | null | undefined): boolean {
  return String(method || '').trim() === PREPAYMENT_OFFSET_PAYMENT_METHOD;
}

/**
 * 付款单列表金额列三态口径（与主流应付一致；不改库存字段，仅展示）：
 * - 预付款：付款总额=实付；已核销空；预付抵扣金额=原 settled；待核销=预付余额
 * - 普通付款（银行/现金/预付抵扣等）：付款总额=实付（预付抵扣无出账时为空）；已核销/待核销照旧；预付抵扣金额空
 */
export function resolvePaymentListDisplayAmounts(record: {
  settlement_type?: string | null;
  payment_method?: string | null;
  total_amount?: number | null;
  settled_amount?: number | null;
  unsettled_amount?: number | null;
}): {
  total_amount: number | null;
  settled_amount: number | null;
  prepayment_deduction_amount: number | null;
  unsettled_amount: number | null;
} {
  const isPrepay = String(record.settlement_type || 'normal') === 'prepayment';
  const isOffset = isPrepaymentOffsetPaymentMethod(record.payment_method);
  const total = Number(record.total_amount ?? 0);
  const settled = Number(record.settled_amount ?? 0);
  const unsettled = Number(record.unsettled_amount ?? 0);
  const finiteOrZero = (n: number) => (Number.isFinite(n) ? n : 0);
  return {
    total_amount: isOffset ? null : finiteOrZero(total),
    settled_amount: isPrepay ? null : finiteOrZero(settled),
    prepayment_deduction_amount: isPrepay ? finiteOrZero(settled) : null,
    unsettled_amount: finiteOrZero(unsettled),
  };
}

/** 按列表展示口径汇总付款金额（合计行 / 筛选全局合计） */
export function sumPaymentListDisplayAmountFields(
  rows: ReadonlyArray<{
    settlement_type?: string | null;
    payment_method?: string | null;
    total_amount?: number | null;
    settled_amount?: number | null;
    unsettled_amount?: number | null;
  }>,
): Record<
  'total_amount' | 'settled_amount' | 'prepayment_deduction_amount' | 'unsettled_amount',
  number
> {
  const out = {
    total_amount: 0,
    settled_amount: 0,
    prepayment_deduction_amount: 0,
    unsettled_amount: 0,
  };
  for (const row of rows) {
    const d = resolvePaymentListDisplayAmounts(row);
    if (d.total_amount != null) out.total_amount += d.total_amount;
    if (d.settled_amount != null) out.settled_amount += d.settled_amount;
    if (d.prepayment_deduction_amount != null) {
      out.prepayment_deduction_amount += d.prepayment_deduction_amount;
    }
    if (d.unsettled_amount != null) out.unsettled_amount += d.unsettled_amount;
  }
  return out;
}

/** 无供应商收款账户信息（预付抵扣/员工垫付） */
export function hidesSupplierPayeeAccount(method: string | null | undefined): boolean {
  return isEmployeeAdvancePaymentMethod(method) || isPrepaymentOffsetPaymentMethod(method);
}

export function isNotePaymentMethod(method: string | null | undefined): boolean {
  return String(method || '').trim() === NOTE_PAYMENT_METHOD;
}

export function isBankTransferPaymentMethod(method: string | null | undefined): boolean {
  return String(method || '').trim() === BANK_TRANSFER_PAYMENT_METHOD;
}

export function isCashPaymentMethod(method: string | null | undefined): boolean {
  return String(method || '').trim() === CASH_PAYMENT_METHOD;
}

/** 银行转账或现金收付款时，入账账户必选 */
export function requiresLedgerAccount(method: string | null | undefined): boolean {
  return (
    isBankTransferPaymentMethod(method)
    || isCashPaymentMethod(method)
    || isEmployeeAdvancePaymentMethod(method)
  );
}

export function assertBankAccountForTransfer(
  paymentMethod: string | null | undefined,
  bankAccountId: unknown,
  t: TFunction,
): void {
  assertBankAccountForPaymentMethod(paymentMethod, bankAccountId, t);
}

export function assertBankAccountForPaymentMethod(
  paymentMethod: string | null | undefined,
  bankAccountId: unknown,
  t: TFunction,
): void {
  const missing = bankAccountId == null || bankAccountId === '';
  if (isBankTransferPaymentMethod(paymentMethod) && missing) {
    throw new Error(t('app.kuaicaiwu.common.bankAccountRequiredForTransfer'));
  }
  if (isCashPaymentMethod(paymentMethod) && missing) {
    throw new Error(t('app.kuaicaiwu.common.bankAccountRequiredForCash'));
  }
  if (isEmployeeAdvancePaymentMethod(paymentMethod) && missing) {
    throw new Error(t('app.kuaicaiwu.payment.advancePayeeAccountRequired'));
  }
}

export function formatBankAccountOptionLabel(account: {
  account_name: string;
  bank_name?: string | null;
  account_number?: string | null;
  account_type?: string | null;
}): string {
  if (String(account.account_type || '').toLowerCase() === 'cash') {
    return String(account.account_name || '').trim();
  }
  return [account.account_name, account.bank_name, account.account_number]
    .map((v) => String(v ?? '').trim())
    .filter(Boolean)
    .join(' ');
}

/** 按收付款方式过滤入账账户：转账→银行，现金→库存现金 */
export function filterBankAccountsForPaymentMethod<T extends { account_type?: string | null }>(
  accounts: T[],
  paymentMethod: string | null | undefined,
): T[] {
  if (isBankTransferPaymentMethod(paymentMethod)) {
    return accounts.filter((a) => String(a.account_type || 'bank').toLowerCase() !== 'cash');
  }
  if (isCashPaymentMethod(paymentMethod)) {
    return accounts.filter((a) => String(a.account_type || '').toLowerCase() === 'cash');
  }
  if (isEmployeeAdvancePaymentMethod(paymentMethod)) {
    return accounts.filter((a) => String(a.account_type || '').toLowerCase() !== 'cash');
  }
  return accounts;
}

export function getReceiptSettlementTypeOptions(t: TFunction) {
  return [
    { label: t('app.kuaicaiwu.receipt.settlementType.normal'), value: 'normal' },
    { label: t('app.kuaicaiwu.receipt.settlementType.prepayment'), value: 'prepayment' },
  ];
}

export function getPaymentSettlementTypeOptions(t: TFunction) {
  return [
    { label: t('app.kuaicaiwu.payment.settlementType.normal'), value: 'normal' },
    { label: t('app.kuaicaiwu.payment.settlementType.prepayment'), value: 'prepayment' },
  ];
}

export function formatReceiptSettlementType(value: string | null | undefined, t: TFunction): string {
  if (value === 'prepayment') return t('app.kuaicaiwu.receipt.settlementType.prepayment');
  return t('app.kuaicaiwu.receipt.settlementType.normal');
}

export function formatPaymentSettlementType(value: string | null | undefined, t: TFunction): string {
  if (value === 'prepayment') return t('app.kuaicaiwu.payment.settlementType.prepayment');
  return t('app.kuaicaiwu.payment.settlementType.normal');
}

export function buildReceivableStatusEnum(t: TFunction) {
  return {
    未收款: { text: t('app.kuaicaiwu.financeStatus.receivable.unpaid') },
    部分收款: { text: t('app.kuaicaiwu.financeStatus.receivable.partial') },
    已结清: { text: t('app.kuaicaiwu.financeStatus.receivable.settled') },
    已冲减: { text: t('app.kuaicaiwu.financeStatus.receivable.offset') },
  };
}

export function buildPayableStatusEnum(t: TFunction) {
  return {
    未付款: { text: t('app.kuaicaiwu.financeStatus.payable.unpaid') },
    部分付款: { text: t('app.kuaicaiwu.financeStatus.payable.partial') },
    已结清: { text: t('app.kuaicaiwu.financeStatus.payable.settled') },
    已冲减: { text: t('app.kuaicaiwu.financeStatus.payable.offset') },
  };
}

export function buildReviewStatusEnum(t: TFunction) {
  return {
    待审核: { text: t('app.kuaicaiwu.financeStatus.review.pending') },
    已审核: { text: t('app.kuaicaiwu.financeStatus.review.approved') },
    已驳回: { text: t('app.kuaicaiwu.financeStatus.review.rejected') },
    通过: { text: t('app.kuaicaiwu.financeStatus.review.approved') },
    驳回: { text: t('app.kuaicaiwu.financeStatus.review.rejected') },
  };
}

export function buildVoucherStatusEnum(t: TFunction) {
  return {
    Draft: { text: t('app.kuaicaiwu.financeStatus.voucher.draft') },
    Confirmed: { text: t('app.kuaicaiwu.financeStatus.voucher.confirmed') },
    Cancelled: { text: t('app.kuaicaiwu.financeStatus.voucher.cancelled') },
  };
}

/** 其他费用收入/支出：含审核态 + 确认过账态 */
export function buildMiscVoucherStatusEnum(t: TFunction) {
  return {
    Draft: { text: t('app.kuaicaiwu.financeStatus.voucher.draft') },
    PendingReview: { text: t('app.kuaicaiwu.financeStatus.review.pending') },
    Approved: { text: t('app.kuaicaiwu.financeStatus.review.approved') },
    Rejected: { text: t('app.kuaicaiwu.financeStatus.review.rejected') },
    Confirmed: { text: t('app.kuaicaiwu.financeStatus.voucher.confirmed') },
    Cancelled: { text: t('app.kuaicaiwu.financeStatus.voucher.cancelled') },
  };
}

export function buildUnifiedInvoiceStatusEnum(t: TFunction) {
  return {
    DRAFT: { text: t('app.kuaicaiwu.financeStatus.unifiedInvoice.draft') },
    CONFIRMED: { text: t('app.kuaicaiwu.financeStatus.unifiedInvoice.confirmed') },
    VERIFIED: { text: t('app.kuaicaiwu.financeStatus.unifiedInvoice.verified') },
    CANCELLED: { text: t('app.kuaicaiwu.financeStatus.unifiedInvoice.cancelled') },
  };
}

const CHINESE_INVOICE_TYPE_I18N: Record<string, string> = {
  增值税专用发票: 'app.kuaicaiwu.salesInvoice.invoiceType.vatSpecial',
  增值税普通发票: 'app.kuaicaiwu.salesInvoice.invoiceType.vatNormal',
  电子发票: 'app.kuaicaiwu.salesInvoice.invoiceType.electronic',
  收据: 'app.kuaicaiwu.salesInvoice.invoiceType.receipt',
  其他: 'app.kuaicaiwu.purchaseInvoice.invoiceType.other',
  VAT_SPECIAL: 'app.kuaicaiwu.invoice.invoiceType.vatSpecial',
  VAT_NORMAL: 'app.kuaicaiwu.invoice.invoiceType.vatNormal',
  ELECTRONIC: 'app.kuaicaiwu.invoice.invoiceType.electronic',
};

export function getChineseInvoiceTypeOptions(t: TFunction, opts?: { includeOther?: boolean; includeReceipt?: boolean }) {
  const base = [
    { label: t('app.kuaicaiwu.salesInvoice.invoiceType.vatSpecial'), value: '增值税专用发票' },
    { label: t('app.kuaicaiwu.salesInvoice.invoiceType.vatNormal'), value: '增值税普通发票' },
    { label: t('app.kuaicaiwu.salesInvoice.invoiceType.electronic'), value: '电子发票' },
  ];
  if (opts?.includeReceipt !== false) {
    base.push({ label: t('app.kuaicaiwu.salesInvoice.invoiceType.receipt'), value: '收据' });
  }
  if (opts?.includeOther) {
    base.push({ label: t('app.kuaicaiwu.purchaseInvoice.invoiceType.other'), value: '其他' });
  }
  return base;
}

export function formatChineseInvoiceType(value: string | null | undefined, t: TFunction): string {
  const raw = String(value ?? '').trim();
  if (!raw) return '—';
  const key = CHINESE_INVOICE_TYPE_I18N[raw];
  return key ? t(key) : raw;
}

export function getUnifiedInvoiceTypeOptions(t: TFunction) {
  return [
    { label: t('app.kuaicaiwu.invoice.invoiceType.vatSpecial'), value: 'VAT_SPECIAL' },
    { label: t('app.kuaicaiwu.invoice.invoiceType.vatNormal'), value: 'VAT_NORMAL' },
    { label: t('app.kuaicaiwu.invoice.invoiceType.electronic'), value: 'ELECTRONIC' },
  ];
}

export function isPartnerStatementReviewApproved(reviewStatus: unknown): boolean {
  const raw = String(reviewStatus ?? '').trim();
  return raw === '已审核' || raw.toLowerCase() === 'approved';
}

/** 详情头徽标：审核通过优先展示「已审核」，否则展示业务状态（如对账定稿）。 */
export function shouldShowPartnerStatementReviewApprovedBadge(data: {
  status?: string | null;
  review_status?: string | null;
}): boolean {
  if (!isPartnerStatementReviewApproved(data.review_status)) return false;
  const status = String(data.status ?? '').trim();
  return status === 'Confirmed' || status === 'Sent' || status === 'LedgerPosted';
}

export function buildPartnerStatementStatusEnum(t: TFunction) {
  return {
    Draft: { text: t('app.kuaicaiwu.partnerStatement.status.draft') },
    Confirmed: { text: t('app.kuaicaiwu.partnerStatement.status.confirmed') },
    Sent: { text: t('app.kuaicaiwu.partnerStatement.status.sent') },
    Disputed: { text: t('app.kuaicaiwu.partnerStatement.status.disputed') },
    LedgerPosted: { text: t('app.kuaicaiwu.partnerStatement.status.ledgerPosted') },
  };
}

const SENT_CHANNEL_I18N: Record<string, string> = {
  wechat_manual: 'app.kuaicaiwu.partnerStatement.sentChannel.wechatManual',
  print: 'app.kuaicaiwu.partnerStatement.sentChannel.print',
  export: 'app.kuaicaiwu.partnerStatement.sentChannel.export',
  email_manual: 'app.kuaicaiwu.partnerStatement.sentChannel.emailManual',
  other: 'app.kuaicaiwu.partnerStatement.sentChannel.other',
};

export function getSentChannelOptions(t: TFunction) {
  return Object.entries(SENT_CHANNEL_I18N).map(([value, key]) => ({
    label: t(key),
    value,
  }));
}

export function formatSentChannel(value: string | null | undefined, t: TFunction): string {
  if (!value) return '—';
  const key = SENT_CHANNEL_I18N[value];
  return key ? t(key) : value;
}
