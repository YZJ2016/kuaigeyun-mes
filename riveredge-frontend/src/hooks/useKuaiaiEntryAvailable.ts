import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getInstalledApplicationList,
  installedApplicationsQueryKey,
} from '../services/application';
import { getTenantId } from '../utils/auth';
import { useCurrentUser } from './useCurrentUser';
import { hasPermission, resolveUserForMenuPermission } from '../utils/permission';

/** @deprecated 请用 installedApplicationsQueryKey(getTenantId())；保留别名避免旧 import 断掉 */
export const KUAIAI_INSTALLED_APPS_QUERY_KEY = installedApplicationsQueryKey(null);

export function useKuaiaiEntryAvailable(): boolean {
  const currentUser = useCurrentUser();
  const tenantId = getTenantId();
  const { data: installedApps } = useQuery({
    queryKey: installedApplicationsQueryKey(tenantId),
    queryFn: () => getInstalledApplicationList({ is_active: true }),
    staleTime: 60_000,
  });

  return useMemo(() => {
    const kuaiaiApp = (installedApps ?? []).find((app) => app.code === 'kuaiai');
    if (!kuaiaiApp) return false;
    if (kuaiaiApp.is_pro && kuaiaiApp.can_access === false) return false;
    const user = resolveUserForMenuPermission(currentUser);
    if (!user) return false;
    if (user.is_tenant_admin || user.is_infra_admin) return true;
    return hasPermission(user, 'kuaiai:entry:read');
  }, [installedApps, currentUser]);
}
