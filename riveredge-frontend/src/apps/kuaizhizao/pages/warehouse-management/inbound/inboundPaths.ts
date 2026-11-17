export const INBOUND_LIST_PATH = '/apps/kuaizhizao/warehouse-management/inbound';

/** 采购中心入库列表（与仓储入库 Hub 同壳，菜单 path 不同） */
export const PURCHASE_INBOUND_LIST_PATH = '/apps/kuaizhizao/purchase-management/inbound';

/** 当前 pathname 属于采购中心入库还是仓储入库 Hub */
export function resolveInboundListPath(pathname: string): string {
  return pathname.includes('/purchase-management/')
    ? PURCHASE_INBOUND_LIST_PATH
    : INBOUND_LIST_PATH;
}

export function purchaseReceiptCreatePath(listPath: string = INBOUND_LIST_PATH): string {
  return `${listPath}/new`;
}

export function purchaseReceiptEditPath(
  receiptId: number,
  listPath: string = INBOUND_LIST_PATH,
): string {
  return `${listPath}/${Number(receiptId)}/edit`;
}

export function purchaseReceiptCopyCreatePath(
  copyFromId: number,
  listPath: string = INBOUND_LIST_PATH,
): string {
  return `${purchaseReceiptCreatePath(listPath)}?copyFrom=${Number(copyFromId)}`;
}

function purchaseReceiptHubDeepLinkPath(
  receiptId: number,
  action: 'detail' | 'edit',
  listPath: string = INBOUND_LIST_PATH,
): string {
  if (action === 'edit') {
    return purchaseReceiptEditPath(receiptId, listPath);
  }
  return `${listPath}?documentType=purchase_receipt&receipt_id=${Number(receiptId)}&action=${action}`;
}

/** 深链打开采购入库详情抽屉（Hub `action=detail`） */
export function purchaseReceiptHubDetailPath(
  receiptId: number,
  listPath: string = INBOUND_LIST_PATH,
): string {
  return purchaseReceiptHubDeepLinkPath(receiptId, 'detail', listPath);
}

/** 深链打开采购入库独立编辑页（UniTab） */
export function purchaseReceiptHubEditPath(
  receiptId: number,
  listPath: string = INBOUND_LIST_PATH,
): string {
  return purchaseReceiptHubDeepLinkPath(receiptId, 'edit', listPath);
}

export const inboundPoEntryPath = (poId: number) =>
  `${INBOUND_LIST_PATH}/entry/purchase-order/${poId}`;

/** 收货通知取单录入页 */
export const inboundReceiptNoticeEntryPath = (noticeId: number) =>
  `${INBOUND_LIST_PATH}/entry/receipt-notice/${noticeId}`;

export const inboundWorkOrderEntryPath = (woId: number) =>
  `${INBOUND_LIST_PATH}/entry/work-order/${woId}`;

export const inboundProductionReturnEntryPath = (workOrderId: number) =>
  `${INBOUND_LIST_PATH}/entry/production-return/${workOrderId}`;

export const inboundSalesReturnEntryPath = (salesOrderId: number) =>
  `${INBOUND_LIST_PATH}/entry/sales-order/${salesOrderId}`;

export const inboundOutsourceEntryPath = (woId: number, pullType: string) =>
  `${INBOUND_LIST_PATH}/entry/outsource-work-order/${woId}?pullType=${encodeURIComponent(pullType)}`;
