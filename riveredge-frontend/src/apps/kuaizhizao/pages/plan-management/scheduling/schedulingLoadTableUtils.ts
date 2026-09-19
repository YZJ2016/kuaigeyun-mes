import type { VisualSchedulingBoardScan } from '../../../services/production';
import type { GanttTaskLevel, WorkOrderForGantt } from '../../../components/GanttSchedulingChart/types';

export interface SchedulingLoadTableRow {
  resourceId: number;
  resourceName: string;
  scheduledHours: number;
  availableHours: number;
  loadRate: number;
  overloaded: boolean;
  workOrderCount: number;
  onMachineCount: number;
}

type LoadStationRow = NonNullable<VisualSchedulingBoardScan['load_by_station']>[number];
type LoadWorkCenterRow = VisualSchedulingBoardScan['load_by_work_center'][number];

function inferDailyCapacityHours(rows: Array<{ hours: number; rate: number }>): number {
  for (const row of rows) {
    const hours = Number(row.hours ?? 0);
    const rate = Number(row.rate ?? 0);
    if (hours > 0 && rate > 0) {
      return hours / (rate / 100);
    }
  }
  return 8;
}

function countWorkOrdersForStation(stationId: number, workOrders: WorkOrderForGantt[]): number {
  const ids = new Set<number>();
  for (const wo of workOrders) {
    for (const op of wo.operations ?? []) {
      if (op.assigned_station_id === stationId && wo.id > 0) {
        ids.add(wo.id);
      }
    }
  }
  return ids.size;
}

function countWorkOrdersForWorkCenter(workCenterId: number, workOrders: WorkOrderForGantt[]): number {
  const ids = new Set<number>();
  for (const wo of workOrders) {
    if (wo.work_center_id === workCenterId && wo.id > 0) {
      ids.add(wo.id);
      continue;
    }
    for (const op of wo.operations ?? []) {
      if (op.work_center_id === workCenterId && wo.id > 0) {
        ids.add(wo.id);
      }
    }
  }
  return ids.size;
}

function countOnMachineForStation(stationId: number, workOrders: WorkOrderForGantt[]): number {
  let count = 0;
  for (const wo of workOrders) {
    for (const op of wo.operations ?? []) {
      if (op.assigned_station_id === stationId && op.machine_session_state === 'on_machine') {
        count += 1;
      }
    }
  }
  return count;
}

function countOnMachineForWorkCenter(workCenterId: number, workOrders: WorkOrderForGantt[]): number {
  let count = 0;
  for (const wo of workOrders) {
    for (const op of wo.operations ?? []) {
      if (op.work_center_id === workCenterId && op.machine_session_state === 'on_machine') {
        count += 1;
      }
    }
  }
  return count;
}

function aggregateStationRows(
  rows: LoadStationRow[],
  horizonDays: number,
  workOrders: WorkOrderForGantt[]
): SchedulingLoadTableRow[] {
  const byStation = new Map<number, LoadStationRow[]>();
  for (const row of rows) {
    const id = Number(row.station_id);
    if (!byStation.has(id)) byStation.set(id, []);
    byStation.get(id)!.push(row);
  }

  const result: SchedulingLoadTableRow[] = [];
  for (const [stationId, stationRows] of byStation) {
    const scheduledHours = stationRows.reduce((sum, row) => sum + Number(row.hours ?? 0), 0);
    const dailyCapacity = inferDailyCapacityHours(stationRows);
    const dayCount = new Set(stationRows.map((row) => row.day)).size || horizonDays;
    const availableHours = dailyCapacity * dayCount;
    const loadRate = availableHours > 0 ? Math.round((scheduledHours / availableHours) * 100) : 0;
    result.push({
      resourceId: stationId,
      resourceName: stationRows[0]?.station_name || `工位${stationId}`,
      scheduledHours: Math.round(scheduledHours * 100) / 100,
      availableHours: Math.round(availableHours * 100) / 100,
      loadRate,
      overloaded: stationRows.some((row) => row.overloaded) || loadRate > 100,
      workOrderCount: countWorkOrdersForStation(stationId, workOrders),
      onMachineCount: countOnMachineForStation(stationId, workOrders),
    });
  }
  return result.sort((a, b) => b.loadRate - a.loadRate || a.resourceName.localeCompare(b.resourceName));
}

function aggregateWorkCenterRows(
  rows: LoadWorkCenterRow[],
  horizonDays: number,
  workOrders: WorkOrderForGantt[]
): SchedulingLoadTableRow[] {
  const byWc = new Map<number, LoadWorkCenterRow[]>();
  for (const row of rows) {
    const id = Number(row.work_center_id);
    if (!byWc.has(id)) byWc.set(id, []);
    byWc.get(id)!.push(row);
  }

  const result: SchedulingLoadTableRow[] = [];
  for (const [wcId, wcRows] of byWc) {
    const scheduledHours = wcRows.reduce((sum, row) => sum + Number(row.hours ?? 0), 0);
    const dailyCapacity = inferDailyCapacityHours(wcRows);
    const dayCount = new Set(wcRows.map((row) => row.day)).size || horizonDays;
    const availableHours = dailyCapacity * dayCount;
    const loadRate = availableHours > 0 ? Math.round((scheduledHours / availableHours) * 100) : 0;
    result.push({
      resourceId: wcId,
      resourceName: wcRows[0]?.work_center_name || `工作中心${wcId}`,
      scheduledHours: Math.round(scheduledHours * 100) / 100,
      availableHours: Math.round(availableHours * 100) / 100,
      loadRate,
      overloaded: wcRows.some((row) => row.overloaded) || loadRate > 100,
      workOrderCount: countWorkOrdersForWorkCenter(wcId, workOrders),
      onMachineCount: countOnMachineForWorkCenter(wcId, workOrders),
    });
  }
  return result.sort((a, b) => b.loadRate - a.loadRate || a.resourceName.localeCompare(b.resourceName));
}

export function buildSchedulingLoadTableRows(
  boardScan: VisualSchedulingBoardScan | null | undefined,
  taskLevel: GanttTaskLevel,
  horizonDays: number,
  workOrders: WorkOrderForGantt[]
): SchedulingLoadTableRow[] {
  if (!boardScan) return [];
  if (taskLevel === 'station') {
    return aggregateStationRows(boardScan.load_by_station ?? [], horizonDays, workOrders);
  }
  if (taskLevel === 'equipment') {
    return aggregateWorkCenterRows(boardScan.load_by_work_center ?? [], horizonDays, workOrders);
  }
  return [];
}
