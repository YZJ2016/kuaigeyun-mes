/**
 * UniTabs 标签栏云端偏好（core_user_preferences.uni_tabs_state）
 *
 * 与 dashboard_quick_entries 同路径：按租户+用户存库，跨设备同步。
 * localStorage 仅作本机首帧镜像，真源为服务端偏好。
 */

import type { TabItem } from './tabsStorage';
import { getSavedActiveKey, getSavedTabs } from './tabsStorage';
import { readCachedPreferencesForCurrentUser } from './userPreferenceStore';

export const UNI_TABS_STATE_PREF_KEY = 'uni_tabs_state';

export interface UniTabsPreferenceState {
  tabs: TabItem[];
  activeKey?: string | null;
}

function isValidTabItem(raw: unknown): raw is TabItem {
  if (!raw || typeof raw !== 'object') return false;
  const tab = raw as TabItem;
  return (
    typeof tab.key === 'string'
    && tab.key.length > 0
    && typeof tab.path === 'string'
    && tab.path.length > 0
    && typeof tab.label === 'string'
    && tab.label.length > 0
  );
}

export function parseUniTabsPreferenceState(raw: unknown): UniTabsPreferenceState | null {
  if (!raw || typeof raw !== 'object') return null;
  const state = raw as UniTabsPreferenceState;
  if (!Array.isArray(state.tabs)) return null;
  const tabs = state.tabs.filter(isValidTabItem).map((tab) => ({
    key: tab.key,
    path: tab.path,
    label: tab.label,
    closable: tab.closable,
    pinned: Boolean(tab.pinned),
  }));
  if (tabs.length === 0) return null;
  const activeKey =
    typeof state.activeKey === 'string' && state.activeKey.trim() ? state.activeKey : null;
  return { tabs, activeKey };
}

export function serializeTabsForPreference(tabs: TabItem[]): TabItem[] {
  return tabs.map((tab) => ({
    key: tab.key,
    path: tab.path,
    label: tab.label,
    closable: tab.closable,
    pinned: Boolean(tab.pinned),
  }));
}

export function buildUniTabsPreferencePatch(
  tabs: TabItem[],
  activeKey: string | null | undefined,
): Record<string, UniTabsPreferenceState> {
  return {
    [UNI_TABS_STATE_PREF_KEY]: {
      tabs: serializeTabsForPreference(tabs),
      activeKey: activeKey || null,
    },
  };
}

export function readUniTabsStateFromPreferences(
  preferences: Record<string, unknown> | null | undefined,
): UniTabsPreferenceState | null {
  if (!preferences) return null;
  return parseUniTabsPreferenceState(preferences[UNI_TABS_STATE_PREF_KEY]);
}

export function readUniTabsStateFromPreferenceCache(): UniTabsPreferenceState | null {
  const cached = readCachedPreferencesForCurrentUser();
  return readUniTabsStateFromPreferences(cached);
}

/** 云端无数据时，从本机 legacy localStorage 组装一次性迁移 payload */
export function buildLegacyLocalTabsMigrationPatch(): Record<string, UniTabsPreferenceState> | null {
  const legacyTabs = getSavedTabs();
  if (!legacyTabs.length) return null;
  return buildUniTabsPreferencePatch(legacyTabs, getSavedActiveKey());
}
