/** 来源单据行 / 手工改价锁定：命中则禁止因改数量/换客户/换日期自动重算 unit_price */

/** 表单行内标记：用户改过单价或价税合计反算单价后置 true；选料重新取价时清除。不落库。 */
export const DOCUMENT_LINE_UNIT_PRICE_LOCKED_KEY = 'unit_price_locked' as const;

export function markDocumentLineUnitPriceLocked<T extends Record<string, unknown>>(line: T): T {
  return { ...line, [DOCUMENT_LINE_UNIT_PRICE_LOCKED_KEY]: true };
}

export function clearDocumentLineUnitPriceLock<T extends Record<string, unknown>>(line: T): T {
  if (!Object.prototype.hasOwnProperty.call(line, DOCUMENT_LINE_UNIT_PRICE_LOCKED_KEY)) {
    return line;
  }
  const next = { ...line };
  delete (next as Record<string, unknown>)[DOCUMENT_LINE_UNIT_PRICE_LOCKED_KEY];
  return next;
}

export function isDocumentLineUnitPriceLocked(line: Record<string, unknown> | null | undefined): boolean {
  if (!line || typeof line !== 'object') return false;
  if (line.source_line_id != null && String(line.source_line_id).trim() !== '') return true;
  if (line.sourceLineId != null && String(line.sourceLineId).trim() !== '') return true;
  if (line.source_document_line_id != null && String(line.source_document_line_id).trim() !== '') return true;
  if (line.sourceDocumentLineId != null && String(line.sourceDocumentLineId).trim() !== '') return true;
  const srcType = line.source_document_type ?? line.sourceDocumentType ?? line.source_type ?? line.sourceType;
  const srcId = line.source_document_id ?? line.sourceDocumentId ?? line.source_id ?? line.sourceId;
  if (srcType != null && String(srcType).trim() !== '' && srcId != null && String(srcId).trim() !== '') {
    return true;
  }
  const srcCode = line.source_document_code ?? line.sourceDocumentCode ?? line.source_order_code ?? line.sourceOrderCode;
  if (srcCode != null && String(srcCode).trim() !== '') return true;
  if (line.pricing_locked === true || line[DOCUMENT_LINE_UNIT_PRICE_LOCKED_KEY] === true) return true;
  const salesDeliveryItemId = line.sales_delivery_item_id ?? line.salesDeliveryItemId;
  if (salesDeliveryItemId != null && String(salesDeliveryItemId).trim() !== '' && Number(salesDeliveryItemId) > 0) {
    return true;
  }
  const purchaseReceiptItemId = line.purchase_receipt_item_id ?? line.purchaseReceiptItemId;
  if (
    purchaseReceiptItemId != null &&
    String(purchaseReceiptItemId).trim() !== '' &&
    Number(purchaseReceiptItemId) > 0
  ) {
    return true;
  }
  // 采购入库从采购订单/收货通知取单：行上只有 *_item_id，无 source_*，须锁定以免改数量重算冲掉订单价
  const purchaseOrderItemId = line.purchase_order_item_id ?? line.purchaseOrderItemId;
  if (
    purchaseOrderItemId != null &&
    String(purchaseOrderItemId).trim() !== '' &&
    Number(purchaseOrderItemId) > 0
  ) {
    return true;
  }
  const receiptNoticeItemId = line.receipt_notice_item_id ?? line.receiptNoticeItemId;
  if (
    receiptNoticeItemId != null &&
    String(receiptNoticeItemId).trim() !== '' &&
    Number(receiptNoticeItemId) > 0
  ) {
    return true;
  }
  return false;
}
