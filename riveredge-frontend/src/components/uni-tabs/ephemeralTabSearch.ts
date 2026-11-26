import { isCreateTabKey } from './isCreateTabKey';

/**
 * 仅用于页签 path 持久化与页签点击导航；不修改地址栏 live search。
 * 列表页深链 handoff 读 query 后会在页面内 replace 清参，但 tab.path 可能先落库。
 */
export const EPHEMERAL_TAB_SEARCH_PARAM_KEYS = [
  'pullFromDemandComputationId',
  'pullFromSalesOrderId',
] as const;

export function stripEphemeralTabSearchParams(pathOrTabKey: string): string {
  const qIndex = pathOrTabKey.indexOf('?');
  if (qIndex < 0) {
    return pathOrTabKey;
  }
  const pathname = pathOrTabKey.slice(0, qIndex);
  const params = new URLSearchParams(pathOrTabKey.slice(qIndex + 1));
  let changed = false;
  for (const key of EPHEMERAL_TAB_SEARCH_PARAM_KEYS) {
    if (params.has(key)) {
      params.delete(key);
      changed = true;
    }
  }
  if (!changed) {
    return pathOrTabKey;
  }
  const search = params.toString();
  return search ? `${pathname}?${search}` : pathname;
}

/** 列表页存入 tab.path 前应去掉一次性下推深链参数；建单页保留完整 query。 */
export function normalizeListTabStoredPath(path: string): string {
  if (isCreateTabKey(path)) {
    return path;
  }
  return stripEphemeralTabSearchParams(path);
}

export function sanitizePersistedListTab(tab: { key: string; path: string }): {
  key: string;
  path: string;
} {
  if (isCreateTabKey(tab.key)) {
    return tab;
  }
  const pathname = (tab.key.split('?')[0] || '/').replace(/\/$/, '') || '/';
  return {
    key: tab.key.includes('?') ? pathname : tab.key,
    path: normalizeListTabStoredPath(tab.path),
  };
}

export function sanitizePersistedTabItems<T extends { key: string; path: string }>(tabs: T[]): T[] {
  return tabs.map((tab) => {
    const { key, path } = sanitizePersistedListTab(tab);
    return key === tab.key && path === tab.path ? tab : { ...tab, key, path };
  });
}