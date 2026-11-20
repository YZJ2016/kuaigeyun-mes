import type { TFunction } from 'i18next';

export const PURCHASE_INVOICE_CAPABILITY_REASON_MESSAGES: Record<string, string> = {
  'purchase_invoice.pull_from_purchase_order.not_allowed': '当前状态的采购订单不可加载采购发票',
  'purchase_invoice.pull_from_purchase_order.no_lines': '采购订单无可开票金额',
  'purchase_invoice.pull_from_purchase_order.already_pulled': '采购订单可开票金额已全部开票，删除未审核发票后可再次加载',
  'purchase_invoice.pull_from_purchase_receipt.not_allowed': '当前状态的采购入库单不可加载采购发票',
  'purchase_invoice.pull_from_purchase_receipt.no_lines': '采购入库单无可开票金额',
  'purchase_invoice.pull_from_purchase_receipt.already_pulled': '采购入库单可开票金额已全部开票，删除未审核发票后可再次加载',
  'purchase_invoice.pull_from_purchase_receipt.partner_statement_ledger':
    '立账策略为以按月结对账单为准，须先完成往来对账单后再从对账单加载采购发票',
  'purchase_invoice.pull_from_outsource_order_receipt.not_allowed': '当前工序委外收货不可加载采购发票',
  'purchase_invoice.pull_from_outsource_order_receipt.no_lines': '工序委外收货无可开票金额',
  'purchase_invoice.pull_from_outsource_order_receipt.already_pulled':
    '工序委外收货可开票金额已全部收票，删除未审核发票后可再次加载',
  'purchase_invoice.pull_from_payable.not_allowed': '当前状态的应付单不可加载采购发票',
  'purchase_invoice.pull_from_payable.no_lines': '应付单无可开票金额',
  'purchase_invoice.pull_from_payable.already_pulled': '应付单可开票金额已全部开票，删除未审核发票后可再次加载',
  'purchase_invoice.pull_from_partner_statement.no_lines':
    '往来对账单中无可用的收票明细行（根据发票立账取采购入库或工序委外收货，立即立账取应付单）',
  'purchase_invoice.pull_from_partner_statement.already_pulled': '往来对账单可开票金额已全部收票，删除未审核发票后可再次加载',
};

export function purchaseInvoiceCapabilityReasonMessage(
  code: string | null | undefined,
  t?: TFunction,
): string {
  if (!code) return '';
  if (t) {
    const key = `app.kuaicaiwu.purchaseInvoice.capability.${code}`;
    const translated = t(key);
    if (translated !== key) return translated;
  }
  return PURCHASE_INVOICE_CAPABILITY_REASON_MESSAGES[code] ?? code;
}
