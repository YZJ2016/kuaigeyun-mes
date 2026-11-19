/**
 * 与后端 document_push_reconcile_service 支持的 source_type 对齐。
 * Hub 只要 historySourceType 命中即展示「同步对比」页签（组件级，无需页面再开开关）。
 */
export const DOCUMENT_PUSH_RECONCILE_SOURCE_TYPES = [
  'purchase_receipt',
  'finished_goods_receipt',
  'sales_delivery',
  'other_outbound',
  'other_inbound',
  'production_picking',
] as const;

export type DocumentPushReconcileSourceType =
  (typeof DOCUMENT_PUSH_RECONCILE_SOURCE_TYPES)[number];

const RECONCILE_SOURCE_SET = new Set<string>(DOCUMENT_PUSH_RECONCILE_SOURCE_TYPES);

/** historySourceType 是否启用内置同步对比 */
export function supportsDocumentPushReconcile(sourceType: string | undefined | null): boolean {
  return RECONCILE_SOURCE_SET.has(String(sourceType || '').trim());
}
