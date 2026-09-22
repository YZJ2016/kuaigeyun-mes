/**
 * 标签栏本机镜像（首帧 / 离线占位）
 *
 * 真源：core_user_preferences.uni_tabs_state（见 uniTabsPreference.ts）
 * 按租户+用户隔离；读取时兼容旧版仅按租户命名的 key。
 */

import { getTenantId } from '../utils/auth';
import { getSessionCurrentUser } from '../utils/sessionCurrentUser';

function getStorageScopeSuffix(): string {
  const tenantId = getTenantId();
  const user = getSessionCurrentUser();
  const userId = user?.id ?? user?.user_id ?? user?.uuid;
  if (tenantId != null && userId != null) {
    return `_t${tenantId}_u${userId}`;
  }
  if (tenantId != null) {
    return `_t${tenantId}`;
  }
  return '';
}

function getTabsKey(): string {
  const suffix = getStorageScopeSuffix();
  return suffix ? `riveredge_saved_tabs${suffix}` : 'riveredge_saved_tabs';
}

function getActiveKeyStorageKey(): string {
  const suffix = getStorageScopeSuffix();
  return suffix ? `riveredge_saved_active_key${suffix}` : 'riveredge_saved_active_key';
}

function getLegacyTenantTabsKey(): string | null {
  const tenantId = getTenantId();
  if (tenantId == null) return null;
  return `riveredge_saved_tabs_t${tenantId}`;
}

function getLegacyTenantActiveKey(): string | null {
  const tenantId = getTenantId();
  if (tenantId == null) return null;
  return `riveredge_saved_active_key_t${tenantId}`;
}

export interface TabItem {
  key: string;
  path: string;
  label: string;
  closable?: boolean;
  pinned?: boolean;
}

export function getSavedTabs(): TabItem[] {
  if (typeof window === 'undefined') return [];
  try {
    const readKey = (key: string): TabItem[] => {
      const raw = localStorage.getItem(key);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    };

    const scoped = readKey(getTabsKey());
    if (scoped.length) return scoped;

    const legacyKey = getLegacyTenantTabsKey();
    if (legacyKey) {
      return readKey(legacyKey);
    }
    return [];
  } catch {
    return [];
  }
}

export function setSavedTabs(tabs: TabItem[]): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(getTabsKey(), JSON.stringify(tabs));
  } catch {
    // ignore
  }
}

export function getSavedActiveKey(): string | null {
  if (typeof window === 'undefined') return null;
  const scoped = localStorage.getItem(getActiveKeyStorageKey());
  if (scoped) return scoped;
  const legacyKey = getLegacyTenantActiveKey();
  if (legacyKey) {
    return localStorage.getItem(legacyKey);
  }
  return null;
}

export function setSavedActiveKey(key: string | null): void {
  if (typeof window === 'undefined') return;
  const storageKey = getActiveKeyStorageKey();
  if (key) {
    localStorage.setItem(storageKey, key);
  } else {
    localStorage.removeItem(storageKey);
  }
}

/** 清除本机镜像（切换租户 / 主题重置）；不删云端 uni_tabs_state */
export function clearTabsData(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(getTabsKey());
    localStorage.removeItem(getActiveKeyStorageKey());
    const legacyTabsKey = getLegacyTenantTabsKey();
    const legacyActiveKey = getLegacyTenantActiveKey();
    if (legacyTabsKey) localStorage.removeItem(legacyTabsKey);
    if (legacyActiveKey) localStorage.removeItem(legacyActiveKey);
  } catch {
    // ignore
  }
}
