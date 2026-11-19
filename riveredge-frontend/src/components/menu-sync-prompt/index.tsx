/**
 * 租户管理员：manifest 与库内菜单不一致时，右下角通知征求同意后再同步。
 * 「立即同步」实际执行：扫描应用 + 一键同步菜单。不阻断操作；禁止读路径静默写库。
 */

import React, { useEffect, useRef } from 'react';
import { App, Button, Space } from 'antd';
import { SyncOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  getMenuSyncStatus,
  scanApplications,
  syncAllManifestsAndMenus,
  MENU_SYNC_STATUS_QUERY_KEY,
} from '../../services/application';
import { getBootstrapStatus } from '../../services/tenantInit';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useGlobalStore } from '../../stores';
import { NAVIGATION_MENU_TREE_QUERY_KEY } from '../../hooks/useUnifiedMenuData';

const DISMISS_STORAGE_KEY_PREFIX = 'menu-sync-prompt:dismissed';
const NOTIFICATION_KEY_PREFIX = 'menu-sync-prompt';
const SESSION_SHOWN_KEY_PREFIX = 'menu-sync-prompt:session-shown';
/** 抬高于右下角 IterationFloatButton（bottom: 24），避免被盖住 */
const NOTIFICATION_BOTTOM_OFFSET = 88;

function buildDismissStorageKey(tenantId: number, manifestFingerprint: string): string {
  return `${DISMISS_STORAGE_KEY_PREFIX}:${tenantId}:${manifestFingerprint}`;
}

const MenuSyncPrompt: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi, notification } = App.useApp();
  const queryClient = useQueryClient();
  const currentUser = useCurrentUser();
  const tenantId = currentUser?.tenant_id;
  const shownFingerprintRef = useRef<string | null>(null);
  const openKeyRef = useRef<string | null>(null);
  const busyRef = useRef(false);
  const syncingRef = useRef(false);

  const { data: bootstrapStatus } = useQuery({
    queryKey: ['tenantBootstrapStatus'],
    queryFn: getBootstrapStatus,
    enabled: tenantId != null,
    staleTime: 60_000,
  });

  const { data: syncStatus } = useQuery({
    queryKey: [...MENU_SYNC_STATUS_QUERY_KEY, tenantId],
    queryFn: getMenuSyncStatus,
    enabled: tenantId != null && !!currentUser && bootstrapStatus?.pending !== true,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    const destroyKey = (key: string | null) => {
      if (!key) return;
      notification.destroy(key);
      if (openKeyRef.current === key) openKeyRef.current = null;
    };
    if (tenantId == null || bootstrapStatus?.pending) {
      destroyKey(openKeyRef.current);
      return;
    }
    const fingerprint = syncStatus?.manifest_fingerprint;
    if (!fingerprint) {
      destroyKey(openKeyRef.current);
      return;
    }
    const notificationKey = `${NOTIFICATION_KEY_PREFIX}-${tenantId}-${fingerprint}`;
    const dismissKey = buildDismissStorageKey(tenantId, fingerprint);
    if (!syncStatus?.needs_sync || localStorage.getItem(dismissKey) === '1') {
      destroyKey(notificationKey);
      destroyKey(openKeyRef.current);
      shownFingerprintRef.current = fingerprint;
      return;
    }
    // refetch 不得把同步中的通知重置为空闲，也不得越过对齐后的关闭逻辑。
    if (syncingRef.current) return;
    if (shownFingerprintRef.current === fingerprint && openKeyRef.current === notificationKey) return;
    const sessionShownKey = `${SESSION_SHOWN_KEY_PREFIX}:${tenantId}:${fingerprint}`;
    if (sessionStorage.getItem(sessionShownKey) === '1') {
      shownFingerprintRef.current = fingerprint;
      return;
    }
    shownFingerprintRef.current = fingerprint;
    sessionStorage.setItem(sessionShownKey, '1');
    const staleCount = syncStatus.stale_app_count;

    const dismiss = () => {
      localStorage.setItem(dismissKey, '1');
      destroyKey(notificationKey);
      destroyKey(openKeyRef.current);
    };

    const openIdle = () => {
      if (localStorage.getItem(dismissKey) === '1') {
        destroyKey(notificationKey);
        return;
      }
      openKeyRef.current = notificationKey;
      notification.open({
        key: notificationKey,
        title: t('components.menuSyncPrompt.title'),
        description: t('components.menuSyncPrompt.description', { count: staleCount }),
        placement: 'bottomRight',
        bottom: NOTIFICATION_BOTTOM_OFFSET,
        duration: 0,
        icon: <SyncOutlined style={{ color: 'var(--ant-color-primary)' }} />,
        actions: (
          <Space>
            <Button size="small" onClick={(e) => { e.stopPropagation(); dismiss(); }}>
              {t('components.menuSyncPrompt.later')}
            </Button>
            <Button type="primary" size="small" onClick={(e) => { e.stopPropagation(); void runSync(); }}>
              {t('components.menuSyncPrompt.action')}
            </Button>
          </Space>
        ),
        onClose: dismiss,
      });
    };

    const openBusy = () => {
      openKeyRef.current = notificationKey;
      notification.open({
        key: notificationKey,
        title: t('components.menuSyncPrompt.title'),
        description: t('components.menuSyncPrompt.syncing'),
        placement: 'bottomRight',
        bottom: NOTIFICATION_BOTTOM_OFFSET,
        duration: 0,
        icon: <SyncOutlined spin style={{ color: 'var(--ant-color-primary)' }} />,
        actions: (
          <Button type="primary" size="small" loading disabled>
            {t('components.menuSyncPrompt.action')}
          </Button>
        ),
      });
    };

    const runSync = async () => {
      if (busyRef.current || syncingRef.current) {
        return;
      }
      busyRef.current = true;
      syncingRef.current = true;
      openBusy();
      try {
        await scanApplications();
        const result = await syncAllManifestsAndMenus();
        dismiss();
        messageApi.success(
          result.message
          || t('components.menuSyncPrompt.syncSuccess', {
            count: result.menu_count ?? 0,
          }),
        );
        useGlobalStore.getState().incrementApplicationMenuVersion();
        queryClient.invalidateQueries({ queryKey: [NAVIGATION_MENU_TREE_QUERY_KEY] });
        queryClient.invalidateQueries({ queryKey: [...MENU_SYNC_STATUS_QUERY_KEY] });
      } catch (error: unknown) {
        const msg = error instanceof Error ? error.message : String(error || '');
        messageApi.error(msg || t('components.menuSyncPrompt.syncFailed'));
        openIdle();
      } finally {
        busyRef.current = false;
        syncingRef.current = false;
      }
    };

    openIdle();
  }, [
    bootstrapStatus?.pending,
    messageApi,
    notification,
    queryClient,
    syncStatus,
    t,
    tenantId,
  ]);

  return null;
};

export default MenuSyncPrompt;

export function invalidateMenuSyncStatusQuery(queryClient: QueryClient, tenantId?: number | null): void {
  queryClient.invalidateQueries({
    queryKey: tenantId != null ? [...MENU_SYNC_STATUS_QUERY_KEY, tenantId] : MENU_SYNC_STATUS_QUERY_KEY,
  });
}
