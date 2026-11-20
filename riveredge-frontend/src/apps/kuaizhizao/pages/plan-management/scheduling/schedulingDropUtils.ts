import dayjs from 'dayjs';
import { isOutsourceGanttOperation } from '../../../components/GanttSchedulingChart/stationResourceUtils';
import type { WorkOrderForGantt } from '../../../components/GanttSchedulingChart/types';
import { toApiDateTimeString } from '../../../../../utils/formDate';

function isFactorySchedulingOperation(
  op: NonNullable<WorkOrderForGantt['operations']>[number]
): boolean {
  return !isOutsourceGanttOperation(op);
}

export type WorkOrderSchedulingMissingField = 'planned_start_date' | 'planned_end_date';

export interface OperationNeedingStation {
  operationId: number;
  operationName: string;
  sequence: number;
  workCenterId?: number | null;
  workCenterName?: string | null;
  assignedStationId?: number | null;
  assignedProductionLineId?: number | null;
  assignedWorkerId?: number | null;
  assignedEquipmentId?: number | null;
  assignedMoldId?: number | null;
  plannedStartDate?: string | null;
  plannedEndDate?: string | null;
}

export interface WorkOrderSchedulingPrepContext {
  missingFields: WorkOrderSchedulingMissingField[];
  operationsNeedingStation: OperationNeedingStation[];
}

export function getOperationsNeedingStation(
  wo: WorkOrderForGantt,
  resourceMode: 'workstation' | 'production_line' = 'workstation'
): OperationNeedingStation[] {
  return getOperationsForStationPrep(wo, resourceMode).filter((op) => {
    if (resourceMode === 'production_line') {
      return op.assignedProductionLineId == null || Number(op.assignedProductionLineId) <= 0;
    }
    return op.assignedStationId == null || Number(op.assignedStationId) <= 0;
  });
}

/** 排产补充弹窗：列出可指派工序；产线模式排除委外（不占本厂产线） */
export function getOperationsForStationPrep(
  wo: WorkOrderForGantt,
  resourceMode: 'workstation' | 'production_line' = 'workstation'
): OperationNeedingStation[] {
  return [...(wo.operations ?? [])]
    .filter((op) => op.id != null)
    .filter((op) => (resourceMode === 'production_line' ? isFactorySchedulingOperation(op) : true))
    .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0))
    .map((op) => ({
      operationId: Number(op.id),
      operationName: op.operation_name || `工序${op.sequence ?? ''}`,
      sequence: op.sequence ?? 0,
      workCenterId: op.work_center_id ?? null,
      workCenterName: op.work_center_name ?? null,
      assignedStationId:
        op.assigned_station_id != null && Number(op.assigned_station_id) > 0
          ? Number(op.assigned_station_id)
          : null,
      assignedProductionLineId:
        op.assigned_production_line_id != null && Number(op.assigned_production_line_id) > 0
          ? Number(op.assigned_production_line_id)
          : null,
      assignedWorkerId:
        op.assigned_worker_id != null && Number(op.assigned_worker_id) > 0
          ? Number(op.assigned_worker_id)
          : null,
      assignedEquipmentId:
        op.assigned_equipment_id != null && Number(op.assigned_equipment_id) > 0
          ? Number(op.assigned_equipment_id)
          : null,
      assignedMoldId:
        op.assigned_mold_id != null && Number(op.assigned_mold_id) > 0
          ? Number(op.assigned_mold_id)
          : null,
      plannedStartDate: op.planned_start_date ?? null,
      plannedEndDate: op.planned_end_date ?? null,
    }));
}

export const DEFAULT_OP_SCHEDULE_HOURS = 8;

/**
 * 产线模式：占用时长（小时）= 数量 × 节拍秒 / 3600。
 * 缺数量或节拍时返回 null（禁止静默回落标准工时）。
 */
export function durationHoursFromTakt(quantity: number, taktSeconds: number): number | null {
  const qty = Number(quantity);
  const takt = Number(taktSeconds);
  if (!(qty > 0) || !(takt > 0)) return null;
  return Math.max(qty * takt / 3600, 1 / 60);
}

export function operationPrepStartFieldName(operationId: number): string {
  return `op_start_${operationId}`;
}

export function operationPrepEndFieldName(operationId: number): string {
  return `op_end_${operationId}`;
}

function parseOptionalDayjs(value: unknown): dayjs.Dayjs | null {
  if (value == null || value === '') return null;
  if (dayjs.isDayjs(value)) return value;
  const parsed = dayjs(String(value));
  return parsed.isValid() ? parsed : null;
}

export interface OperationPrepScheduleResult {
  dates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>;
  adjustedOperationNames: string[];
}

function resolveSequentialOperationSlot(
  op: OperationNeedingStation,
  formValues: Record<string, unknown>,
  prevEnd: dayjs.Dayjs | null,
  hours: number,
  workOrderStart?: dayjs.Dayjs | null
): {
  start: dayjs.Dayjs;
  end: dayjs.Dayjs;
  adjusted: boolean;
  nextPrevEnd: dayjs.Dayjs;
} {
  const startRaw = parseOptionalDayjs(formValues[operationPrepStartFieldName(op.operationId)]);
  const endRaw = parseOptionalDayjs(formValues[operationPrepEndFieldName(op.operationId)]);

  let adjusted = false;
  let start: dayjs.Dayjs;
  if (startRaw) {
    start = startRaw;
  } else if (prevEnd) {
    start = prevEnd;
  } else {
    start = dayjs().startOf('hour').add(1, 'hour');
  }

  if (workOrderStart?.isValid() && start.isBefore(workOrderStart)) {
    start = workOrderStart;
    adjusted = true;
  }
  if (prevEnd && start.isBefore(prevEnd)) {
    start = prevEnd;
    adjusted = true;
  }

  let end: dayjs.Dayjs;
  if (endRaw) {
    end = endRaw;
  } else {
    end = start.add(hours, 'hour');
  }

  if (!end.isAfter(start)) {
    end = start.add(hours, 'hour');
    adjusted = true;
  }

  return { start, end, adjusted, nextPrevEnd: end };
}

/** 补充排产弹窗：按工序顺序解析计划时间（未填开始则接上道工序结束；乱序则自动顺延） */
export function resolveOperationPrepScheduleDates(
  operations: OperationNeedingStation[],
  formValues: Record<string, unknown>,
  options?: {
    workOrderStart?: string | null;
    defaultDurationHours?: number;
    /** 产线模式：按工序各自节拍时长（小时） */
    durationHoursByOperationId?: Map<number, number>;
    /** 产线模式：整单一次窗口，禁止按工序串行叠加节拍 */
    sharedWindow?: boolean;
  }
): OperationPrepScheduleResult {
  const fallbackHours = options?.defaultDurationHours ?? DEFAULT_OP_SCHEDULE_HOURS;
  const sorted = [...operations].sort((a, b) => a.sequence - b.sequence);
  const workOrderStart = options?.workOrderStart ? dayjs(options.workOrderStart) : null;
  const validWorkOrderStart = workOrderStart?.isValid() ? workOrderStart : null;

  // 产线整单：所有工序共享同一 start/end；禁止回落默认 8h 伪装节拍
  if (options?.sharedWindow && sorted.length > 0) {
    const first = sorted[0];
    const hoursCandidate =
      options.durationHoursByOperationId?.get(first.operationId) ??
      [...(options.durationHoursByOperationId?.values() ?? [])][0];
    if (hoursCandidate == null || !(Number(hoursCandidate) > 0)) {
      return { dates: [], adjustedOperationNames: [] };
    }
    const hours = Number(hoursCandidate);
    const startRaw = formValues[operationPrepStartFieldName(first.operationId)];
    const startFromForm = dayjs.isDayjs(startRaw)
      ? startRaw
      : startRaw
        ? dayjs(startRaw as string)
        : null;
    const start =
      startFromForm?.isValid()
        ? startFromForm
        : validWorkOrderStart ?? dayjs().startOf('hour');
    const end = start.add(hours, 'hour');
    const startStr = toApiDateTimeString(start);
    const endStr = toApiDateTimeString(end);
    const adjustedOperationNames: string[] = [];
    for (const op of sorted) {
      const prevStart = formValues[operationPrepStartFieldName(op.operationId)];
      const prevEnd = formValues[operationPrepEndFieldName(op.operationId)];
      const sameStart =
        dayjs.isDayjs(prevStart) && prevStart.isSame(start)
          ? true
          : prevStart
            ? dayjs(prevStart as string).isSame(start)
            : false;
      const sameEnd =
        dayjs.isDayjs(prevEnd) && prevEnd.isSame(end)
          ? true
          : prevEnd
            ? dayjs(prevEnd as string).isSame(end)
            : false;
      if (!sameStart || !sameEnd) {
        adjustedOperationNames.push(op.operationName);
      }
    }
    return {
      dates: sorted.map((op) => ({
        operation_id: op.operationId,
        planned_start_date: startStr,
        planned_end_date: endStr,
      })),
      adjustedOperationNames,
    };
  }

  let prevEnd: dayjs.Dayjs | null = validWorkOrderStart;
  const dates: OperationPrepScheduleResult['dates'] = [];
  const adjustedOperationNames: string[] = [];

  for (const op of sorted) {
    const hours =
      options?.durationHoursByOperationId?.get(op.operationId) ?? fallbackHours;
    const slot = resolveSequentialOperationSlot(op, formValues, prevEnd, hours, validWorkOrderStart);
    if (slot.adjusted) {
      adjustedOperationNames.push(op.operationName);
    }
    dates.push({
      operation_id: op.operationId,
      planned_start_date: toApiDateTimeString(slot.start),
      planned_end_date: toApiDateTimeString(slot.end),
    });
    prevEnd = slot.nextPrevEnd;
  }

  return { dates, adjustedOperationNames };
}

/** 将工序计划时间转为表单字段（打开弹窗时归一化乱序时间线） */
export function operationPrepScheduleDatesToFormValues(
  result: OperationPrepScheduleResult
): Record<string, dayjs.Dayjs> {
  return Object.fromEntries(
    result.dates.flatMap(({ operation_id, planned_start_date, planned_end_date }) => [
      [operationPrepStartFieldName(operation_id), dayjs(planned_start_date)],
      [operationPrepEndFieldName(operation_id), dayjs(planned_end_date)],
    ])
  );
}

/** 编辑某一工序时间后，自该工序起向下游顺延，保持顺序时间线 */
export function cascadeOperationPrepScheduleFromIndex(
  operations: OperationNeedingStation[],
  formValues: Record<string, unknown>,
  fromIndex: number,
  options?: {
    workOrderStart?: string | null;
    defaultDurationHours?: number;
    durationHoursByOperationId?: Map<number, number>;
    /** 产线模式：整单共享窗口 */
    sharedWindow?: boolean;
  }
): Record<string, dayjs.Dayjs> {
  if (options?.sharedWindow) {
    return operationPrepScheduleDatesToFormValues(
      resolveOperationPrepScheduleDates(operations, formValues, {
        ...options,
        sharedWindow: true,
      })
    );
  }

  const fallbackHours = options?.defaultDurationHours ?? DEFAULT_OP_SCHEDULE_HOURS;
  const sorted = [...operations].sort((a, b) => a.sequence - b.sequence);
  const workOrderStart = options?.workOrderStart ? dayjs(options.workOrderStart) : null;
  const validWorkOrderStart = workOrderStart?.isValid() ? workOrderStart : null;

  let prevEnd: dayjs.Dayjs | null = validWorkOrderStart;
  const patches: Record<string, dayjs.Dayjs> = {};

  for (let index = 0; index < sorted.length; index += 1) {
    const op = sorted[index];
    const hours =
      options?.durationHoursByOperationId?.get(op.operationId) ?? fallbackHours;
    const slot = resolveSequentialOperationSlot(op, formValues, prevEnd, hours, validWorkOrderStart);
    if (index >= fromIndex) {
      patches[operationPrepStartFieldName(op.operationId)] = slot.start;
      patches[operationPrepEndFieldName(op.operationId)] = slot.end;
    }
    prevEnd = slot.nextPrevEnd;
  }

  return patches;
}

export function mapOperationForGantt(
  op: Record<string, unknown>
): NonNullable<WorkOrderForGantt['operations']>[number] {
  const id = Number(op.id);
  return {
    id: Number.isInteger(id) && id > 0 ? id : undefined,
    operation_name: (op.operation_name as string | null | undefined) ?? null,
    sequence: op.sequence != null ? Number(op.sequence) : undefined,
    work_center_id:
      op.work_center_id != null && Number(op.work_center_id) > 0 ? Number(op.work_center_id) : null,
    work_center_name: (op.work_center_name as string | null | undefined) ?? null,
    planned_start_date: (op.planned_start_date as string | null | undefined) ?? null,
    planned_end_date: (op.planned_end_date as string | null | undefined) ?? null,
    assigned_station_id:
      op.assigned_station_id != null && Number(op.assigned_station_id) > 0
        ? Number(op.assigned_station_id)
        : null,
    assigned_station_name: (op.assigned_station_name as string | null | undefined) ?? null,
    assigned_production_line_id:
      op.assigned_production_line_id != null && Number(op.assigned_production_line_id) > 0
        ? Number(op.assigned_production_line_id)
        : null,
    assigned_production_line_code:
      (op.assigned_production_line_code as string | null | undefined) ?? null,
    assigned_production_line_name:
      (op.assigned_production_line_name as string | null | undefined) ?? null,
    assigned_equipment_id:
      op.assigned_equipment_id != null && Number(op.assigned_equipment_id) > 0
        ? Number(op.assigned_equipment_id)
        : null,
    assigned_equipment_name: (op.assigned_equipment_name as string | null | undefined) ?? null,
    assigned_mold_name: (op.assigned_mold_name as string | null | undefined) ?? null,
    assigned_tool_name: (op.assigned_tool_name as string | null | undefined) ?? null,
    machine_session_state:
      op.machine_session_state === 'on_machine' ||
      op.machine_session_state === 'off_machine' ||
      op.machine_session_state === 'none'
        ? op.machine_session_state
        : null,
  };
}

export function getWorkOrderSchedulingMissingFields(
  wo: Pick<WorkOrderForGantt, 'planned_start_date' | 'planned_end_date'>
): WorkOrderSchedulingMissingField[] {
  const missing: WorkOrderSchedulingMissingField[] = [];
  if (!wo.planned_start_date) missing.push('planned_start_date');
  if (!wo.planned_end_date) missing.push('planned_end_date');
  return missing;
}

export function getWorkOrderSchedulingPrepContext(
  wo: WorkOrderForGantt,
  resourceMode: 'workstation' | 'production_line' = 'workstation'
): WorkOrderSchedulingPrepContext {
  // 产线模式（行业包路径）：不强制工单头计划起止；只补缺产线指派
  if (resourceMode === 'production_line') {
    return {
      missingFields: [],
      operationsNeedingStation: getOperationsNeedingStation(wo, 'production_line'),
    };
  }
  return {
    missingFields: getWorkOrderSchedulingMissingFields(wo),
    operationsNeedingStation: getOperationsForStationPrep(wo),
  };
}

export function workOrderNeedsSchedulingPrep(
  wo: WorkOrderForGantt,
  resourceMode: 'workstation' | 'production_line' = 'workstation'
): boolean {
  if (resourceMode === 'production_line') {
    return getOperationsNeedingStation(wo, 'production_line').length > 0;
  }
  const ctx = getWorkOrderSchedulingPrepContext(wo, resourceMode);
  if (ctx.missingFields.length > 0) return true;
  return getOperationsNeedingStation(wo, resourceMode).length > 0;
}

/** 产线模式：把产线 ID 盖到全部工序（不写工位真源） */
export function stampProductionLineOnWorkOrder(
  wo: WorkOrderForGantt,
  productionLineId: number,
  productionLineName?: string | null
): WorkOrderForGantt {
  const lineId = Number(productionLineId);
  if (!(lineId > 0)) return wo;
  return {
    ...wo,
    operations: (wo.operations ?? []).map((op) => ({
      ...op,
      assigned_production_line_id: lineId,
      assigned_production_line_name:
        productionLineName ?? op.assigned_production_line_name ?? null,
      // 甘特泳道挂载用；持久化走产线 API
      assigned_station_id: lineId,
      assigned_station_name: productionLineName ?? op.assigned_station_name ?? null,
    })),
  };
}

/** 从 DOM 点解析甘特产线/工位泳道 ID（st-{id}） */
export function resolveGanttStationResourceIdFromPoint(
  clientX: number,
  clientY: number
): number | null {
  if (typeof document === 'undefined') return null;
  const els = document.elementsFromPoint(clientX, clientY);
  for (const el of els) {
    let node: Element | null = el;
    while (node) {
      const raw =
        node.getAttribute?.('data-id') ||
        node.getAttribute?.('data-task-id') ||
        node.getAttribute?.('data-resource-id');
      if (raw) {
        const m = String(raw).match(/^st-(\d+)$/i);
        if (m) {
          const id = Number(m[1]);
          if (Number.isInteger(id) && id > 0) return id;
        }
        const asNum = Number(raw);
        if (Number.isInteger(asNum) && asNum > 0) return asNum;
      }
      node = node.parentElement;
    }
  }
  return null;
}

export const SCHEDULING_DRAG_WORK_ORDER = 'application/x-kuaizhizao-scheduling-work-order';
export const SCHEDULING_DRAG_OPERATION = 'application/x-kuaizhizao-scheduling-operation';

export interface PendingSchedulingOperation {
  operationId: number;
  workOrderId: number;
  operationName: string;
  workOrderCode: string;
  sequence: number;
}

export interface ScheduleWorkOrderDropResult {
  operationDateUpdates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>;
  operationStationUpdates: Array<{ operation_id: number; assigned_station_id: number }>;
  pendingOperations: PendingSchedulingOperation[];
  /** 产线模式：整单窗口，同步工单头 */
  workOrderDateUpdate?: { planned_start_date: string; planned_end_date: string } | null;
  /** 产线模式硬失败码 */
  errorCode?: 'daily_capacity_exceeded' | 'missing_takt' | null;
}

const DEFAULT_OP_HOURS = 8;

/**
 * 是否已排上甘特板：以工序计划起止为准。
 * 工单头 planned_* 可能来自交期/MRP，不能冒充「已排」——否则产线拖入会被 alreadyOnBoard 误拦，
 * 且撤排清工序后若头表残留会仍占板。
 */
export function isWorkOrderScheduledOnBoard(wo: WorkOrderForGantt): boolean {
  return (wo.operations ?? []).some(
    (op) => op.id != null && Boolean(op.planned_start_date) && Boolean(op.planned_end_date)
  );
}

/** 已排工序：已指派工位或产线，且具备计划起止时间 */
export function isOperationScheduledOnBoard(
  op: NonNullable<WorkOrderForGantt['operations']>[number]
): boolean {
  if (op.id == null) return false;
  if (!op.planned_start_date || !op.planned_end_date) return false;
  if (op.assigned_production_line_id != null && Number(op.assigned_production_line_id) > 0) {
    return true;
  }
  return op.assigned_station_id != null && Number(op.assigned_station_id) > 0;
}

export function countScheduledOperations(wo: WorkOrderForGantt): number {
  return (wo.operations ?? []).filter(isOperationScheduledOnBoard).length;
}

export function countWorkOrderOperations(wo: WorkOrderForGantt): number {
  return (wo.operations ?? []).filter((op) => op.id != null).length;
}

export function getUnscheduledWorkOrders(workOrders: WorkOrderForGantt[]): WorkOrderForGantt[] {
  return workOrders.filter((wo) => !isWorkOrderScheduledOnBoard(wo));
}

function defaultOpDurationHours(_op: NonNullable<WorkOrderForGantt['operations']>[number]): number {
  return DEFAULT_OP_HOURS;
}

function stationLastEnd(
  stationId: number,
  boardOrders: WorkOrderForGantt[],
  pendingUpdates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>,
  scheduleAnchor?: dayjs.Dayjs,
  options?: { asProductionLine?: boolean }
): dayjs.Dayjs {
  let cursor = dayjs().startOf('hour');
  if (scheduleAnchor?.isAfter(cursor)) {
    cursor = scheduleAnchor;
  }
  const pendingEndByOp = new Map(
    pendingUpdates.map((u) => [u.operation_id, dayjs(u.planned_end_date)])
  );
  const asLine = Boolean(options?.asProductionLine);
  const pendingOpIds = new Set(pendingUpdates.map((u) => u.operation_id));

  for (const wo of boardOrders) {
    for (const op of wo.operations ?? []) {
      if (op.id == null) continue;
      const resourceId = asLine
        ? Number(op.assigned_production_line_id || op.assigned_station_id || 0)
        : Number(op.assigned_station_id || 0);
      if (resourceId !== stationId) continue;
      const endFromPending = pendingEndByOp.get(op.id);
      const end = endFromPending ?? (op.planned_end_date ? dayjs(op.planned_end_date) : null);
      if (end && end.isAfter(cursor)) cursor = end;
    }
  }
  // 仅累计本资源上已写入 pending 的工序结束（禁止跨资源抬高游标）
  for (const wo of boardOrders) {
    for (const op of wo.operations ?? []) {
      if (op.id == null || !pendingOpIds.has(op.id)) continue;
      const resourceId = asLine
        ? Number(op.assigned_production_line_id || op.assigned_station_id || 0)
        : Number(op.assigned_station_id || 0);
      if (resourceId !== stationId) continue;
      const end = pendingEndByOp.get(op.id);
      if (end && end.isAfter(cursor)) cursor = end;
    }
  }
  for (const u of pendingUpdates) {
    // 同批拖入内尚未写回 board 的资源归属：仅当 pending 列表单独使用时，用已算 end 抬游标
    // 产线整单路径不再逐工序累加，此循环对同资源串行工位模式仍需要
    if (asLine) continue;
    const end = dayjs(u.planned_end_date);
    if (end.isAfter(cursor)) cursor = end;
  }
  return cursor;
}

/** 同日同线已排工单件数合计（按工单计，不按工序重复） */
export function sumLineDayScheduledQty(
  lineId: number,
  dayKey: string,
  boardOrders: WorkOrderForGantt[],
  excludeWorkOrderId?: number
): number {
  let total = 0;
  const seenWo = new Set<number>();
  for (const wo of boardOrders) {
    if (excludeWorkOrderId != null && wo.id === excludeWorkOrderId) continue;
    if (seenWo.has(wo.id)) continue;
    const onLine = (wo.operations ?? []).some((op) => {
      const rid = Number(op.assigned_production_line_id || op.assigned_station_id || 0);
      if (rid !== lineId) return false;
      if (!op.planned_start_date) return false;
      return dayjs(op.planned_start_date).format('YYYY-MM-DD') === dayKey;
    });
    if (!onLine) continue;
    seenWo.add(wo.id);
    total += Number(wo.quantity ?? 0);
  }
  return total;
}

function resolveWorkOrderScheduleAnchor(wo: WorkOrderForGantt): dayjs.Dayjs | undefined {
  if (!wo.planned_start_date) return undefined;
  const anchor = dayjs(wo.planned_start_date).startOf('hour');
  const now = dayjs().startOf('hour');
  return anchor.isAfter(now) ? anchor : undefined;
}

/** 将排产结果合并进工单（工位/产线 + 工序计划时间），供甘特图即时展示 */
export function mergeScheduledWorkOrderIntoBoard(
  wo: WorkOrderForGantt,
  result: ScheduleWorkOrderDropResult,
  stationNameById?: Map<number, string>,
  options?: { asProductionLine?: boolean }
): WorkOrderForGantt {
  const asLine = Boolean(options?.asProductionLine);
  const dateByOp = new Map(result.operationDateUpdates.map((item) => [item.operation_id, item]));
  const stationByOp = new Map(
    result.operationStationUpdates.map((item) => [item.operation_id, item.assigned_station_id])
  );
  const operations = (wo.operations ?? []).map((op) => {
    if (op.id == null) return op;
    const datePatch = dateByOp.get(op.id);
    const resourceId = stationByOp.get(op.id);
    const resourceName =
      resourceId != null && resourceId > 0
        ? stationNameById?.get(resourceId)
        : undefined;
    if (asLine && resourceId != null && resourceId > 0) {
      return {
        ...op,
        assigned_production_line_id: resourceId,
        assigned_production_line_name: resourceName ?? op.assigned_production_line_name,
        assigned_station_id: resourceId,
        assigned_station_name: resourceName ?? op.assigned_station_name,
        planned_start_date: datePatch?.planned_start_date ?? op.planned_start_date,
        planned_end_date: datePatch?.planned_end_date ?? op.planned_end_date,
      };
    }
    const stationId = resourceId ?? op.assigned_station_id;
    return {
      ...op,
      assigned_station_id: stationId ?? op.assigned_station_id,
      assigned_station_name:
        stationId != null && stationId > 0
          ? stationNameById?.get(stationId) ?? op.assigned_station_name
          : op.assigned_station_name,
      planned_start_date: datePatch?.planned_start_date ?? op.planned_start_date,
      planned_end_date: datePatch?.planned_end_date ?? op.planned_end_date,
    };
  });
  const header = result.workOrderDateUpdate;
  return {
    ...wo,
    operations,
    planned_start_date: header?.planned_start_date ?? wo.planned_start_date,
    planned_end_date: header?.planned_end_date ?? wo.planned_end_date,
  };
}

/** 刷新列表后保留刚排产工单的工位/工序时间（避免接口延迟导致甘特条消失） */
export function mergeApiWorkOrderWithScheduled(
  apiWo: WorkOrderForGantt,
  scheduledWo: WorkOrderForGantt
): WorkOrderForGantt {
  const scheduledOpsById = new Map(
    (scheduledWo.operations ?? [])
      .filter((op) => op.id != null)
      .map((op) => [Number(op.id), op])
  );
  const apiOps = apiWo.operations ?? [];
  const baseOps = apiOps.length > 0 ? apiOps : scheduledWo.operations ?? [];
  return {
    ...apiWo,
    planned_start_date: scheduledWo.planned_start_date ?? apiWo.planned_start_date,
    planned_end_date: scheduledWo.planned_end_date ?? apiWo.planned_end_date,
    operations: baseOps.map((op) => {
      if (op.id == null) return op;
      const scheduled = scheduledOpsById.get(op.id);
      if (!scheduled) return op;
      return {
        ...op,
        assigned_station_id: scheduled.assigned_station_id ?? op.assigned_station_id,
        assigned_station_name: scheduled.assigned_station_name ?? op.assigned_station_name,
        assigned_production_line_id:
          scheduled.assigned_production_line_id ?? op.assigned_production_line_id,
        assigned_production_line_code:
          scheduled.assigned_production_line_code ?? op.assigned_production_line_code,
        assigned_production_line_name:
          scheduled.assigned_production_line_name ?? op.assigned_production_line_name,
        planned_start_date: scheduled.planned_start_date ?? op.planned_start_date,
        planned_end_date: scheduled.planned_end_date ?? op.planned_end_date,
      };
    }),
  };
}

export function pickFocusOperationTaskId(wo: WorkOrderForGantt): string | null {
  const op = (wo.operations ?? [])
    .filter(
      (item) =>
        item.id != null &&
        ((item.assigned_production_line_id != null && Number(item.assigned_production_line_id) > 0) ||
          (item.assigned_station_id != null && Number(item.assigned_station_id) > 0))
    )
    .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0))[0];
  return op?.id != null ? `op-${op.id}` : null;
}

export function buildScheduleWorkOrderDrop(
  wo: WorkOrderForGantt,
  boardOrders: WorkOrderForGantt[],
  options?: {
    resourceMode?: 'workstation' | 'production_line';
    taktSecondsByLineId?: Map<number, number>;
    dailyCapacityByLineId?: Map<number, number>;
    /** 产线模式：拖入目标泳道产线，覆盖未指派工序 */
    defaultProductionLineId?: number | null;
  }
): ScheduleWorkOrderDropResult {
  const resourceMode = options?.resourceMode ?? 'workstation';
  const taktByLine = options?.taktSecondsByLineId;
  const dailyByLine = options?.dailyCapacityByLineId;
  const defaultLineId =
    options?.defaultProductionLineId != null && Number(options.defaultProductionLineId) > 0
      ? Number(options.defaultProductionLineId)
      : null;
  const asLine = resourceMode === 'production_line';
  const operationDateUpdates: ScheduleWorkOrderDropResult['operationDateUpdates'] = [];
  const operationStationUpdates: ScheduleWorkOrderDropResult['operationStationUpdates'] = [];
  const pendingOperations: PendingSchedulingOperation[] = [];

  const sortedOps = [...(wo.operations ?? [])]
    .filter((op) => op.id != null)
    .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));

  const scheduleAnchor = resolveWorkOrderScheduleAnchor(wo);
  const qty = Number(wo.quantity ?? 0);

  // —— 产线模式：整单一次 qty×takt，厂内工序同窗口（委外不占产线） ——
  if (asLine) {
    const factoryOps = sortedOps.filter((op) => isFactorySchedulingOperation(op));
    const targetLineId =
      defaultLineId ??
      (() => {
        for (const op of factoryOps) {
          const lid = Number(op.assigned_production_line_id || 0);
          if (lid > 0) return lid;
        }
        return null;
      })();

    if (factoryOps.length === 0) {
      return {
        operationDateUpdates,
        operationStationUpdates,
        pendingOperations: [],
        workOrderDateUpdate: null,
        errorCode: null,
      };
    }

    if (targetLineId == null || targetLineId <= 0) {
      for (const op of factoryOps) {
        pendingOperations.push({
          operationId: Number(op.id),
          workOrderId: wo.id,
          operationName: op.operation_name || `工序${op.sequence ?? ''}`,
          workOrderCode: wo.code || String(wo.id),
          sequence: op.sequence ?? 0,
        });
      }
      return {
        operationDateUpdates,
        operationStationUpdates,
        pendingOperations,
        workOrderDateUpdate: null,
        errorCode: null,
      };
    }

    const taktHours = durationHoursFromTakt(qty, taktByLine?.get(targetLineId) ?? 0);
    if (taktHours == null) {
      return {
        operationDateUpdates: [],
        operationStationUpdates: [],
        pendingOperations: factoryOps.map((op) => ({
          operationId: Number(op.id),
          workOrderId: wo.id,
          operationName: op.operation_name || `工序${op.sequence ?? ''}`,
          workOrderCode: wo.code || String(wo.id),
          sequence: op.sequence ?? 0,
        })),
        workOrderDateUpdate: null,
        errorCode: 'missing_takt',
      };
    }

    const slotStart = stationLastEnd(
      targetLineId,
      boardOrders.filter((item) => item.id !== wo.id),
      [],
      scheduleAnchor,
      { asProductionLine: true }
    );
    const slotEnd = slotStart.add(taktHours, 'hour');
    const dayKey = slotStart.format('YYYY-MM-DD');
    const dailyCap = dailyByLine?.get(targetLineId) ?? 0;
    if (dailyCap > 0) {
      const used = sumLineDayScheduledQty(targetLineId, dayKey, boardOrders, wo.id);
      if (used + qty > dailyCap + 1e-9) {
        return {
          operationDateUpdates: [],
          operationStationUpdates: [],
          pendingOperations: [],
          workOrderDateUpdate: null,
          errorCode: 'daily_capacity_exceeded',
        };
      }
    }

    const startStr = toApiDateTimeString(slotStart);
    const endStr = toApiDateTimeString(slotEnd);
    for (const op of factoryOps) {
      const opId = Number(op.id);
      operationDateUpdates.push({
        operation_id: opId,
        planned_start_date: startStr,
        planned_end_date: endStr,
      });
      operationStationUpdates.push({
        operation_id: opId,
        assigned_station_id: targetLineId,
      });
    }
    return {
      operationDateUpdates,
      operationStationUpdates,
      pendingOperations: [],
      workOrderDateUpdate: { planned_start_date: startStr, planned_end_date: endStr },
      errorCode: null,
    };
  }

  // —— 工位模式：逐工序（原逻辑） ——
  for (const op of sortedOps) {
    const opId = Number(op.id);
    const stationId =
      op.assigned_station_id != null && Number(op.assigned_station_id) > 0
        ? Number(op.assigned_station_id)
        : null;

    if (stationId == null) {
      pendingOperations.push({
        operationId: opId,
        workOrderId: wo.id,
        operationName: op.operation_name || `工序${op.sequence ?? ''}`,
        workOrderCode: wo.code || String(wo.id),
        sequence: op.sequence ?? 0,
      });
      continue;
    }

    if (op.planned_start_date && op.planned_end_date) {
      operationStationUpdates.push({
        operation_id: opId,
        assigned_station_id: stationId,
      });
      continue;
    }

    const slotStart = stationLastEnd(
      stationId,
      boardOrders,
      operationDateUpdates,
      scheduleAnchor,
      { asProductionLine: false }
    );
    const hours = defaultOpDurationHours(op);
    const slotEnd = slotStart.add(hours, 'hour');

    operationDateUpdates.push({
      operation_id: opId,
      planned_start_date: toApiDateTimeString(slotStart),
      planned_end_date: toApiDateTimeString(slotEnd),
    });
    operationStationUpdates.push({
      operation_id: opId,
      assigned_station_id: stationId,
    });
  }

  return {
    operationDateUpdates,
    operationStationUpdates,
    pendingOperations,
    workOrderDateUpdate: null,
    errorCode: null,
  };
}

export function buildAssignPendingOperationToStation(
  pendingOp: PendingSchedulingOperation,
  stationId: number,
  boardOrders: WorkOrderForGantt[],
  existingUpdates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }> = [],
  options?: { durationHours?: number }
): {
  operationDateUpdates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>;
  operationStationUpdates: Array<{ operation_id: number; assigned_station_id: number }>;
} {
  const slotStart = stationLastEnd(stationId, boardOrders, existingUpdates);
  const hours = options?.durationHours != null && options.durationHours > 0
    ? options.durationHours
    : DEFAULT_OP_HOURS;
  const slotEnd = slotStart.add(hours, 'hour');
  return {
    operationDateUpdates: [
      {
        operation_id: pendingOp.operationId,
        planned_start_date: toApiDateTimeString(slotStart),
        planned_end_date: toApiDateTimeString(slotEnd),
      },
    ],
    operationStationUpdates: [{ operation_id: pendingOp.operationId, assigned_station_id: stationId }],
  };
}

export function parseWorkOrderDragId(dataTransfer: DataTransfer): number | null {
  const raw = dataTransfer.getData(SCHEDULING_DRAG_WORK_ORDER);
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export function parseOperationDragId(dataTransfer: DataTransfer): number | null {
  const raw = dataTransfer.getData(SCHEDULING_DRAG_OPERATION);
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}
