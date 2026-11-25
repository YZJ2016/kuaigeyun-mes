import type { ChangeImpactPreview } from '../../services/sales-order-change';

/** 变更影响预览是否有可展示内容（空对象不算「有数据」） */
export function changeImpactHasVisibleContent(impact: ChangeImpactPreview | null | undefined): boolean {
  if (!impact) return false;
  if ((impact.blocking_errors?.length ?? 0) > 0) return true;
  if ((impact.warnings?.length ?? 0) > 0) return true;
  if ((impact.recommended_actions?.length ?? 0) > 0) return true;
  const lists: Array<Array<Record<string, unknown>> | undefined> = [
    impact.affected_demands,
    impact.affected_computations,
    impact.affected_plans,
    impact.affected_work_orders,
    impact.affected_receipt_notices,
    impact.affected_inbounds,
  ];
  return lists.some((arr) => (arr?.length ?? 0) > 0);
}