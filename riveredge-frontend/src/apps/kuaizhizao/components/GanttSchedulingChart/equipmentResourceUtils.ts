/**
 * 设备资源型甘特：每个设备一行，同设备多道工序在同一行按时间轴分段展示。
 */

import dayjs from 'dayjs';
import type { WorkOrderForGantt, GanttTask } from './types';
import { buildGanttNodeTooltip, operationToGanttTask, sortWorkOrdersForGantt } from './utils';
import { findOverlappingTaskIds } from './stationResourceUtils';

const DEFAULT_START_HOUR = 8;
const DEFAULT_END_HOUR = 17;

export interface EquipmentResource {
  id: number;
  name: string;
  code?: string;
  type?: string;
}

export function equipmentResourceId(equipmentId: number): string {
  return `eq-${equipmentId}`;
}

export function isEquipmentResourceTaskId(id: number | string): boolean {
  return String(id).startsWith('eq-');
}

function parseEquipmentIdFromResourceRow(id: number | string): number | null {
  const m = String(id).match(/^eq-(\d+)$/i);
  if (!m) return null;
  const parsed = Number(m[1]);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export { parseEquipmentIdFromResourceRow };

function defaultDayRange(): { start: Date; end: Date } {
  const today = dayjs().startOf('day');
  return {
    start: today.hour(DEFAULT_START_HOUR).minute(0).toDate(),
    end: today.hour(DEFAULT_END_HOUR).minute(0).toDate(),
  };
}

function rangeFromTasks(childTasks: GanttTask[]): { start: Date; end: Date } {
  if (childTasks.length === 0) return defaultDayRange();
  const starts = childTasks.map((t) => t.start.getTime());
  const ends = childTasks.map((t) => t.end.getTime());
  return {
    start: new Date(Math.min(...starts)),
    end: new Date(Math.max(...ends)),
  };
}

function durationDays(start: Date, end: Date): number {
  const ms = end.getTime() - start.getTime();
  return Math.max(1, Math.ceil(ms / (24 * 60 * 60 * 1000)));
}

function parseOperationIdFromTaskId(id: number | string): number | null {
  const m = String(id).match(/^op-(\d+)$/i);
  if (!m) return null;
  const opId = Number(m[1]);
  return Number.isInteger(opId) && opId > 0 ? opId : null;
}

function buildEmptyEquipmentResourceRow(equipmentId: number, name: string, code?: string): GanttTask {
  const { start, end } = defaultDayRange();
  const codePrefix = code ? `${code} ` : '';
  const label = `${codePrefix}${name}`.trim();
  return {
    id: equipmentResourceId(equipmentId),
    type: 'task',
    parent: 0,
    text: label,
    gantt_primary_label: label,
    gantt_station_label: label,
    gantt_work_order_code: '空闲',
    gantt_station_badge_count: 0,
    gantt_station_badge_tone: 'idle',
    start,
    end,
    duration: durationDays(start, end),
    progress: 0,
    lazy: false,
    unscheduled: true,
    css: 'gantt-equipment-resource gantt-equipment-idle',
    class: 'gantt-equipment-resource gantt-equipment-idle',
  };
}

function buildEquipmentMergedTask(
  equipmentId: number,
  name: string,
  code: string | undefined,
  childTasks: GanttTask[],
  conflictCount: number
): GanttTask {
  const { start, end } = rangeFromTasks(childTasks);
  const codePrefix = code ? `${code} ` : '';
  const label = `${codePrefix}${name}`.trim();
  const tone = conflictCount > 0 ? 'conflict' : 'busy';

  return {
    id: equipmentResourceId(equipmentId),
    type: 'task',
    parent: 0,
    text: label,
    gantt_primary_label: label,
    gantt_station_label: label,
    gantt_station_badge_count: childTasks.length,
    gantt_station_badge_tone: tone,
    start,
    end,
    duration: durationDays(start, end),
    progress: 0,
    lazy: false,
    segments: childTasks.map((t) => {
      const operationId = parseOperationIdFromTaskId(t.id);
      return {
        start: t.start,
        end: t.end,
        duration: t.duration,
        text: [t.gantt_primary_label, t.gantt_work_order_code].filter(Boolean).join('\n'),
        title:
          t.title ||
          buildGanttNodeTooltip({
            workOrderCode: t.gantt_work_order_code,
            operationName: t.gantt_primary_label,
            equipmentName: t.assigned_equipment_name,
            start: t.start,
            end: t.end,
          }),
        gantt_primary_label: t.gantt_primary_label,
        gantt_work_order_code: t.gantt_work_order_code,
        operation_id: operationId ?? undefined,
        work_order_id: t.work_order_id,
        css: t.css,
        class: t.class,
        color: t.color,
        textColor: t.textColor,
      };
    }),
    css: [
      'gantt-equipment-merged',
      conflictCount > 0 ? 'gantt-equipment-overloaded' : '',
    ]
      .filter(Boolean)
      .join(' '),
    class: [
      'gantt-equipment-merged',
      conflictCount > 0 ? 'gantt-equipment-overloaded' : '',
    ]
      .filter(Boolean)
      .join(' '),
  };
}

export function workOrdersToEquipmentResourceGanttTasks(
  workOrders: WorkOrderForGantt[] | null | undefined,
  equipments: EquipmentResource[] | null | undefined,
  equipmentTypeFilter: string | 'all' = 'all'
): GanttTask[] {
  const matchesTypeFilter = (meta: EquipmentResource): boolean => {
    if (equipmentTypeFilter === 'all') return true;
    return String(meta.type || '').trim() === equipmentTypeFilter;
  };

  const safeWorkOrders = workOrders ?? [];
  const safeEquipments = equipments ?? [];
  const equipmentMeta = new Map<number, EquipmentResource>();
  for (const eq of safeEquipments) {
    if (eq.id > 0) equipmentMeta.set(eq.id, eq);
  }

  const opsByEquipment = new Map<
    number,
    Array<{ op: NonNullable<WorkOrderForGantt['operations']>[number]; wo: WorkOrderForGantt }>
  >();

  for (const wo of sortWorkOrdersForGantt(safeWorkOrders)) {
    for (const op of (wo.operations || []).filter((o) => o.id != null)) {
      const eid =
        op.assigned_equipment_id != null && Number(op.assigned_equipment_id) > 0
          ? Number(op.assigned_equipment_id)
          : null;
      if (eid == null) continue;

      if (!equipmentMeta.has(eid)) {
        equipmentMeta.set(eid, {
          id: eid,
          name: (op.assigned_equipment_name || '').trim() || `设备${eid}`,
          code: String(eid),
        });
      }
      if (!opsByEquipment.has(eid)) opsByEquipment.set(eid, []);
      opsByEquipment.get(eid)!.push({ op, wo });
    }
  }

  const orderedIds: number[] = [];
  const sortedMaster = [...safeEquipments]
    .filter((eq) => eq.id > 0)
    .sort((a, b) => String(a.code || a.name).localeCompare(String(b.code || b.name), 'zh-CN'));
  for (const eq of sortedMaster) {
    if (!orderedIds.includes(eq.id)) orderedIds.push(eq.id);
  }
  for (const eid of opsByEquipment.keys()) {
    if (eid > 0 && !orderedIds.includes(eid)) orderedIds.push(eid);
  }

  const tasks: GanttTask[] = [];
  for (const eid of orderedIds) {
    const meta = equipmentMeta.get(eid) ?? { id: eid, name: `设备${eid}`, code: String(eid) };
    if (!matchesTypeFilter(meta)) continue;
    const childrenInput = opsByEquipment.get(eid) ?? [];

    let childTasks = childrenInput.map(({ op, wo }) => {
      const task = operationToGanttTask(op, wo, 'station_child');
      return {
        ...task,
        type: 'task' as const,
        parent: equipmentResourceId(eid),
        assigned_equipment_name: meta.name,
      };
    });

    childTasks.sort((a, b) => a.start.getTime() - b.start.getTime() || String(a.id).localeCompare(String(b.id)));

    const overlapIds = findOverlappingTaskIds(childTasks);
    if (overlapIds.size > 0) {
      childTasks = childTasks.map((t) => {
        if (!overlapIds.has(String(t.id))) return t;
        return {
          ...t,
          css: 'gantt-task-red gantt-station-conflict',
          class: 'gantt-task-red gantt-station-conflict',
          color: '#ff4d4f',
          textColor: '#ffffff',
        };
      });
    }

    if (childTasks.length === 0) {
      tasks.push(buildEmptyEquipmentResourceRow(eid, meta.name, meta.code));
      continue;
    }
    tasks.push(buildEquipmentMergedTask(eid, meta.name, meta.code, childTasks, overlapIds.size));
  }

  return tasks;
}
