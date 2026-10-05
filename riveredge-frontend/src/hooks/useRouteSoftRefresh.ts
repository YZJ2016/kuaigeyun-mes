import { useEffect, useRef } from 'react';

export const ROUTE_SOFT_REFRESH_EVENT = 'riveredge:soft-refresh-active-tab';

export interface RouteSoftRefreshDetail {
  tabKey: string;
}

/** 与 UniTabs tabKey 对齐：去掉 _refresh、尾斜杠 */
export function normalizeSoftRefreshTabKey(pathname: string, search?: string): string {
  const path = (pathname || '/').replace(/\/$/, '') || '/';
  const params = new URLSearchParams(search || '');
  params.delete('_refresh');
  const cleanSearch = params.toString();
  return cleanSearch ? `${path}?${cleanSearch}` : path;
}

export function tabKeyFromRouteKey(tabKey: string): string {
  const q = tabKey.indexOf('?');
  const pathname = q >= 0 ? tabKey.slice(0, q) : tabKey;
  const search = q >= 0 ? tabKey.slice(q) : '';
  return normalizeSoftRefreshTabKey(pathname, search);
}

  /**
   * 标签栏「刷新」或等价软刷新：重拉数据（列表 UniTable / 看板 useDashboardRequest）。
   * 若事件带 tabKey，则与当前路由比对；比对失败时仍执行（避免 basename / 编码差异漏刷）。
   */
  export function useRouteSoftRefresh(handler: () => void) {
    const handlerRef = useRef(handler);
    handlerRef.current = handler;

    useEffect(() => {
      const onRefresh = (_event: Event) => {
        handlerRef.current();
      };
      window.addEventListener(ROUTE_SOFT_REFRESH_EVENT, onRefresh);
      return () => window.removeEventListener(ROUTE_SOFT_REFRESH_EVENT, onRefresh);
    }, []);
  }

export function dispatchRouteSoftRefresh(tabKey: string) {
  window.dispatchEvent(
    new CustomEvent<RouteSoftRefreshDetail>(ROUTE_SOFT_REFRESH_EVENT, {
      detail: { tabKey: tabKeyFromRouteKey(tabKey) },
    }),
  );
}
