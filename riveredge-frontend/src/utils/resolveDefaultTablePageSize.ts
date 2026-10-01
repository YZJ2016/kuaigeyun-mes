/**
 * 表格默认每页条数唯一解析路径（UniTable / UniReport 共用）。
 *
 * 优先级：页面显式 override → 个人偏好（仅当用户显式设置）→ 站点 ui.default_page_size → 20
 * 禁止页面再写死 pagination.defaultPageSize: 20 盖掉站点配置。
 */

import { useConfigStore } from '../stores/configStore';
import { useUserPreferenceStore } from '../stores/userPreferenceStore';

const FALLBACK_PAGE_SIZE = 20;

function toPositivePageSize(value: unknown): number | undefined {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.floor(n);
}

/** 个人偏好里是否显式写了每页条数（null/undefined 视为跟随站点） */
export function readExplicitPreferenceTablePageSize(
  preferences: Record<string, unknown> | null | undefined,
): number | undefined {
  const ui = preferences?.ui;
  if (!ui || typeof ui !== 'object' || Array.isArray(ui)) return undefined;
  if (!Object.prototype.hasOwnProperty.call(ui, 'default_page_size')) return undefined;
  return toPositivePageSize((ui as Record<string, unknown>).default_page_size);
}

export function resolveDefaultTablePageSize(override?: number): number {
  const fromOverride = toPositivePageSize(override);
  if (fromOverride != null) return fromOverride;

  const fromPreference = readExplicitPreferenceTablePageSize(
    useUserPreferenceStore.getState().preferences,
  );
  if (fromPreference != null) return fromPreference;

  const fromConfig = toPositivePageSize(
    useConfigStore.getState().getConfig('ui.default_page_size', FALLBACK_PAGE_SIZE),
  );
  return fromConfig ?? FALLBACK_PAGE_SIZE;
}
