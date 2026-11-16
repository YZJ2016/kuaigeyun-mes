import type { InboundReceiptType } from './inboundHubTypes';

export type PurchaseReceiptEntryHandoff = {
  lineWhByPoItemId: Record<number, number>;
  lineLocByPoItemId: Record<number, number | undefined>;
  lineLocCodeByPoItemId: Record<number, string>;
  lineBatchByPoItemId: Record<number, string>;
  lineSerialByPoItemId: Record<number, string[]>;
};

export type InboundPullDirectConfirmTarget = {
  id: number;
  receipt_type: InboundReceiptType;
  purchaseReceiptHandoff?: PurchaseReceiptEntryHandoff;
};

/** 采购订单取单页 → Hub 新建弹窗：尚未调用下推 API，保存时才建单 */
export type PurchaseReceiptPoComposePayload = {
  purchaseOrderId: number;
  quantities: Record<number, number>;
  batchNumbers: Record<number, string>;
  lineWh: Record<number, number>;
  lineLoc: Record<number, number | undefined>;
  lineLocCode: Record<number, string>;
  lineSerials: Record<number, string[]>;
  defaultWarehouseId?: number;
  receiptTimeIso?: string;
  receiverId?: number;
  receiverName?: string;
  deliveryNote?: string;
  notes?: string;
  attachments?: unknown[];
};

export type InboundPullEntryNavigationState = {
  inboundDirectConfirm?: InboundPullDirectConfirmTarget;
  purchaseReceiptPoCompose?: PurchaseReceiptPoComposePayload;
};
