/**
 * 纯工位账号访问边界守卫（spec 180 / AC3、AC4）。
 *
 * - 纯工位账号（绑定角色全部 role_type === 'station'）只停留在工位入口及其子路径，
 *   访问其他路由一律 replace 回 /apps/kuaizhizao/production-execution/station；
 *   无论 Electron 壳还是普通浏览器都生效。
 * - Electron 壳（window.stationShell）内一旦识别到非纯工位账号（混合角色、无角色、
 *   管理员等）：先调用壳的 notifyStationRejected（存在才调用），再清理本地会话回登录页。
 *
 * 判定只依据登录用户的角色数据；window.stationShell、URL、workstationId
 * 只是客户端上下文，不作为授权证明。
 */
import React, { useEffect, useRef } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import PageSkeleton from '../page-skeleton';
import { useGlobalStore } from '../../stores/globalStore';
import { useCurrentUserQuery } from '../../hooks/useCurrentUserQuery';
import { buildRestoredUserFromStorage } from '../../utils/restoredUser';
import { getToken } from '../../utils/auth';
import { clearSessionScopedQueries } from '../../utils/clearSessionQueries';
import { redirectAfterLogout } from '../../utils/loginEntry';
import { isPureStationAccount, isStationAllowedPathname } from '../../utils/stationAccess';
import { STATION_ENTRY_PATH } from '../../utils/clientChannel';

type StationShellRejectionApi = { notifyStationRejected?: () => void };

function readStationShell(): StationShellRejectionApi | null {
  if (typeof window === 'undefined') return null;
  const shell = (window as Window & { stationShell?: unknown }).stationShell;
  return shell && typeof shell === 'object' ? (shell as StationShellRejectionApi) : null;
}

const StationAccessGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const storeUser = useGlobalStore((s) => s.currentUser);
  // enabled:false 只订阅缓存更新、不主动拉取：/auth/me 是否发请求仍由 AuthGuard 控制
  const { data: queryUser } = useCurrentUserQuery({ enabled: false });
  const user = storeUser ?? queryUser ?? buildRestoredUserFromStorage();
  const hasToken = !!getToken();
  const rejectedRef = useRef(false);

  const pureStation = !!user && isPureStationAccount(user);
  const shell = readStationShell();
  // 壳内已登录账号必须为纯工位账号；混合角色、无角色、管理员一律拒绝
  const shouldReject = !!shell && hasToken && !!user && !pureStation;

  useEffect(() => {
    if (!shouldReject || rejectedRef.current) return;
    rejectedRef.current = true;
    try {
      shell?.notifyStationRejected?.();
    } catch {
      /* 壳接口缺失或异常不阻断本地会话清理 */
    }
    clearSessionScopedQueries(queryClient);
    useGlobalStore.getState().logout();
    redirectAfterLogout(navigate);
  }, [shouldReject, shell, queryClient, navigate]);

  if (shouldReject) {
    return <PageSkeleton variant="content" />;
  }

  if (pureStation && hasToken && !isStationAllowedPathname(location.pathname)) {
    return <Navigate to={STATION_ENTRY_PATH} replace />;
  }

  return <>{children}</>;
};

export default StationAccessGate;
