/**
 * 开口行取单契约：可加载 = remaining_quantity > 0。
 * 已取数量含草稿下游；下游审核/执行态不参与是否开口。
 */

export type PullOpenLineQtyRow = {
  suggested_quantity?: number | null;
  pushed_quantity?: number | null;
  remaining_quantity?: number | null;
  suggested_aux_quantity?: number | null;
  pushed_aux_quantity?: number | null;
  remaining_aux_quantity?: number | null;
  aux_unit?: string | null;
};

/** 采购申请开口行：来源单须已审核通过方可下推（与 BE push_purchase_order / push_inquiry 一致） */
export type PullRequisitionOpenLineRow = PullOpenLineQtyRow & {
  can_push?: boolean | null;
};

/** 开口行是否可勾选（剩余量；不含来源单审核态） */
export function isPullOpenLineSelectable(row: PullOpenLineQtyRow): boolean {
  return Number(row.remaining_quantity ?? 0) > 0;
}

/** 采购申请 → 采购订单/询价：可加载分段唯一门禁（剩余量 + 来源可下推） */
export function isPullRequisitionOpenLineSelectable(row: PullRequisitionOpenLineRow): boolean {
  return row.can_push === true && isPullOpenLineSelectable(row);
}

export type PullWorkOrderFgInboundLineRow = PullOpenLineQtyRow & {
  can_push?: boolean | null;
};

/** 成品入库从工单取单：剩余量 + 领料/报工门禁 */
export function isPullWorkOrderFgLineSelectable(row: PullWorkOrderFgInboundLineRow): boolean {
  if (row.can_push === false) return false;
  if (row.can_push === true) return isPullOpenLineSelectable(row);
  return isPullOpenLineSelectable(row);
}

/** 与 isRowDisabled 对接：不可选时返回 true */
export function isPullOpenLineRowDisabled(row: PullOpenLineQtyRow): boolean {
  return !isPullOpenLineSelectable(row);
}

export function readPullOpenLineSuggestedQty(row: PullOpenLineQtyRow): number {
  return Number(row.suggested_quantity ?? 0);
}

export function readPullOpenLinePushedQty(row: PullOpenLineQtyRow): number {
  return Number(row.pushed_quantity ?? 0);
}

export function readPullOpenLineRemainingQty(row: PullOpenLineQtyRow): number {
  return Number(row.remaining_quantity ?? 0);
}

export function readPullOpenLineAuxSuggestedQty(row: PullOpenLineQtyRow): number | null {
  if (!row.aux_unit || !String(row.aux_unit).trim()) return null;
  const v = row.suggested_aux_quantity;
  return v == null ? 0 : Number(v);
}

export function readPullOpenLineAuxPushedQty(row: PullOpenLineQtyRow): number | null {
  if (!row.aux_unit || !String(row.aux_unit).trim()) return null;
  const v = row.pushed_aux_quantity;
  return v == null ? 0 : Number(v);
}

export function readPullOpenLineAuxRemainingQty(row: PullOpenLineQtyRow): number | null {
  if (!row.aux_unit || !String(row.aux_unit).trim()) return null;
  const v = row.remaining_aux_quantity;
  return v == null ? 0 : Number(v);
}

/** 确认/handoff 预填：有副剩余用副剩余，否则不落副数量 */
export function readPullOpenLineHandoffAuxQty(row: PullOpenLineQtyRow): number | undefined {
  const rem = readPullOpenLineAuxRemainingQty(row);
  if (rem == null) return undefined;
  return rem > 0 ? rem : 0;
}
