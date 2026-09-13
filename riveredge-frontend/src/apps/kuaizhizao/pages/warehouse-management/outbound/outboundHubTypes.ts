/** Hub 聚合列表统一行类型 */

import type { TFunction } from 'i18next';
import type {
  KuaizhizaoDocumentActionKey,
  KuaizhizaoPullCreateMenuItemSpec,
} from '../../../constants/documentActionRegistry';
import { outboundHubCapabilityReasonMessage } from '../../../../../hooks/useDocumentCapabilities';
import type { OutboundQuickPullKey } from './outboundPullEntryTypes';

export type OutboundIssueType =
  | 'production_picking'
  | 'sales_delivery'
  | 'outsource_issue'
  | 'other_outbound'
  | 'material_borrow'
  | 'purchase_return';

/** 模块级 scoped 出库 Hub 包装页 props */
export type OutboundHubPageProps = {
  fixedOutboundType?: OutboundIssueType;
  scopedOutboundTypes?: readonly OutboundIssueType[];
  headerTitle?: string;
  columnPersistenceId?: string;
};

export interface OutboundHubOrder {
  id?: number;
  outbound_type?: OutboundIssueType;
  delivery_code?: string;
  picking_code?: string;
  outbound_code?: string;
  borrow_code?: string;
  issue_code?: string;
  return_code?: string;
  purchase_order_code?: string;
  supplier_name?: string;
  return_time?: string;
  returner_name?: string;
  status?: string;
  delivery_date?: string;
  customer_id?: number;
  customer_name?: string;
  work_order_id?: number;
  work_order_code?: string;
  sales_order_id?: number;
  sales_order_code?: string;
  outsource_work_order_id?: number;
  outsource_work_order_code?: string;
  warehouse_id?: number;
  warehouse_name?: string;
  total_quantity?: number;
  quantity_unit?: string | null;
  total_amount?: number;
  total_items?: number;
  /** 列表「明细」列预览（仅 material_name） */
  items?: { material_name?: string | null }[];
  required_quantity_total?: number;
  picked_quantity_total?: number;
  delivered_by?: string;
  picker_name?: string;
  deliverer_name?: string;
  borrower_name?: string;
  issued_by_name?: string;
  picking_time?: string;
  delivery_time?: string;
  borrow_time?: string;
  issued_at?: string;
  reason_type?: string;
  picking_score?: number | null;
  picking_rank_band?: string | null;
  notes?: string;
  attachments?: { uid?: string; name?: string; url?: string }[];
  created_at?: string;
  updated_at?: string;
  capabilities?: {
    confirm?: { allowed?: boolean; reason?: string };
    withdraw?: { allowed?: boolean; reason?: string };
    print?: { allowed?: boolean; reason?: string };
    delete?: { allowed?: boolean; reason?: string };
    update?: { allowed?: boolean; reason?: string };
  };
  [key: string]: unknown;
}

export const OUTBOUND_PENDING_STATUSES = new Set([
  '待出库',
  '待领料',
  '待借出',
  '待退货',
  '草稿',
  'draft',
  'pending',
]);

export const OUTBOUND_POSTED_STATUSES = new Set([
  '已出库',
  '已领料',
  '已借出',
  '已退货',
  '已完成',
  'completed',
  '已确认',
  'confirmed',
]);

export const OUTBOUND_ISSUE_TYPE_I18N_KEYS: Record<OutboundIssueType, string> = {
  production_picking: 'app.kuaizhizao.warehouseOutbound.type.productionPicking',
  sales_delivery: 'app.kuaizhizao.warehouseOutbound.type.salesDelivery',
  outsource_issue: 'app.kuaizhizao.warehouseOutbound.type.outsourceIssue',
  other_outbound: 'app.kuaizhizao.warehouseOutbound.type.otherOutbound',
  material_borrow: 'app.kuaizhizao.warehouseOutbound.type.materialBorrow',
  purchase_return: 'app.kuaizhizao.warehouseOutbound.type.purchaseReturn',
};

export const OUTBOUND_ISSUE_TYPES: OutboundIssueType[] = [
  'production_picking',
  'sales_delivery',
  'outsource_issue',
  'other_outbound',
  'material_borrow',
  'purchase_return',
];

export function getOutboundIssueTypeLabel(t: TFunction, type: OutboundIssueType): string {
  return t(OUTBOUND_ISSUE_TYPE_I18N_KEYS[type]);
}

/** 列表工具栏快速筛选：全部 + 各出库类型（可选 scoped 子集） */
export function outboundIssueTypeSegmentOptions(
  t: TFunction,
  scopedTypes?: readonly OutboundIssueType[],
): Array<{ label: string; value: string }> {
  const types = scopedTypes?.length
    ? OUTBOUND_ISSUE_TYPES.filter((type) => scopedTypes.includes(type))
    : OUTBOUND_ISSUE_TYPES;
  const showAll = !scopedTypes?.length || scopedTypes.length > 1;
  return [
    ...(showAll ? [{ label: t('app.kuaizhizao.warehouseCommon.allTypes'), value: 'all' }] : []),
    ...types.map((type) => ({
      label: getOutboundIssueTypeLabel(t, type),
      value: type,
    })),
  ];
}

export const OUTBOUND_ISSUE_TYPE_LABELS: Record<OutboundIssueType, string> = {
  production_picking: '生产领料',
  sales_delivery: '销售出库',
  outsource_issue: '委外发料',
  other_outbound: '其他出库',
  material_borrow: '借料单',
  purchase_return: '采购退货',
};

export function isOutboundConfirmable(record: OutboundHubOrder): boolean {
  if (record.capabilities?.confirm != null) {
    return record.capabilities.confirm.allowed === true;
  }
  if (record.outbound_type === 'outsource_issue') return false;
  return OUTBOUND_PENDING_STATUSES.has(String(record.status || '').trim());
}

export function isOutboundWithdrawable(record: OutboundHubOrder): boolean {
  return record.capabilities?.withdraw?.allowed === true;
}

export function isOutboundDeletable(record: OutboundHubOrder): boolean {
  if (record.outbound_type === 'outsource_issue') return false;
  if (record.capabilities?.delete != null) {
    return record.capabilities.delete.allowed === true;
  }
  const st = String(record.status || '').trim();
  return ['待审核', '草稿', 'draft', '已取消', 'cancelled'].includes(st);
}

/** 确认出库/领料/借出前可编辑（capabilities.update） */
const OUTBOUND_EDITABLE_FALLBACK: Partial<Record<OutboundIssueType, Set<string>>> = {
  production_picking: new Set(['草稿', 'draft', '待审核', '待领料', 'pending']),
  sales_delivery: new Set(['草稿', 'draft', '待审核', '待出库', 'pending']),
  other_outbound: new Set(['草稿', 'draft', '待审核', '待出库', 'pending']),
  material_borrow: new Set(['草稿', 'draft', '待审核', '待借出', 'pending']),
};

export function isOutboundEditable(record: OutboundHubOrder): boolean {
  if (record.outbound_type === 'outsource_issue') return false;
  if (record.capabilities?.update != null) {
    return record.capabilities.update.allowed === true;
  }
  const ot = record.outbound_type;
  if (!ot) return false;
  const allowed = OUTBOUND_EDITABLE_FALLBACK[ot];
  if (!allowed) return false;
  return allowed.has(String(record.status || '').trim());
}

export function outboundConfirmCapabilityReasonMessage(record: OutboundHubOrder, t: TFunction): string {
  return outboundHubCapabilityReasonMessage(record.capabilities?.confirm?.reason, t);
}

export function outboundWithdrawCapabilityReasonMessage(record: OutboundHubOrder, t: TFunction): string {
  return outboundHubCapabilityReasonMessage(record.capabilities?.withdraw?.reason, t);
}

export function outboundUpdateCapabilityReasonMessage(record: OutboundHubOrder, t: TFunction): string {
  return outboundHubCapabilityReasonMessage(record.capabilities?.update?.reason, t);
}

export function outboundDocumentCode(record: OutboundHubOrder): string {
  return (
    record.delivery_code ||
    record.picking_code ||
    record.outbound_code ||
    record.borrow_code ||
    record.issue_code ||
    record.return_code ||
    String(record.id ?? '')
  );
}

function pushUniqueRef(parts: string[], value: unknown) {
  const s = String(value ?? '').trim();
  if (s && !parts.includes(s)) parts.push(s);
}

export function outboundSourceDocNo(record: OutboundHubOrder): string {
  const parts: string[] = [];
  pushUniqueRef(parts, record.purchase_order_code);
  pushUniqueRef(parts, record.sales_order_code);
  pushUniqueRef(parts, record.work_order_code);
  pushUniqueRef(parts, record.outsource_work_order_code);
  return parts.join(' / ');
}

export function outboundDocumentTrackingType(
  order: Pick<OutboundHubOrder, 'outbound_type'>,
): 'production_picking' | 'sales_delivery' | 'other_outbound' | 'material_borrow' | undefined {
  if (order.outbound_type === 'sales_delivery') return 'sales_delivery';
  if (order.outbound_type === 'production_picking') return 'production_picking';
  if (order.outbound_type === 'other_outbound') return 'other_outbound';
  if (order.outbound_type === 'material_borrow') return 'material_borrow';
  return undefined;
}

/** Hub 统一「出库日期」原始值 */
export function resolveOutboundHubDateRaw(record: OutboundHubOrder): unknown {
  return (
    record.delivery_date ||
    record.picking_time ||
    record.delivery_time ||
    record.borrow_time ||
    record.return_time ||
    record.issued_at ||
    null
  );
}

/** Hub 统一「操作员」 */
export function resolveOutboundHubOperator(record: OutboundHubOrder): string {
  const value =
    record.delivered_by ||
    record.picker_name ||
    record.deliverer_name ||
    record.borrower_name ||
    record.returner_name ||
    record.issued_by_name ||
    '';
  return String(value).trim();
}

export function mapOutsourceIssueToOutbound(item: Record<string, unknown>): OutboundHubOrder {
  const code = String(item.code ?? '');
  const statusRaw = String(item.status ?? '');
  const status =
    statusRaw === 'completed' ? '已完成' : statusRaw === 'draft' ? '已出库' : statusRaw || '已出库';
  const previewItems = Array.isArray(item.items)
    ? (item.items as { material_name?: string | null }[])
    : [];
  return {
    id: item.id as number,
    outbound_type: 'outsource_issue',
    issue_code: code,
    picking_code: code,
    work_order_code: String(item.outsource_work_order_code ?? item.outsourceWorkOrderCode ?? ''),
    warehouse_id: item.warehouse_id as number | undefined,
    warehouse_name: String(item.warehouse_name ?? item.warehouseName ?? ''),
    total_quantity: Number(item.total_quantity ?? item.quantity ?? 0),
    total_items: Number(item.total_items ?? 1),
    quantity_unit:
      item.quantity_unit != null
        ? String(item.quantity_unit)
        : item.unit != null
          ? String(item.unit)
          : null,
    items: previewItems,
    delivered_by: String(
      item.issued_by_name ?? item.issuedByName ?? item.created_by_name ?? item.createdByName ?? '',
    ),
    delivery_date: String(item.issued_at ?? item.issuedAt ?? item.created_at ?? item.createdAt ?? ''),
    status,
    updated_at: String(item.updated_at ?? item.updatedAt ?? ''),
    created_at: String(item.created_at ?? item.createdAt ?? ''),
    created_by: item.created_by ?? item.createdBy,
    created_by_name: item.created_by_name ?? item.createdByName,
    updated_by: item.updated_by ?? item.updatedBy,
    updated_by_name: item.updated_by_name ?? item.updatedByName,
    notes: String(item.remarks ?? item.notes ?? ''),
    lifecycle: item.lifecycle as OutboundHubOrder['lifecycle'],
  };
}

const OUTBOUND_PULL_ACTION_ISSUE_TYPES: Partial<
  Record<KuaizhizaoDocumentActionKey, readonly OutboundIssueType[]>
> = {
  'outbound.pull_from_work_order': ['production_picking'],
  'sales_delivery.pull_from_shipment_notice': ['sales_delivery'],
  'sales_delivery.pull_from_sales_order': ['sales_delivery'],
  'outbound.pull_from_outsource_work_order': ['outsource_issue'],
  'delivery_note.pull_from_sales_delivery': ['sales_delivery'],
};

const OUTBOUND_QUICK_PULL_KEY_ISSUE_TYPES: Record<
  OutboundQuickPullKey,
  readonly OutboundIssueType[]
> = {
  work_order: ['production_picking'],
  shipment_notice: ['sales_delivery'],
  sales_order: ['sales_delivery'],
  outsource: ['outsource_issue'],
  delivery_note: ['sales_delivery'],
};

function outboundPullTargetsOverlapScope(
  targets: readonly OutboundIssueType[],
  scopedTypes?: readonly OutboundIssueType[],
): boolean {
  if (!scopedTypes?.length) return true;
  return targets.some((type) => scopedTypes.includes(type));
}

export function isOutboundPullActionInHubScope(
  actionKey: KuaizhizaoDocumentActionKey,
  scopedTypes?: readonly OutboundIssueType[],
): boolean {
  const targets = OUTBOUND_PULL_ACTION_ISSUE_TYPES[actionKey];
  if (!targets?.length) return !scopedTypes?.length;
  return outboundPullTargetsOverlapScope(targets, scopedTypes);
}

export function filterOutboundPullCreateMenuSpecs(
  specs: KuaizhizaoPullCreateMenuItemSpec[],
  scopedTypes?: readonly OutboundIssueType[],
): KuaizhizaoPullCreateMenuItemSpec[] {
  if (!scopedTypes?.length) return specs;
  return specs.filter((spec) => isOutboundPullActionInHubScope(spec.actionKey, scopedTypes));
}

export function resolveDefaultOutboundQuickPullKey(
  scopedTypes?: readonly OutboundIssueType[],
): OutboundQuickPullKey {
  if (!scopedTypes?.length) return 'work_order';
  const order: OutboundQuickPullKey[] = [
    'work_order',
    'shipment_notice',
    'sales_order',
    'outsource',
    'delivery_note',
  ];
  for (const key of order) {
    if (outboundPullTargetsOverlapScope(OUTBOUND_QUICK_PULL_KEY_ISSUE_TYPES[key], scopedTypes)) {
      return key;
    }
  }
  return 'work_order';
}
