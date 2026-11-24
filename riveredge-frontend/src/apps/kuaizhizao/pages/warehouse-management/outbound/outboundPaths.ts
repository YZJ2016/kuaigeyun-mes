export const OUTBOUND_LIST_PATH = '/apps/kuaizhizao/warehouse-management/outbound';

/** 销售中心出库列表（与仓储出库 Hub 同壳，菜单 path 不同） */
export const SALES_OUTBOUND_LIST_PATH = '/apps/kuaizhizao/sales-management/outbound';

/** 当前 pathname 属于销售中心出库还是仓储出库 Hub */
export function resolveOutboundListPath(pathname: string): string {
  return pathname.includes('/sales-management/') ? SALES_OUTBOUND_LIST_PATH : OUTBOUND_LIST_PATH;
}

export function salesDeliveryCreatePath(listPath: string = OUTBOUND_LIST_PATH): string {
  return `${listPath}/sales-delivery/new`;
}

export function salesDeliveryEditPath(
  deliveryId: number,
  listPath: string = OUTBOUND_LIST_PATH,
): string {
  return `${listPath}/sales-delivery/${Number(deliveryId)}/edit`;
}

export const outboundWorkOrderEntryPath = (woId: number, materialCallId?: number) => {
  const base = `${OUTBOUND_LIST_PATH}/entry/work-order/${woId}`;
  if (materialCallId != null && materialCallId > 0) {
    return `${base}?materialCallId=${materialCallId}`;
  }
  return base;
};

export const outboundSalesOrderEntryPath = (soId: number) =>
  `${OUTBOUND_LIST_PATH}/entry/sales-order/${soId}`;

export const outboundShipmentNoticeEntryPath = (noticeId: number) =>
  `${OUTBOUND_LIST_PATH}/entry/shipment-notice/${noticeId}`;

export const outboundOutsourceEntryPath = (woId: number) =>
  `${OUTBOUND_LIST_PATH}/entry/outsource-work-order/${woId}`;
