'use strict';

/**
 * 工位壳导航白名单（纯函数，无 Electron 依赖）。
 *
 * will-navigate 只拦整页导航；SPA 的 history.pushState / replaceState 不经过这里。
 * 允许集合：
 * - /login：租户登录页。未认证跳转（buildLoginRedirectPath）在工位路径上解析为 /login；
 *   壳在非纯工位账号被拒时也把窗口导航回 {serverOrigin}/login。
 * - /lock-screen：锁屏页。
 * - /apps/kuaizhizao/production-execution/station 及真实子路径：工位入口。
 *
 * 明确不放行：
 * - '/'、'/docs'、'/init/*' 等 PC 公共路由；
 * - '/infra'、'/infra/login'：平台超管入口，不属于工位租户账号的认证流程；
 * - '/{tenant}' 单段组织入口：工位固定用 /login 全路径登录，登出入口快照也记录 /login；
 * - 同源其他 PC 路由、伪前缀（/loginx、.../station-evil）、跨源、非 http(s)、畸形 URL。
 *
 * 判定只看 pathname，查询串与锚点不影响结果。
 */

const STATION_ENTRY_PATH = '/apps/kuaizhizao/production-execution/station';
const LOGIN_PATH = '/login';
const LOCK_SCREEN_PATH = '/lock-screen';

const ALLOWED_PATHS = [LOGIN_PATH, LOCK_SCREEN_PATH, STATION_ENTRY_PATH];

/** 路径精确匹配，或以 `path + '/'` 为前缀（伪前缀如 /loginx 不算）。 */
function isAllowedPathname(pathname) {
  return ALLOWED_PATHS.some(
    (allowed) => pathname === allowed || pathname.startsWith(`${allowed}/`),
  );
}

function parseHttpOrigin(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return '';
  let url;
  try {
    url = new URL(raw.trim());
  } catch {
    return '';
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
  return url.origin;
}

/**
 * @param {string} targetUrl will-navigate 给的目标 URL
 * @param {string} serverOrigin 本机配置的服务地址（main.js normalizeOrigin 的产物）
 * @returns {boolean} 允许整页导航到该地址时返回 true
 */
function isNavigationAllowed(targetUrl, serverOrigin) {
  const origin = parseHttpOrigin(serverOrigin);
  if (!origin) return false;

  let target;
  try {
    target = new URL(targetUrl);
  } catch {
    return false;
  }
  if (target.protocol !== 'http:' && target.protocol !== 'https:') return false;
  // 与 main.js normalizeOrigin 一致：带用户名/口令的 URL 不放行
  if (target.username || target.password) return false;
  if (target.origin !== origin) return false;
  // new URL 已归一化 pathname（解码点段 .. / .），直接比对即可
  return isAllowedPathname(target.pathname);
}

module.exports = {
  isNavigationAllowed,
  STATION_ENTRY_PATH,
  ALLOWED_PATHS,
};
