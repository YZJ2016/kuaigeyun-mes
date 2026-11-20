/**
 * 对账单明细 → 购销发票源行：与后端 partner_statement_invoice_pull 规则一致。
 */
import type { PartnerStatementLine } from '../services/finance/partnerStatement';

export type LedgerPostingMode = 'immediate' | 'by_invoice';

export function invoiceSourceDocTypeForMode(
  partnerType: 'Customer' | 'Supplier' | string,
  ledgerPostingMode?: string | null,
): string {
  const mode: LedgerPostingMode =
    ledgerPostingMode === 'by_invoice' ? 'by_invoice' : 'immediate';
  if (partnerType === 'Customer') {
    return mode === 'by_invoice' ? '销售出库' : '应收单';
  }
  if (partnerType === 'Supplier') {
    return mode === 'by_invoice' ? '采购入库' : '应付单';
  }
  return '';
}

const SUPPLIER_BY_INVOICE_DOC_TYPES = ['采购入库', '工序委外收货'] as const;

export function collectStatementInvoiceLines(
  lines: PartnerStatementLine[],
  partnerType: 'Customer' | 'Supplier' | string,
  ledgerPostingMode?: string | null,
): PartnerStatementLine[] {
  const mode: LedgerPostingMode =
    ledgerPostingMode === 'by_invoice' ? 'by_invoice' : 'immediate';
  const wantTypes =
    partnerType === 'Supplier' && mode === 'by_invoice'
      ? SUPPLIER_BY_INVOICE_DOC_TYPES
      : [invoiceSourceDocTypeForMode(partnerType, ledgerPostingMode)].filter(Boolean);
  if (!wantTypes.length) return [];
  const wantSet = new Set(wantTypes);
  return lines.filter((ln) => {
    if (!wantSet.has(String(ln.doc_type || '').trim())) return false;
    if (ln.doc_id == null) return false;
    if (Number(ln.tree_level ?? 0) > 0) return false;
    return Number(ln.statement_amount ?? ln.debit ?? 0) > 0;
  });
}