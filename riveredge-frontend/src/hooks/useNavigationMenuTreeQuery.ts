/**
 * 导航菜单树（/core/menus/navigation-tree）统一查询 Hook。
 *
 * 侧边栏、工作台快捷入口、面包屑解析、各管理页等都消费同一份导航树。
 * 必须使用同一 queryKey，否则 React Query 视为不同 query，会在同一页面重复
 * 拉取 navigation-tree（侧栏一次、工作台又一次）。此处集中规范 queryKey 与
 * 查询参数，所有消费方复用，确保 staleTime 内命中同一缓存、只发一次请求。
 *
 * 失效仍可用前缀 [NAVIGATION_MENU_TREE_QUERY_KEY] 匹配（React Query 默认前缀匹配）。
 *
 * 注意：navigation-tree 为租户级全量启用菜单，RBAC 在前端 filter；queryKey
 * 不得含 permission_version，否则 /auth/me 回写版本时会丢缓存并二次拉取，APP 菜单闪空。
 */

import { useMemo } from 'react';
import { layoutShellQueryOptions } from '../config/reactQuery';
import { useQuery } from '@tanstack/react-query';
import { getNavigationMenuTree, type MenuTree } from '../services/menu';
import type { CurrentUser } from '../types/api';
import { useCurrentUser } from './useCurrentUser';

/** 与 clearSessionQueries / 各失效点共用，避免侧栏与工作台菜单缓存不一致 */
export const NAVIGATION_MENU_TREE_QUERY_KEY = 'navigationMenuTree';

/** 规范的导航树 queryKey：按租户缓存；权限变更只重算前端过滤，不重拉树 */
export function buildNavigationMenuTreeQueryKey(
  user?: Pick<CurrentUser, 'tenant_id'> | null,
) {
  return [NAVIGATION_MENU_TREE_QUERY_KEY, user?.tenant_id ?? null] as const;
}

export interface UseNavigationMenuTreeQueryOptions {
  /** 额外的启用条件（与「已登录」做与运算） */
  enabled?: boolean;
}

/**
 * 统一的导航菜单树查询。所有消费方都应使用本 Hook（而非各自手写 useQuery），
 * 以共用同一 queryKey 与缓存，消除重复请求。
 */
export function useNavigationMenuTreeQuery(
  options: UseNavigationMenuTreeQueryOptions = {},
) {
  const { enabled = true } = options;
  const currentUser = useCurrentUser();

  const queryKey = useMemo(
    () => buildNavigationMenuTreeQueryKey(currentUser),
    [currentUser?.tenant_id],
  );

  return useQuery<MenuTree[]>({
    queryKey,
    queryFn: () => getNavigationMenuTree(),
    enabled: !!currentUser && enabled,
    ...layoutShellQueryOptions,
    staleTime: 5 * 60 * 1000,
    // 失效重拉时保留上一棵树，避免侧栏 APP 菜单空档
    placeholderData: (previousData) => previousData,
  });
}
