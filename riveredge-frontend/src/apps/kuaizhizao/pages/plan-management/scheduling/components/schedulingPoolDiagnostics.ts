import type { TFunction } from 'i18next';
import type { VisualSchedulingBoardScan } from '../../../../services/production';
import type { WorkOrderForGantt } from '../../../../components/GanttSchedulingChart/types';
import {
  getOperationsNeedingStation,
  getWorkOrderSchedulingMissingFields,
} from '../schedulingDropUtils';

export type WorkOrderDiagnosticSeverity = 'error' | 'warning';

export interface WorkOrderDiagnosticIssue {
  key: string;
  severity: WorkOrderDiagnosticSeverity;
  label: string;
}

const CONFLICT_TYPE_KEYS: Record<string, string> = {
  station_overlap: 'app.kuaizhizao.scheduling.diagnostics.conflict.stationOverlap',
  equipment_overlap: 'app.kuaizhizao.scheduling.diagnostics.conflict.equipmentOverlap',
  mold_overlap: 'app.kuaizhizao.scheduling.diagnostics.conflict.moldOverlap',
  tool_overlap: 'app.kuaizhizao.scheduling.diagnostics.conflict.toolOverlap',
  sequence_violation: 'app.kuaizhizao.scheduling.diagnostics.conflict.sequenceViolation',
  frozen: 'app.kuaizhizao.scheduling.diagnostics.conflict.frozen',
  freeze_window: 'app.kuaizhizao.scheduling.diagnostics.conflict.freezeWindow',
};

export function conflictTypeLabel(type: string, t?: TFunction): string {
  const key = CONFLICT_TYPE_KEYS[type];
  return key && t ? t(key) : type;
}

function missingFieldLabel(
  field: 'planned_start_date' | 'planned_end_date',
  t: TFunction
): string {
  return field === 'planned_start_date'
    ? t('app.kuaizhizao.scheduling.diagnostics.missingPlannedStart')
    : t('app.kuaizhizao.scheduling.diagnostics.missingPlannedEnd');
}

/** 汇总工单在待排表格中展示的排产问题（本地校验 + board-scan 诊断） */
export function collectWorkOrderDiagnosticIssues(
  wo: WorkOrderForGantt,
  boardScan: VisualSchedulingBoardScan | null | undefined,
  t: TFunction,
  options?: {
    materialHardConstraint?: boolean;
    /** 行业包产线模式：不报缺工位/头表日期，改报缺产线 */
    resourceMode?: 'workstation' | 'production_line';
  }
): WorkOrderDiagnosticIssue[] {
  const issues: WorkOrderDiagnosticIssue[] = [];
  const seen = new Set<string>();
  const resourceMode = options?.resourceMode ?? 'workstation';
  const isLineMode = resourceMode === 'production_line';

  const push = (issue: WorkOrderDiagnosticIssue) => {
    if (seen.has(issue.key)) return;
    seen.add(issue.key);
    issues.push(issue);
  };

  // 工位业务线仍提示头表计划日；产线模式不强制
  if (!isLineMode) {
    for (const field of getWorkOrderSchedulingMissingFields(wo)) {
      push({
        key: `missing-${field}`,
        severity: 'warning',
        label: missingFieldLabel(field, t),
      });
    }
  }

  const missingResources = getOperationsNeedingStation(wo, resourceMode);
  if (missingResources.length > 0) {
    push({
      key: isLineMode ? 'missing-production-line' : 'missing-station',
      severity: 'warning',
      label: t(
        isLineMode
          ? 'app.kuaizhizao.scheduling.diagnostics.missingProductionLines'
          : 'app.kuaizhizao.scheduling.diagnostics.missingStations',
        { count: missingResources.length }
      ),
    });
  }

  if (!boardScan) return issues;

  for (const item of boardScan.unscheduled_orders ?? []) {
    if (item.work_order_id !== wo.id) continue;
    if (issues.some((i) => i.key.startsWith('missing-planned'))) continue;
    push({
      key: 'unscheduled',
      severity: 'warning',
      label: item.reason || t('app.kuaizhizao.scheduling.diagnostics.unscheduledFallback'),
    });
  }

  for (const conflict of boardScan.conflicts ?? []) {
    if (conflict.work_order_id !== wo.id) continue;
    push({
      key: `conflict-${conflict.type}-${conflict.task_id ?? conflict.operation_id ?? conflict.message}`,
      severity: 'error',
      label: conflictTypeLabel(conflict.type, t),
    });
  }

  for (const material of boardScan.material_issues ?? []) {
    if (material.work_order_id !== wo.id) continue;
    push({
      key: 'material',
      severity: options?.materialHardConstraint ? 'error' : 'warning',
      label: material.message || t('app.kuaizhizao.scheduling.diagnostics.materialShortageFallback'),
    });
  }

  return issues;
}
