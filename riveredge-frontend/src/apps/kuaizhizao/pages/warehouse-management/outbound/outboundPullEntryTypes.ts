import type { OutboundIssueType } from './outboundHubTypes';

export type OutboundQuickPullKey =
  | 'work_order'
  | 'sales_order'
  | 'shipment_notice'
  | 'outsource'
  | 'delivery_note';

export type OutboundPullDirectConfirmTarget = {
  id: number;
  outbound_type: OutboundIssueType;
};

/** 取单/录入建单后打开出库 Hub 详情抽屉（二次确认） */
export type OutboundPullOpenDetailTarget = {
  id: number;
  outbound_type: OutboundIssueType;
};

export type OutboundHubEntryIntent = {
  /** 进入后筛选出库类型 */
  outboundTypeFilter?: OutboundIssueType | 'all';
  /** 进入后自动打开取单弹窗 */
  openPullModal?: OutboundQuickPullKey;
  /** 进入后展示一次提示 */
  toastMessage?: string;
};

export type OutboundPullEntryNavigationState = {
  outboundDirectConfirm?: OutboundPullDirectConfirmTarget;
  outboundOpenDetail?: OutboundPullOpenDetailTarget;
  outboundHubEntry?: OutboundHubEntryIntent;
};
