import type { TFunction } from 'i18next';
import type { UserDisplayRoleItem } from '../../../../../services/user';
import type { EquipmentResource } from '../../../components/GanttSchedulingChart/equipmentResourceUtils';
import type { WorkerResource } from '../../../components/GanttSchedulingChart/workerResourceUtils';

export type SchedulingResourceFilterValue = 'all' | string;

export const SCHEDULING_EQUIPMENT_TYPE_VALUES = ['加工设备', '检测设备', '包装设备', '其他'] as const;

export interface SchedulingEquipmentResource extends EquipmentResource {
  type?: string;
}

export interface SchedulingWorkerRoleRef {
  uuid: string;
  name: string;
}

export interface SchedulingWorkerResource extends WorkerResource {
  roles?: SchedulingWorkerRoleRef[];
  roleUuids?: string[];
}

const EQUIPMENT_TYPE_I18N: Record<(typeof SCHEDULING_EQUIPMENT_TYPE_VALUES)[number], string> = {
  加工设备: 'pages.system.equipment.typeProcessing',
  检测设备: 'pages.system.equipment.typeInspection',
  包装设备: 'pages.system.equipment.typePackaging',
  其他: 'pages.system.equipment.typeOther',
};

export function resolveUserRoles(
  roles: UserDisplayRoleItem[] | null | undefined
): SchedulingWorkerRoleRef[] {
  const out: SchedulingWorkerRoleRef[] = [];
  const seen = new Set<string>();
  for (const role of roles ?? []) {
    const uuid = String(role.uuid || '').trim();
    const name = String(role.name || '').trim();
    if (!uuid || !name || seen.has(uuid)) continue;
    seen.add(uuid);
    out.push({ uuid, name });
  }
  return out.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
}

export function buildSchedulingEquipmentTypeFilterOptions(t: TFunction) {
  return [
    { value: 'all', label: t('app.kuaizhizao.scheduling.ganttToolbar.resourceFilterAll') },
    ...SCHEDULING_EQUIPMENT_TYPE_VALUES.map((value) => ({
      value,
      label: t(EQUIPMENT_TYPE_I18N[value]),
    })),
  ];
}

export function buildSchedulingWorkerRoleFilterOptions(
  workers: SchedulingWorkerResource[],
  t: TFunction
) {
  const roleMap = new Map<string, string>();
  for (const worker of workers) {
    for (const role of worker.roles ?? []) {
      if (role.uuid && role.name) {
        roleMap.set(role.uuid, role.name);
      }
    }
  }
  return [
    { value: 'all', label: t('app.kuaizhizao.scheduling.ganttToolbar.resourceFilterAll') },
    ...[...roleMap.entries()]
      .sort((a, b) => a[1].localeCompare(b[1], 'zh-CN'))
      .map(([uuid, name]) => ({ value: uuid, label: name })),
  ];
}

export function matchesEquipmentTypeFilter(
  equipment: Pick<SchedulingEquipmentResource, 'type'>,
  filter: SchedulingResourceFilterValue
): boolean {
  if (filter === 'all') return true;
  return String(equipment.type || '').trim() === filter;
}

export function matchesWorkerRoleFilter(
  worker: Pick<SchedulingWorkerResource, 'roleUuids'>,
  filter: SchedulingResourceFilterValue
): boolean {
  if (filter === 'all') return true;
  return (worker.roleUuids ?? []).includes(filter);
}

export function filterSchedulingEquipments(
  equipments: SchedulingEquipmentResource[],
  filter: SchedulingResourceFilterValue
): SchedulingEquipmentResource[] {
  if (filter === 'all') return equipments;
  return equipments.filter((item) => matchesEquipmentTypeFilter(item, filter));
}

export function filterSchedulingWorkers(
  workers: SchedulingWorkerResource[],
  filter: SchedulingResourceFilterValue
): SchedulingWorkerResource[] {
  if (filter === 'all') return workers;
  return workers.filter((item) => matchesWorkerRoleFilter(item, filter));
}
