import type { MenuDataItem } from '@ant-design/pro-components';
import { extractAppCodeFromPath } from '../../utils/menuTranslation';
import type { SidebarMenuDensity } from './sidebarMenuDensity';

/** 侧栏菜单布局：平铺（默认） / 双列 */
export type SidebarMenuLayout = 'flat' | 'split';

export const SIDEBAR_MENU_LAYOUT_PREF_KEY = 'ui.sidebar_menu_layout';

export const DEFAULT_SIDEBAR_MENU_LAYOUT: SidebarMenuLayout = 'flat';

/** ProLayout mix 布局默认侧栏宽度；平铺/双列共用，保证切换时总宽一致 */
export const FLAT_SIDEBAR_WIDTH = 215;
export const SPLIT_SIDEBAR_PRIMARY_WIDTH = 56;
export const SPLIT_SIDEBAR_SECONDARY_WIDTH = FLAT_SIDEBAR_WIDTH - SPLIT_SIDEBAR_PRIMARY_WIDTH;
export const SPLIT_SIDEBAR_WIDTH = FLAT_SIDEBAR_WIDTH;
export const SPLIT_SIDEBAR_COLLAPSED_WIDTH = SPLIT_SIDEBAR_PRIMARY_WIDTH;

/** 侧栏菜单行高：标准档对齐 antd Menu controlHeightLG(40) */
export const SIDER_MENU_ITEM_HEIGHT_STANDARD = 40;

/** 紧凑档行高（更多菜单可见） */
export const SIDER_MENU_ITEM_HEIGHT_COMPACT = 34;

export const SIDER_MENU_PADDING_STANDARD = 8;
export const SIDER_MENU_PADDING_COMPACT = 6;

/** 紧凑档行间距 */
export const SIDER_MENU_ITEM_MARGIN_BLOCK_COMPACT = 2;

/** 双列左列应用格最小高度 */
export const SPLIT_SIDEBAR_PRIMARY_ITEM_MIN_HEIGHT_STANDARD = 58;
export const SPLIT_SIDEBAR_PRIMARY_ITEM_MIN_HEIGHT_COMPACT = 52;

/** 双列左列图标磁贴尺寸 */
export const SPLIT_SIDEBAR_PRIMARY_ICON_SIZE_STANDARD = 34;
export const SPLIT_SIDEBAR_PRIMARY_ICON_SIZE_COMPACT = 32;

export type SiderMenuMetrics = {
  itemHeight: number;
  menuPadding: number;
  itemMarginBlock: number;
  splitPrimaryMinHeight: number;
  splitPrimaryIconSize: number;
};

export function resolveSiderMenuMetrics(density: SidebarMenuDensity): SiderMenuMetrics {
  if (density === 'compact') {
    return {
      itemHeight: SIDER_MENU_ITEM_HEIGHT_COMPACT,
      menuPadding: SIDER_MENU_PADDING_COMPACT,
      itemMarginBlock: SIDER_MENU_ITEM_MARGIN_BLOCK_COMPACT,
      splitPrimaryMinHeight: SPLIT_SIDEBAR_PRIMARY_ITEM_MIN_HEIGHT_COMPACT,
      splitPrimaryIconSize: SPLIT_SIDEBAR_PRIMARY_ICON_SIZE_COMPACT,
    };
  }
  return {
    itemHeight: SIDER_MENU_ITEM_HEIGHT_STANDARD,
    menuPadding: SIDER_MENU_PADDING_STANDARD,
    itemMarginBlock: 0,
    splitPrimaryMinHeight: SPLIT_SIDEBAR_PRIMARY_ITEM_MIN_HEIGHT_STANDARD,
    splitPrimaryIconSize: SPLIT_SIDEBAR_PRIMARY_ICON_SIZE_STANDARD,
  };
}

export function readSidebarMenuLayoutPref(preferences: Record<string, unknown> | null | undefined): SidebarMenuLayout {
  const nested = preferences?.ui as Record<string, unknown> | undefined;
  const raw = nested?.sidebar_menu_layout ?? preferences?.[SIDEBAR_MENU_LAYOUT_PREF_KEY];
  return raw === 'split' ? 'split' : 'flat';
}

type SidebarShortLabelTranslate = (key: string, options?: { defaultValue?: string }) => string;

/** 双列左列短标签：优先 i18n 显式映射，避免「仪表板」被截成「表板」、「行业包」被截成「业包」 */
const SIDEBAR_SHORT_LABEL_I18N_BY_PATH: Record<string, string> = {
  '/system/dashboard': 'menu.dashboard.short',
  '/apps/industry-pack': 'app.industry-pack.short',
};

const INDUSTRY_PACK_ROOT_PATH = '/apps/industry-pack';

function resolveAppCodeForShortLabel(item: MenuDataItem): string | null {
  const path = typeof item.path === 'string' ? item.path : '';
  const normalizedPath = path.replace(/\/$/, '');
  if (normalizedPath === INDUSTRY_PACK_ROOT_PATH) return 'industry-pack';
  const fromPath = extractAppCodeFromPath(path);
  if (fromPath) return fromPath;
  // ProLayout transformRoute 可能把 `#app-group-x` 收成 `/#app-group-x`
  const hashMatch = path.match(/^\/?#app-group-(.+)$/);
  if (hashMatch?.[1]) return hashMatch[1].trim() || null;
  const key = typeof item.key === 'string' ? item.key : '';
  if (key.startsWith('app-group-code-')) {
    const code = key.slice('app-group-code-'.length).trim();
    return code || null;
  }
  return null;
}

/** 一级菜单短标签：优先 i18n（menu.*.short / app.*.short），中文兜底取末两字 */
export function toSidebarShortLabel(
  item: MenuDataItem,
  t?: SidebarShortLabelTranslate,
): string {
  const path = typeof item.path === 'string' ? item.path : '';
  const normalizedPath = path.replace(/\/$/, '');
  const fallback = typeof item.name === 'string' ? item.name : '';

  if (t) {
    if (normalizedPath) {
      const i18nKey = SIDEBAR_SHORT_LABEL_I18N_BY_PATH[normalizedPath];
      if (i18nKey) {
        const mapped = t(i18nKey, { defaultValue: '' });
        if (mapped && mapped !== i18nKey && mapped.trim() !== '') {
          return mapped;
        }
      }
    }

    const appCode = resolveAppCodeForShortLabel(item);
    if (appCode) {
      const shortKey = `app.${appCode}.short`;
      const translated = t(shortKey, { defaultValue: '' });
      if (translated && translated !== shortKey && translated.trim() !== '') {
        return translated;
      }
    }

    // 行业包根：面包屑可能被误判成子模块 code，名称仍为「行业包」
    const packName = t('app.industry-pack.name', { defaultValue: '行业包' });
    if (fallback.trim() === packName || fallback.trim() === '行业包') {
      const packShort = t('app.industry-pack.short', { defaultValue: '行业' });
      if (packShort && packShort.trim() !== '') return packShort;
    }
  }

  const text = fallback.trim();
  if (!text) return '';
  if (text.length <= 2) return text;
  return text.slice(-2);
}

export function menuItemKey(item: MenuDataItem): string {
  return String(item.key ?? item.path ?? item.name ?? '');
}

/**
 * 菜单 path 可含 query（如 /apps/…/day-register?mode=rest）。
 * 匹配得分：-1 不匹配；0 仅 pathname（无 query 菜单）；>0 为命中的 query 参数个数。
 * 同 pathname 多入口（如交付物 vs 交付物?preset=electronics）时取最高分，避免无 query 项抢走选中态。
 */
export function menuPathMatchScore(
  menuPath: string | undefined | null,
  pathname: string,
  search = '',
): number {
  if (!menuPath) return -1;
  const qIndex = menuPath.indexOf('?');
  const pathPart = qIndex >= 0 ? menuPath.slice(0, qIndex) : menuPath;
  if (pathPart !== pathname) return -1;
  if (qIndex < 0) return 0;
  const required = new URLSearchParams(menuPath.slice(qIndex + 1));
  const actual = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  let matched = 0;
  for (const [key, value] of required.entries()) {
    if (actual.get(key) !== value) return -1;
    matched += 1;
  }
  return matched;
}

export function menuPathMatchesLocation(
  menuPath: string | undefined | null,
  pathname: string,
  search = '',
): boolean {
  return menuPathMatchScore(menuPath, pathname, search) >= 0;
}

export type BestMenuMatch = {
  item: MenuDataItem;
  /** 不含叶子自身的祖先 key */
  ancestorKeys: string[];
  /** 含叶子到根的完整链（用于面包屑） */
  chain: MenuDataItem[];
  score: number;
};

/** 在整棵菜单树中找与当前路由匹配度最高的项（query 约束越多越优先） */
export function findBestMenuMatch(
  items: MenuDataItem[],
  pathname: string,
  search = '',
): BestMenuMatch | null {
  const holder: { best: BestMenuMatch | null } = { best: null };

  const walk = (nodes: MenuDataItem[], ancestors: MenuDataItem[], ancestorKeys: string[]) => {
    for (const node of nodes) {
      const key = menuItemKey(node);
      const chain = [...ancestors, node];
      const score = menuPathMatchScore(node.path, pathname, search);
      if (score >= 0 && (!holder.best || score > holder.best.score)) {
        holder.best = { item: node, ancestorKeys, chain, score };
      }
      if (node.children?.length) {
        walk(node.children, chain, key ? [...ancestorKeys, key] : ancestorKeys);
      }
    }
  };

  walk(items, [], []);
  return holder.best;
}

export function findActiveRootKey(roots: MenuDataItem[], currentPath: string, search = ''): string {
  let bestKey = '';
  let bestScore = -1;
  for (const root of roots) {
    const key = menuItemKey(root);
    if (!key) continue;
    const rootScore = menuPathMatchScore(root.path, currentPath, search);
    const childBest = root.children?.length
      ? findBestMenuMatch(root.children, currentPath, search)
      : null;
    const score = Math.max(rootScore, childBest?.score ?? -1);
    if (score > bestScore) {
      bestScore = score;
      bestKey = key;
    }
  }
  if (bestScore < 0) {
    const first = roots[0];
    return first ? menuItemKey(first) : '';
  }
  return bestKey;
}

export function findFirstLeafPath(items: MenuDataItem[]): string | undefined {
  for (const item of items) {
    if (item.hideInMenu) continue;
    if (item.path && !item.path.startsWith('#')) return item.path;
    if (item.children?.length) {
      const nested = findFirstLeafPath(item.children);
      if (nested) return nested;
    }
  }
  return undefined;
}

function treeHasInfraPath(item: MenuDataItem): boolean {
  if (item.key === 'menu.infra') return true;
  if (typeof item.path === 'string' && item.path.startsWith('/infra/')) return true;
  return item.children?.some(treeHasInfraPath) ?? false;
}

function countVisibleMenuChildren(item: MenuDataItem): number {
  return (item.children ?? []).filter((child) => child.hideInMenu !== true).length;
}

/** 行业包容器无已启用子应用时不占双列左栏磁贴（与后端 navigation-tree 一致） */
export function isEmptyIndustryPackRoot(item: MenuDataItem): boolean {
  const path = typeof item.path === 'string' ? item.path : '';
  if (path !== INDUSTRY_PACK_ROOT_PATH) return false;
  return countVisibleMenuChildren(item) === 0;
}

/** 双列左列不展示：系统配置（走底栏）、平台基础设施等硬编码平台根 */
export function isSplitSidebarExcludedRoot(item: MenuDataItem): boolean {
  if (item.hideInMenu === true) return true;
  if (item.path === '/system') return true;
  if (isEmptyIndustryPackRoot(item)) return true;
  return treeHasInfraPath(item);
}

export function buildSplitMenuRoots(items: MenuDataItem[]): MenuDataItem[] {
  return items.filter((item) => !isSplitSidebarExcludedRoot(item));
}

export function computeSplitSecondaryOpenKeys(
  roots: MenuDataItem[],
  currentPath: string,
  computeOpenKeys: (items: MenuDataItem[], path: string, search?: string) => string[],
  search = '',
): string[] {
  const activeKey = findActiveRootKey(roots, currentPath, search);
  const activeRoot = roots.find((item) => menuItemKey(item) === activeKey);
  if (!activeRoot?.children?.length) return [];
  return computeOpenKeys(activeRoot.children, currentPath, search);
}
