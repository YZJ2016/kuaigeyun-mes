/**
 * 角色「功能权限树 → 数据/字段权限」资源范围（前后端唯一推导入口）。
 * 仅功能权限 TAB 中已勾选操作的菜单页进入数据/字段 TAB；禁止从 grantedCodes 扁平推导或菜单全量兜底。
 * 后端对齐：RolePermissionMatrixService.collect_granted_resource_keys_for_role。
 */

import type { FunctionGrantMenuNode } from '../../../../services/role';
import { codesFromAction, isActionGranted } from './FunctionGrantTree';
import { translateGrantMenuTitle } from './functionGrantTreeFilters';
import { permissionCodeToResourceKey, type ResourceOption } from './dataPermissionFilters';

export function normalizeResourceKey(resource: string): string {
  return resource.trim().toLowerCase();
}

/** 与后端 menu_resource_resolver.is_generic_menu_permission_code 对齐 */
/** 与后端 PermissionPolicyService 对齐：仅授 display 的资源不参与字段权限 */
export function collectDisplayOnlyResourceKeys(grantedCodes: string[]): Set<string> {
  const byResource = new Map<string, Set<string>>();
  for (const raw of grantedCodes) {
    const norm = String(raw ?? '').trim().toLowerCase();
    if (!norm || isGenericPolicyResourceCode(norm)) continue;
    const parts = norm.split(':').filter(Boolean);
    if (parts.length < 3) continue;
    const app = parts[0];
    const action = parts[parts.length - 1];
    const resource = parts.slice(1, -1).join(':');
    if (!app || !resource || !action) continue;
    const key = normalizeResourceKey(`${app}:${resource}`);
    const bucket = byResource.get(key) ?? new Set<string>();
    bucket.add(action);
    byResource.set(key, bucket);
  }
  const displayOnly = new Set<string>();
  for (const [key, actions] of byResource) {
    if (actions.size > 0 && [...actions].every((a) => a === 'display')) {
      displayOnly.add(key);
    }
  }
  return displayOnly;
}

export function collectGrantedResourceKeysExcludingDisplayOnly(
  tree: FunctionGrantMenuNode[],
  grantedCodes: string[]
): Set<string> {
  const keys = collectGrantedResourceKeysFromGrantTree(tree, grantedCodes);
  const displayOnly = collectDisplayOnlyResourceKeys(grantedCodes);
  for (const key of displayOnly) {
    keys.delete(key);
  }
  return keys;
}

export function isGenericPolicyResourceCode(norm: string): boolean {
  if (!norm) return true;
  const parts = norm.split(':').filter(Boolean);
  if (parts.length >= 3 && parts[parts.length - 1] === 'read') {
    const resource = parts.slice(1, -1).join(':');
    if (resource === 'workspace' || resource === parts[0]) return true;
  }
  return false;
}

/**
 * 功能权限矩阵树 + 当前勾选 code → 数据/字段权限可配置资源（唯一真源）。
 * 仅当菜单节点上至少有一项操作已勾选时，该页才进入第二、三 TAB。
 */
export function collectGrantedResourceOptionsFromGrantTree(
  tree: FunctionGrantMenuNode[],
  grantedCodes: string[],
  t: (key: string, opts?: { defaultValue?: string }) => string
): ResourceOption[] {
  const granted = new Set(
    grantedCodes.map((c) => String(c ?? '').trim().toLowerCase()).filter(Boolean)
  );
  if (granted.size === 0 || tree.length === 0) return [];

  const byKey = new Map<string, ResourceOption>();

  const walk = (nodes: FunctionGrantMenuNode[]) => {
    for (const node of nodes) {
      const hasGrantedAction = node.actions.some((a) => isActionGranted(a, granted));
      if (hasGrantedAction) {
        const label = translateGrantMenuTitle(node, t);
        for (const action of node.actions) {
          if (!isActionGranted(action, granted)) continue;
          for (const code of codesFromAction(action)) {
            const norm = String(code ?? '').trim().toLowerCase();
            if (!norm || isGenericPolicyResourceCode(norm)) continue;
            const key = permissionCodeToResourceKey(code);
            if (!key) continue;
            const nk = normalizeResourceKey(key);
            const existing = byKey.get(nk);
            if (!existing) {
              byKey.set(nk, { value: nk, label, searchLabels: [label] });
            } else if (!existing.searchLabels?.includes(label)) {
              const searchLabels = [...(existing.searchLabels ?? [existing.label]), label];
              const compact =
                searchLabels.length > 1
                  ? `${searchLabels[0]}（${searchLabels.slice(1).join(' / ')}）`
                  : searchLabels[0];
              byKey.set(nk, {
                value: nk,
                label: compact,
                searchLabels,
              });
            }
          }
        }
      }
      if (node.children?.length) walk(node.children);
    }
  };

  walk(tree);
  return Array.from(byKey.values()).sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
}

/** 由功能权限树推导出的 app:resource 键集合 */
export function collectGrantedResourceKeysFromGrantTree(
  tree: FunctionGrantMenuNode[],
  grantedCodes: string[]
): Set<string> {
  const keys = new Set<string>();
  for (const opt of collectGrantedResourceOptionsFromGrantTree(tree, grantedCodes, (k, o) =>
    o?.defaultValue ?? k
  )) {
    keys.add(normalizeResourceKey(opt.value));
  }
  return keys;
}
