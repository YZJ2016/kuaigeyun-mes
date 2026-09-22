import type { GanttTaskLevel } from '../../../components/GanttSchedulingChart/types';

const STORAGE_KEY = 'kuaizhizao.scheduling.pinnedResources.v1';

export type SchedulingPinnedResourceKind = 'station' | 'equipment' | 'worker';

export interface SchedulingPinnedResources {
  stationIds: number[];
  equipmentIds: number[];
  workerIds: number[];
}

export const EMPTY_PINNED_RESOURCES: SchedulingPinnedResources = {
  stationIds: [],
  equipmentIds: [],
  workerIds: [],
};

export function loadSchedulingPinnedResources(): SchedulingPinnedResources {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...EMPTY_PINNED_RESOURCES };
    const parsed = JSON.parse(raw) as Partial<SchedulingPinnedResources>;
    return {
      stationIds: Array.isArray(parsed.stationIds)
        ? parsed.stationIds.map(Number).filter((id) => Number.isInteger(id) && id > 0)
        : [],
      equipmentIds: Array.isArray(parsed.equipmentIds)
        ? parsed.equipmentIds.map(Number).filter((id) => Number.isInteger(id) && id > 0)
        : [],
      workerIds: Array.isArray(parsed.workerIds)
        ? parsed.workerIds.map(Number).filter((id) => Number.isInteger(id) && id > 0)
        : [],
    };
  } catch {
    return { ...EMPTY_PINNED_RESOURCES };
  }
}

export function saveSchedulingPinnedResources(value: SchedulingPinnedResources): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

export function pinnedIdsForLevel(
  pinned: SchedulingPinnedResources,
  level: GanttTaskLevel
): number[] {
  if (level === 'station') return pinned.stationIds;
  if (level === 'equipment') return pinned.equipmentIds;
  if (level === 'worker') return pinned.workerIds;
  return [];
}

export function togglePinnedResourceId(
  pinned: SchedulingPinnedResources,
  level: GanttTaskLevel,
  resourceId: number
): SchedulingPinnedResources {
  const id = Number(resourceId);
  if (!Number.isInteger(id) || id <= 0) return pinned;
  if (level === 'station') {
    const set = new Set(pinned.stationIds);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    return { ...pinned, stationIds: [...set] };
  }
  if (level === 'equipment') {
    const set = new Set(pinned.equipmentIds);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    return { ...pinned, equipmentIds: [...set] };
  }
  if (level === 'worker') {
    const set = new Set(pinned.workerIds);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    return { ...pinned, workerIds: [...set] };
  }
  return pinned;
}
