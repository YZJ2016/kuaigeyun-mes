/**
 * 壳页 F5 性能断言（E2E-1）：登录态硬刷新后菜单可见，且不误拉 univer/CAD 重包。
 */
import { test, expect } from '@playwright/test';
import { FRONTEND_URL, STORAGE_STATE_PATH } from './helpers/session';

test.use({ storageState: STORAGE_STATE_PATH });

test.describe('壳页加载', () => {
  test('F5 后侧栏可见且无 univer/libredwg 请求', async ({ page }) => {
    const heavyHits: string[] = [];
    page.on('request', (req) => {
      const u = req.url();
      if (/vendor-(univerjs|libredwg|altium|monaco)-/i.test(u)) {
        heavyHits.push(u);
      }
    });

    await page.goto(`${FRONTEND_URL}/system/dashboard/workplace`, {
      waitUntil: 'domcontentloaded',
      timeout: 60_000,
    });
    await page.waitForSelector('.ant-layout-sider, .ant-pro-sider, nav', { timeout: 60_000 });

    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.ant-layout-sider, .ant-pro-sider, nav', { timeout: 60_000 });

    const nav = await page.evaluate(() => {
      const n = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
      return n
        ? {
            dcl: Math.round(n.domContentLoadedEventEnd),
            load: Math.round(n.loadEventEnd),
          }
        : null;
    });
    console.log('[perf-shell]', JSON.stringify({ nav, heavyHits }));

    expect(heavyHits, `壳页不应加载重包: ${heavyHits.join(', ')}`).toEqual([]);
  });
});
