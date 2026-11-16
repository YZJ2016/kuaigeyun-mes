/** 来源单据行单价锁定：命中则禁止因改数量自动重算 unit_price */

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
  if (line.pricing_locked === true || line.unit_price_locked === true) return true;
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
  return false;
}
