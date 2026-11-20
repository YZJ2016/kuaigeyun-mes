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

/** 取单/录入建单后打开入库 Hub 详情抽屉（二次确认） */
export type InboundPullOpenDetailTarget = {
  id: number;
  receipt_type: 'finished_goods' | 'semi_finished_goods';
};

export type InboundHubEntryIntent = {
  receiptTypeFilter?: InboundReceiptType | 'all';
  toastMessage?: string;
};

/** 采购订单取单页 → Hub 新建弹窗：尚未调用下推 API，保存时才建单 */
export type PurchaseReceiptPoComposePayload = {
  /** 兼容字段：多选时为首张采购订单 id */
  purchaseOrderId: number;
  /** 同供应商合并入库时可含多张采购订单 */
  purchaseOrderIds?: number[];
  quantities: Record<number, number>;
  /**
   * 开口行副可取数量（与取单 remaining_aux_quantity 对齐）。
   * 分批第二次取单必须带此字段，禁止新建页仅按整单主数量比例重算副数量。
   */
  auxQuantities?: Record<number, number>;
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
  inboundOpenDetail?: InboundPullOpenDetailTarget;
  inboundHubEntry?: InboundHubEntryIntent;
  purchaseReceiptPoCompose?: PurchaseReceiptPoComposePayload;
};
