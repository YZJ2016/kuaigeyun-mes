/**
 * 人员资源型甘特：每个人员一行，同人员多道工序在同一行按时间轴分段展示。
 */

import dayjs from 'dayjs';
import type { WorkOrderForGantt, GanttTask } from './types';
import { buildGanttNodeTooltip, operationToGanttTask, sortWorkOrdersForGantt } from './utils';
import { findOverlappingTaskIds } from './stationResourceUtils';

const DEFAULT_START_HOUR = 8;
const DEFAULT_END_HOUR = 17;

export interface WorkerResource {
  id: number;
  name: string;
  code?: string;
  roleUuids?: string[];
}

export function workerResourceId(workerId: number): string {
  return `wk-${workerId}`;
}

export function isWorkerResourceTaskId(id: number | string): boolean {
  return String(id).startsWith('wk-');
}

export function parseWorkerIdFromResourceRow(id: number | string): number | null {
  const m = String(id).match(/^wk-(\d+)$/i);
  if (!m) return null;
  const parsed = Number(m[1]);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

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

export function resolveWorkerIdsForOperation(
  op: NonNullable<WorkOrderForGantt['operations']>[number]
): number[] {
  const fromList = Array.isArray(op.assigned_worker_ids)
    ? op.assigned_worker_ids
        .map((id) => Number(id))
        .filter((id) => Number.isInteger(id) && id > 0)
    : [];
  if (fromList.length > 0) return [...new Set(fromList)];
  const single = Number(op.assigned_worker_id);
  if (Number.isInteger(single) && single > 0) return [single];
  return [];
}

function formatWorkerRowLabel(name: string, code?: string): string {
  const displayName = name.trim();
  if (displayName) return displayName;
  return (code || '').trim() || '—';
}

function buildEmptyWorkerResourceRow(workerId: number, name: string, code?: string): GanttTask {
  const { start, end } = defaultDayRange();
  const label = formatWorkerRowLabel(name, code);
  return {
    id: workerResourceId(workerId),
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
    css: 'gantt-worker-resource gantt-worker-idle',
    class: 'gantt-worker-resource gantt-worker-idle',
  };
}

function buildWorkerMergedTask(
  workerId: number,
  name: string,
  code: string | undefined,
  childTasks: GanttTask[],
  conflictCount: number
): GanttTask {
  const { start, end } = rangeFromTasks(childTasks);
  const label = formatWorkerRowLabel(name, code);
  const tone = conflictCount > 0 ? 'conflict' : 'busy';

  return {
    id: workerResourceId(workerId),
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
    css: ['gantt-worker-merged', conflictCount > 0 ? 'gantt-worker-overloaded' : '']
      .filter(Boolean)
      .join(' '),
    class: ['gantt-worker-merged', conflictCount > 0 ? 'gantt-worker-overloaded' : '']
      .filter(Boolean)
      .join(' '),
  };
}

export function workOrdersToWorkerResourceGanttTasks(
  workOrders: WorkOrderForGantt[] | null | undefined,
  workers: WorkerResource[] | null | undefined,
  workerRoleFilter: string | 'all' = 'all'
): GanttTask[] {
  const matchesRoleFilter = (meta: WorkerResource): boolean => {
    if (workerRoleFilter === 'all') return true;
    return (meta.roleUuids ?? []).includes(workerRoleFilter);
  };

  const safeWorkOrders = workOrders ?? [];
  const safeWorkers = workers ?? [];
  const workerMeta = new Map<number, WorkerResource>();
  for (const w of safeWorkers) {
    if (w.id > 0) workerMeta.set(w.id, w);
  }

  const opsByWorker = new Map<
    number,
    Array<{ op: NonNullable<WorkOrderForGantt['operations']>[number]; wo: WorkOrderForGantt }>
  >();

  for (const wo of sortWorkOrdersForGantt(safeWorkOrders)) {
    for (const op of (wo.operations || []).filter((o) => o.id != null)) {
      const workerIds = resolveWorkerIdsForOperation(op);
      for (const wid of workerIds) {
        if (!workerMeta.has(wid)) {
          workerMeta.set(wid, {
            id: wid,
            name: (op.assigned_worker_name || '').trim().split('、')[0] || `人员${wid}`,
            code: String(wid),
            roleUuids: [],
          });
        }
        if (!opsByWorker.has(wid)) opsByWorker.set(wid, []);
        opsByWorker.get(wid)!.push({ op, wo });
      }
    }
  }

  const orderedIds: number[] = [];
  const sortedMaster = [...safeWorkers]
    .filter((w) => w.id > 0)
    .sort((a, b) => String(a.code || a.name).localeCompare(String(b.code || b.name), 'zh-CN'));
  for (const w of sortedMaster) {
    if (!orderedIds.includes(w.id)) orderedIds.push(w.id);
  }
  for (const wid of opsByWorker.keys()) {
    if (wid > 0 && !orderedIds.includes(wid)) orderedIds.push(wid);
  }

  const tasks: GanttTask[] = [];
  for (const wid of orderedIds) {
    const meta = workerMeta.get(wid) ?? { id: wid, name: `人员${wid}`, code: String(wid), roleUuids: [] };
    if (!matchesRoleFilter(meta)) continue;
    const childrenInput = opsByWorker.get(wid) ?? [];

    let childTasks = childrenInput.map(({ op, wo }) => {
      const task = operationToGanttTask(op, wo, 'station_child');
      return {
        ...task,
        type: 'task' as const,
        parent: workerResourceId(wid),
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
      tasks.push(buildEmptyWorkerResourceRow(wid, meta.name, meta.code));
      continue;
    }
    tasks.push(buildWorkerMergedTask(wid, meta.name, meta.code, childTasks, overlapIds.size));
  }

  return tasks;
}
