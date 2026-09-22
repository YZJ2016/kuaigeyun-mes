import { useEffect, useRef } from 'react';

export const ROUTE_SOFT_REFRESH_EVENT = 'riveredge:soft-refresh-active-tab';

export interface RouteSoftRefreshDetail {
  tabKey: string;
}

/**
 * 标签栏「刷新」或等价软刷新：仅重拉数据，禁止 remount 整页。
 * 列表页由 UniTable 统一监听；看板可在 useDashboardRequest 内注册 refresh。
 */
export function useRouteSoftRefresh(handler: () => void) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const onRefresh = () => {
      handlerRef.current();
    };
    window.addEventListener(ROUTE_SOFT_REFRESH_EVENT, onRefresh);
    return () => window.removeEventListener(ROUTE_SOFT_REFRESH_EVENT, onRefresh);
  }, []);
}

export function dispatchRouteSoftRefresh(tabKey: string) {
  window.dispatchEvent(
    new CustomEvent<RouteSoftRefreshDetail>(ROUTE_SOFT_REFRESH_EVENT, {
      detail: { tabKey },
    }),
  );
}
