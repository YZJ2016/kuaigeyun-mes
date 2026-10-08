/**
 * 纯工位账号访问边界（spec 180 / STN-D12～D15）。
 *
 * 判定只依据登录用户的角色数据：绑定角色全部 role_type === 'station' 才是纯工位账号。
 * window.stationShell、URL、workstationId 只是客户端上下文，不是授权证明。
 *
 * 本文件必须保持零运行时依赖（仅复用 clientChannel 的路径约定），
 * 供登录页 MPA、路由守卫与 Node 纯函数测试共用。
 */
import { STATION_ENTRY_PATH, isStationEntryPath } from './clientChannel.ts';

export const STATION_ROLE_TYPE = 'station';

/** 角色上只需要 role_type；兼容 CurrentUser.roles 与登录响应 user.roles 的最小形状。 */
export interface StationAccessRoleLike {
  role_type?: string | null;
}

export interface StationAccessUserLike {
  is_infra_admin?: boolean | null;
  roles?: ReadonlyArray<StationAccessRoleLike | null | undefined> | null;
}

/** 与后端 serialize_active_roles 的 strip().lower() 口径一致 */
export function normalizeStationRoleType(roleType: string | null | undefined): string {
  return String(roleType ?? '').trim().toLowerCase();
}

/**
 * 纯工位账号：至少绑定一个角色，且全部角色的 role_type 都是 'station'。
 * 平台超管、无角色账号、station 与 internal/external 混挂都不算纯工位账号。
 */
export function isPureStationAccount(user: StationAccessUserLike | null | undefined): boolean {
  if (!user || user.is_infra_admin) return false;
  const roles = user.roles;
  if (!Array.isArray(roles) || roles.length === 0) return false;
  return roles.every(
    (role) => normalizeStationRoleType(role?.role_type) === STATION_ROLE_TYPE,
  );
}

function normalizePathname(pathname: string): string {
  return (
    String(pathname || '')
      .split('?')[0]
      .split('#')[0]
      .replace(/\/+$/, '') || '/'
  );
}

/**
 * 纯工位账号允许停留的路径：工位入口及真实子路径 + 锁屏页。
 * 其余路径（含伪前缀、PC 模块、系统管理）一律由守卫 replace 回工位入口。
 */
export function isStationAllowedPathname(pathname: string): boolean {
  const path = normalizePathname(pathname);
  if (path === '/lock-screen') return true;
  return isStationEntryPath(path);
}

export { STATION_ENTRY_PATH };
