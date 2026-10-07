/**
 * 告警中心页面封装：设备名映射、串行批删、规则条件展示。
 * 规则/记录仍直接调 services/kuaiiot 的原始端点，不改接口契约。
 */

import { listDevices, type AlertOut, type AlertRuleOut } from '../../services/kuaiiot';

/** 记录视图行类型：与服务端 AlertOut 一致，别名仅为页面语义清晰。 */
export type AlertRecordRow = AlertOut;

export type DeviceLabelMap = Map<number, string>;

/** 设备 id → “名称 (编码)”。无 device:display 权限时抛错，调用方回退编号展示。 */
export async function loadDeviceLabelMap(): Promise<DeviceLabelMap> {
  const devices = await listDevices();
  const map: DeviceLabelMap = new Map();
  for (const device of devices || []) {
    map.set(device.id, `${device.name} (${device.code})`);
  }
  return map;
}

export function deviceLabel(map: DeviceLabelMap, id?: number | null): string {
  if (id == null) return '—';
  return map.get(id) ?? `设备 #${id}`;
}

/** 比较符与后端 alert_threshold_resolver.OPERATORS 一致（gt/lt/gte/lte/eq/ne）。 */
export const ALERT_OPERATOR_OPTIONS = [
  { value: 'gt', label: '> 大于' },
  { value: 'lt', label: '< 小于' },
  { value: 'gte', label: '≥ 大于等于' },
  { value: 'lte', label: '≤ 小于等于' },
  { value: 'eq', label: '= 等于' },
  { value: 'ne', label: '≠ 不等于' },
];

const OPERATOR_SYMBOL: Record<string, string> = {
  gt: '>',
  lt: '<',
  gte: '≥',
  lte: '≤',
  eq: '=',
  ne: '≠',
};

export function formatRuleCondition(
  rule: Pick<AlertRuleOut, 'operator' | 'threshold_number' | 'threshold_text'>,
): string {
  const symbol = OPERATOR_SYMBOL[rule.operator] ?? rule.operator ?? '';
  const threshold = rule.threshold_number ?? rule.threshold_text;
  if (threshold === null || threshold === undefined || threshold === '') return symbol || '—';
  return `${symbol} ${threshold}`;
}

/** 严重级别选项：与 status-tags.tsx 的 SEVERITY 文案一致。 */
export const ALERT_SEVERITY_OPTIONS = [
  { value: 'info', label: '提示' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' },
];

/** 告警记录状态选项：与 status-tags.tsx 的 ALERT_STATUS 文案一致。 */
export const ALERT_STATUS_OPTIONS = [
  { value: 'open', label: '未确认' },
  { value: 'acknowledged', label: '已确认' },
  { value: 'recovered', label: '已恢复' },
  { value: 'closed', label: '已处置' },
];

export type SerialDeleteResult<T> = {
  done: T[];
  failed?: { item: T; message: string };
};

/** 串行逐条软删：任一失败即停并返回明细；已成功项不回滚（与 spec 契约一致）。 */
export async function deleteRowsInSequence<T>(
  rows: T[],
  deleteOne: (row: T) => Promise<unknown>,
): Promise<SerialDeleteResult<T>> {
  const done: T[] = [];
  for (const row of rows) {
    try {
      await deleteOne(row);
      done.push(row);
    } catch (error) {
      return {
        done,
        failed: {
          item: row,
          message: error instanceof Error ? error.message : '删除失败',
        },
      };
    }
  }
  return { done };
}
