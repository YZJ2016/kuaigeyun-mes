/** 大屏/报表分享页（免登录，凭 URL token 访问） */

const SHARED_DASHBOARD_PATH = '/apps/kuaireport/dashboards/shared';
const SHARED_REPORT_PATH = '/apps/kuaireport/reports/shared';

function normalizePathname(pathname: string): string {
  const trimmed = (pathname || '').replace(/\/+$/, '');
  return trimmed || '/';
}

/** 当前或给定 pathname 是否为 kuaireport 分享浏览页 */
export function isKuaireportSharedBrowsePath(pathname?: string): boolean {
  const path = normalizePathname(
    pathname ?? (typeof window !== 'undefined' ? window.location.pathname : ''),
  );
  return path === SHARED_DASHBOARD_PATH || path === SHARED_REPORT_PATH;
}

/** 精确路径或 path + '/' / '?' 边界，避免 /sharedXxx 之类前缀误命中 */
function matchesSharedApiPath(url: string, base: string): boolean {
  return url === base || url.startsWith(`${base}/`) || url.startsWith(`${base}?`);
}

/** apiRequest 中视为公开、不携带会话 Token 的 kuaireport 分享接口 */
export function isKuaireportSharedApiPath(url: string): boolean {
  return (
    matchesSharedApiPath(url, SHARED_DASHBOARD_PATH) ||
    matchesSharedApiPath(url, SHARED_REPORT_PATH)
  );
}
