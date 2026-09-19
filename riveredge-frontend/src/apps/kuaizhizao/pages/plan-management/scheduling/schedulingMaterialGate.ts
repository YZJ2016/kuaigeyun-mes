import type { TFunction } from 'i18next';
import type { SchedulingConstraints, VisualSchedulingBoardScan } from '../../../services/production';

export type MaterialGateDecision = 'allow' | 'warn' | 'block';

export function getMaterialIssueForWorkOrder(
  workOrderId: number,
  boardScan: VisualSchedulingBoardScan | null | undefined
) {
  return (boardScan?.material_issues ?? []).find((item) => item.work_order_id === workOrderId);
}

export function resolveMaterialGateDecision(
  workOrderId: number,
  constraints: SchedulingConstraints,
  boardScan: VisualSchedulingBoardScan | null | undefined
): MaterialGateDecision {
  const issue = getMaterialIssueForWorkOrder(workOrderId, boardScan);
  if (!issue || !constraints.consider_material) return 'allow';
  if (constraints.material_hard_constraint) return 'block';
  return 'warn';
}

export function filterWorkOrderIdsByMaterialGate(
  workOrderIds: number[],
  constraints: SchedulingConstraints,
  boardScan: VisualSchedulingBoardScan | null | undefined
): { allowedIds: number[]; blockedIds: number[]; warnIds: number[] } {
  const allowedIds: number[] = [];
  const blockedIds: number[] = [];
  const warnIds: number[] = [];
  for (const id of workOrderIds) {
    const decision = resolveMaterialGateDecision(id, constraints, boardScan);
    if (decision === 'block') blockedIds.push(id);
    else if (decision === 'warn') warnIds.push(id);
    else allowedIds.push(id);
  }
  return { allowedIds, blockedIds, warnIds };
}

export function buildMaterialGateConfirmDescription(
  warnCount: number,
  blockedCount: number,
  t: TFunction
): string | undefined {
  if (blockedCount > 0 && warnCount > 0) {
    return t('app.kuaizhizao.scheduling.materialGate.confirmMixed', {
      blocked: blockedCount,
      warn: warnCount,
    });
  }
  if (blockedCount > 0) {
    return t('app.kuaizhizao.scheduling.materialGate.confirmBlocked', { count: blockedCount });
  }
  if (warnCount > 0) {
    return t('app.kuaizhizao.scheduling.materialGate.confirmWarn', { count: warnCount });
  }
  return undefined;
}
