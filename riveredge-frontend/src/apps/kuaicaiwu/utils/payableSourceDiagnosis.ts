/** 应付来源诊断（区分订单里程碑/入库/发票，避免「建单即应付」误读） */

const PAYABLE_SOURCE_ORDER_MILESTONE = '订单里程碑';
const PAYABLE_SOURCE_PURCHASE_RECEIPT = '采购入库';

export function payableSourceDiagnosisKey(sourceType: string | null | undefined): string | null {
  const st = String(sourceType || '').trim();
  if (st === PAYABLE_SOURCE_ORDER_MILESTONE) {
    return 'app.kuaicaiwu.payable.sourceDiagnosis.orderMilestone';
  }
  if (
    st === PAYABLE_SOURCE_PURCHASE_RECEIPT ||
    st === 'purchase_receipt' ||
    st === 'PurchaseReceipt'
  ) {
    return 'app.kuaicaiwu.payable.sourceDiagnosis.purchaseReceipt';
  }
  if (st === 'PurchaseInvoice' || st === 'purchase_invoice') {
    return 'app.kuaicaiwu.payable.sourceDiagnosis.purchaseInvoice';
  }
  return null;
}
