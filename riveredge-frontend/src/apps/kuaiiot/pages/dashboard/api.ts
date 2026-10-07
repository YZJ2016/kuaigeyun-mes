/**
 * 数采中心数据源聚合。各源独立成败：任一接口失败只影响对应分区，
 * 页面用 “— + 原因” 呈现，不用 0 冒充。
 */

import {
  getDiagnostics,
  getEquipmentOpsFeed,
  listAlerts,
  listMessageLogs,
  type AlertOut,
  type DiagnosticsOut,
  type EquipmentOpsFeed,
  type MessageLog,
} from '../../services/kuaiiot';

export type DashboardSourceKey = 'diagnostics' | 'alerts' | 'feed' | 'messages';

export type DashboardSources = {
  diagnostics?: DiagnosticsOut;
  alerts?: AlertOut[];
  feed?: EquipmentOpsFeed;
  messages?: MessageLog[];
  errors: Partial<Record<DashboardSourceKey, string>>;
};

function reasonOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '接口读取失败或无权限';
}

async function capture<T>(
  key: DashboardSourceKey,
  run: () => Promise<T>,
  errors: DashboardSources['errors'],
  apply: (value: T) => void,
): Promise<void> {
  try {
    apply(await run());
  } catch (error) {
    errors[key] = reasonOf(error);
  }
}

export async function loadDashboardSources(): Promise<DashboardSources> {
  const errors: DashboardSources['errors'] = {};
  const sources: DashboardSources = { errors };
  await Promise.all([
    capture('diagnostics', getDiagnostics, errors, (value) => {
      sources.diagnostics = value;
    }),
    capture('alerts', listAlerts, errors, (value) => {
      sources.alerts = Array.isArray(value) ? value : [];
    }),
    capture('feed', () => getEquipmentOpsFeed(24), errors, (value) => {
      sources.feed = value;
    }),
    capture('messages', () => listMessageLogs(), errors, (value) => {
      sources.messages = Array.isArray(value) ? value : [];
    }),
  ]);
  return sources;
}
