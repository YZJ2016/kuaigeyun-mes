/**
 * 列表工具栏「同步 / 推送」显隐：按角色功能权限（:sync / :push），不再走业务配置。
 *
 * 在「角色权限」中勾选对应资源的「显示同步」「显示推送」即可控制。
 * 业务配置里的 toolbar_*_enabled 已废弃，勿再写入。
 */
import { useMemo } from 'react';
import { useResourcePermissions } from './useResourcePermissions';

/** @deprecated 仅为历史 import 兼容；实际是 businessConfig 缓存 key */
export const TOOLBAR_SYNC_PUSH_FLAGS_QUERY_KEY = ['businessConfig'] as const;

/** @deprecated 配置中心广播事件名，其它仍读 businessConfig 的页面可继续用 */
export const BUSINESS_CONFIG_UPDATED_EVENT = 'riveredge:business-config-updated';

export type ToolbarSyncPushFlags = {
  syncEnabled: boolean;
  pushEnabled: boolean;
  /** 任一开启时工具栏按钮可见（SyncPushHub） */
  hubVisible: boolean;
};

/** 与各列表页 useResourcePermissions 资源前缀一致 */
export type ToolbarSyncPushResource =
  | 'kuaizhizao:work-order'
  | 'kuaizhizao:production-execution-reporting'
  | 'kuaizhizao:sales-order'
  | 'kuaizhizao:purchase-order'
  | 'kuaizhizao:inventory';

/** @deprecated 旧 category 名 → 资源前缀（兼容未改完的调用） */
const CATEGORY_TO_RESOURCE: Record<string, ToolbarSyncPushResource> = {
  work_order: 'kuaizhizao:work-order',
  reporting: 'kuaizhizao:production-execution-reporting',
  sales: 'kuaizhizao:sales-order',
  purchase: 'kuaizhizao:purchase-order',
  warehouse: 'kuaizhizao:inventory',
};

export function resolveToolbarSyncPushResource(
  resourceOrCategory: string,
): string {
  const raw = (resourceOrCategory || '').trim();
  if (raw.includes(':')) return raw;
  return CATEGORY_TO_RESOURCE[raw] || raw;
}

export function resolveToolbarSyncPushFlagsFromPerms(
  canAction: ((action: string) => boolean) | undefined,
): ToolbarSyncPushFlags {
  const check = canAction || (() => false);
  const syncEnabled = Boolean(check('sync'));
  const pushEnabled = Boolean(check('push'));
  return {
    syncEnabled,
    pushEnabled,
    hubVisible: syncEnabled || pushEnabled,
  };
}

export function useToolbarSyncPushFlags(
  resourceOrCategory: ToolbarSyncPushResource | string,
): ToolbarSyncPushFlags {
  const resource = resolveToolbarSyncPushResource(resourceOrCategory);
  const perms = useResourcePermissions(resource);
  return useMemo(
    () => resolveToolbarSyncPushFlagsFromPerms(perms.canAction),
    [perms.canAction],
  );
}

/** 写入 React Query businessConfig 缓存并广播（配置中心其它参数仍用） */
export function syncBusinessConfigQueryCache(
  queryClient: import('@tanstack/react-query').QueryClient,
  config: import('../services/businessConfig').BusinessConfig,
): void {
  queryClient.setQueryData(TOOLBAR_SYNC_PUSH_FLAGS_QUERY_KEY, config);
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(BUSINESS_CONFIG_UPDATED_EVENT, { detail: config }),
  );
  try {
    window.localStorage.setItem(
      'riveredge:business-config-cache',
      JSON.stringify({ ts: Date.now(), config }),
    );
  } catch {
    // ignore
  }
}

export function patchBusinessConfigQueryCache(
  queryClient: import('@tanstack/react-query').QueryClient,
  patch: Record<string, Record<string, unknown>>,
  fallback?: import('../services/businessConfig').BusinessConfig | null,
): import('../services/businessConfig').BusinessConfig {
  type BusinessConfig = import('../services/businessConfig').BusinessConfig;
  const prev = queryClient.getQueryData<BusinessConfig>(TOOLBAR_SYNC_PUSH_FLAGS_QUERY_KEY);
  const base = prev?.parameters || fallback?.parameters || {};
  const nextParameters: Record<string, Record<string, unknown>> = { ...base };
  for (const [cat, catPatch] of Object.entries(patch)) {
    nextParameters[cat] = {
      ...(nextParameters[cat] || {}),
      ...catPatch,
    };
  }
  const next: BusinessConfig = {
    ...(prev || fallback || { parameters: {} }),
    parameters: nextParameters as BusinessConfig['parameters'],
  };
  syncBusinessConfigQueryCache(queryClient, next);
  return next;
}
