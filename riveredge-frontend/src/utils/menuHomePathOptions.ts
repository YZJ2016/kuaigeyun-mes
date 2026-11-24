import type { MenuTree } from '../services/menu';

export type MenuHomePathOption = { label: string; value: string };

/**
 * 共用 menu-entry-shell 的应用根（仅菜单聚合，无业务落地页）。
 * 与后端 manifest entry_point 指向 menu-entry-shell 的应用一致。
 */
const MENU_ENTRY_SHELL_APP_CODES = new Set(['kuaiems', 'kuaiqms', 'industry-pack']);

/** 是否不宜作为角色/租户首页的「虚拟应用根」或侧栏分组壳 path */
export function isVirtualMenuGroupHomePath(path: string, node?: Pick<MenuTree, 'meta' | 'children'>): boolean {
  const normalized = path.replace(/\/+$/, '') || '/';
  if (node?.meta?.custom_layout_virtual === true) {
    return true;
  }
  const appRoot = normalized.match(/^\/apps\/([^/]+)$/);
  if (appRoot && MENU_ENTRY_SHELL_APP_CODES.has(appRoot[1])) {
    return true;
  }
  // 带子菜单的纯分组：有 path 但只为撑开目录，无独立业务页
  if ((node?.children?.length ?? 0) > 0 && normalized.startsWith('#app-group-')) {
    return true;
  }
  return false;
}

/** 将导航菜单树展平为「设首页」可选 path（仅含已配置 path 的非外链菜单） */
export function flattenMenuHomePathOptions(
  items: MenuTree[],
  labelFn?: (name: string, path: string) => string,
): MenuHomePathOption[] {
  const out: MenuHomePathOption[] = [];
  const seen = new Set<string>();

  const walk = (nodes: MenuTree[], prefix: string) => {
    for (const n of nodes) {
      const path = (n.path || '').trim();
      if (path && !n.is_external && !seen.has(path) && !isVirtualMenuGroupHomePath(path, n)) {
        seen.add(path);
        const name = (n.name || '').trim() || path;
        out.push({
          label: labelFn ? labelFn(name, path) : `${prefix}${name} (${path})`,
          value: path,
        });
      }
      if (n.children?.length) {
        const nextPrefix = prefix ? `${prefix}  ` : '';
        walk(n.children, nextPrefix);
      }
    }
  };

  walk(items, '');
  return out.sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
}