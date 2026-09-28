/**
 * 快智造：按菜单路径预取页面 chunk（与 index.tsx 中 lazy 同源），hover 菜单时触发，减轻「点击后等白屏」。
 * P5-5：进系统后 idle 预取 Top-5 高频页，缩短冷跳转。
 */

const pageModules = import.meta.glob('./pages/**/*.tsx') as Record<string, () => Promise<unknown>>;

/** 与 Route path 不一致的页面模块（其余默认 ./pages/{route}/index.tsx） */
const ROUTE_MODULE_OVERRIDES: Record<string, string> = {
  'plan-management/production-control-tower':
    './pages/plan-management/production-plans/ProductionControlTower.tsx',
  // 生产终端路由已下线
  // 'production-execution/terminal': './pages/production-execution/work-orders/kiosk.tsx',
};

/** 销售订单 / 采购订单 / 工单 / 库存 / 应用首页 */
export const KUZHI_TOP_PREFETCH_ROUTES: readonly string[] = [
  '/apps/kuaizhizao',
  '/apps/kuaizhizao/sales-management/sales-orders',
  '/apps/kuaizhizao/purchase-management/purchase-orders',
  '/apps/kuaizhizao/production-execution/work-orders',
  '/apps/kuaizhizao/warehouse-management/inventory',
];

function runLoader(key: string | undefined): void {
  if (!key) return;
  const load = pageModules[key];
  if (load) void load().catch(() => {});
}

/**
 * @param fullPath 菜单 path，如 /apps/kuaizhizao/sales-management/sales-orders
 */
export function prefetchKuaizhizaoRoute(fullPath: string | undefined): void {
  if (!fullPath?.startsWith('/apps/kuaizhizao')) return;

  const raw = fullPath.split('?')[0].replace(/\/$/, '');
  const base = '/apps/kuaizhizao';
  const rel = raw === base ? '' : raw.startsWith(`${base}/`) ? raw.slice(base.length + 1) : '';

  if (!rel) {
    runLoader('./pages/dashboard/index.tsx');
    return;
  }

  if (/\/work-orders\/[^/]+\/kiosk$/.test(rel)) {
    runLoader('./pages/production-execution/work-orders/detail-kiosk.tsx');
    return;
  }

  const override = ROUTE_MODULE_OVERRIDES[rel];
  if (override) {
    runLoader(override);
    return;
  }

  const asIndex = `./pages/${rel}/index.tsx`;
  if (pageModules[asIndex]) {
    runLoader(asIndex);
    return;
  }

  const asFile = `./pages/${rel}.tsx`;
  if (pageModules[asFile]) {
    runLoader(asFile);
    return;
  }
}

let topPrefetchScheduled = false;

/** 壳就绪后 idle 预取 Top-5（只调度一次） */
export function schedulePrefetchKuaizhizaoTopRoutes(): void {
  if (topPrefetchScheduled || typeof window === 'undefined') return;
  topPrefetchScheduled = true;
  const run = () => {
    for (const path of KUZHI_TOP_PREFETCH_ROUTES) {
      prefetchKuaizhizaoRoute(path);
    }
  };
  const ric = (
    window as Window & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
    }
  ).requestIdleCallback;
  if (typeof ric === 'function') {
    ric(run, { timeout: 4000 });
  } else {
    window.setTimeout(run, 1800);
  }
}
