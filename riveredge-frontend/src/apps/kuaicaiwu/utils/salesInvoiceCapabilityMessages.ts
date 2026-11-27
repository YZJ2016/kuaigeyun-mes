import type { TFunction } from 'i18next';

export const SALES_INVOICE_CAPABILITY_REASON_MESSAGES: Record<string, string> = {
  'sales_invoice.pull_from_sales_order.not_allowed': '当前状态的销售订单不可加载销售发票',
  'sales_invoice.pull_from_sales_order.no_lines': '销售订单无可开票金额',
  'sales_invoice.pull_from_sales_order.already_pulled': '销售订单可开票金额已全部开票，删除未审核发票后可再次加载',
  'sales_invoice.pull_from_sales_delivery.not_allowed': '当前状态的销售出库单不可加载销售发票',
  'sales_invoice.pull_from_sales_delivery.no_lines': '销售出库单无可开票金额',
  'sales_invoice.pull_from_sales_delivery.already_pulled': '销售出库单可开票金额已全部开票，删除未审核发票后可再次加载',
  'sales_invoice.pull_from_receivable.not_allowed': '当前状态的应收单不可加载销售发票',
  'sales_invoice.pull_from_receivable.no_lines': '应收单无可开票金额',
  'sales_invoice.pull_from_receivable.already_pulled': '应收单可开票金额已全部开票，删除未审核发票后可再次加载',
  'sales_invoice.pull_from_receivable.partner_statement_source':
    '来源为往来对账单的应收须在往来对账单页面创建销售发票',
  'sales_invoice.pull_from_partner_statement.no_lines':
    '往来对账单中无可用的开票明细行（根据发票立账取销售出库，立即立账取应收单）',
  'sales_invoice.pull_from_partner_statement.already_pulled': '往来对账单可开票金额已全部开票，删除未审核发票后可再次加载',
};

export function salesInvoiceCapabilityReasonMessage(
  code: string | null | undefined,
  t?: TFunction,
): string {
  if (!code) return '';
  if (t) {
    const key = `app.kuaicaiwu.salesInvoice.capability.${code}`;
    const translated = t(key);
    if (translated !== key) return translated;
  }
  return SALES_INVOICE_CAPABILITY_REASON_MESSAGES[code] ?? code;
}
