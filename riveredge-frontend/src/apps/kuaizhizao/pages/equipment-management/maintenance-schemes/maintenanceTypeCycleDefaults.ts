/**
 * 设备保养方案：周期类型 / 维护类型默认周期（与后端 constants/maintenance_scheme 对齐）。
 * 仅用于表单预填，允许用户改。
 */

export const CYCLE_TYPE_TIME = '按时间';
export const CYCLE_TYPE_RUNTIME = '按运行时长';
export const CYCLE_TYPE_COUNT = '按使用次数';

/** 仅「按时间」使用的日历维护类型 → 默认周期 */
export const MAINTENANCE_TYPE_DEFAULT_CYCLE: Record<
  string,
  { cycle_value: number; cycle_unit: string }
> = {
  日常保养: { cycle_value: 1, cycle_unit: '天' },
  月度: { cycle_value: 1, cycle_unit: '月' },
  季度: { cycle_value: 3, cycle_unit: '月' },
  半年度: { cycle_value: 6, cycle_unit: '月' },
  年度: { cycle_value: 1, cycle_unit: '年' },
};

/** 「按运行时长 / 按使用次数」各自默认周期 */
export const CYCLE_TYPE_DEFAULTS: Record<
  string,
  { cycle_value: number; cycle_unit: string }
> = {
  [CYCLE_TYPE_RUNTIME]: { cycle_value: 100, cycle_unit: '小时' },
  [CYCLE_TYPE_COUNT]: { cycle_value: 100, cycle_unit: '次' },
};

export const TIME_CYCLE_UNITS = ['天', '周', '月', '年'] as const;

export function resolveMaintenanceTypeDefaultCycle(maintenanceType?: string | null): {
  cycle_value: number;
  cycle_unit: string;
} | null {
  const key = String(maintenanceType || '').trim();
  return MAINTENANCE_TYPE_DEFAULT_CYCLE[key] ?? null;
}

export function resolveCycleTypeDefault(cycleType?: string | null): {
  cycle_value: number;
  cycle_unit: string;
} | null {
  const key = String(cycleType || '').trim();
  return CYCLE_TYPE_DEFAULTS[key] ?? null;
}

export function isTimeCycleType(cycleType?: string | null): boolean {
  return String(cycleType || '').trim() === CYCLE_TYPE_TIME;
}
