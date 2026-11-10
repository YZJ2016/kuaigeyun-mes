import { defineConfig } from '@playwright/test';

/**
 * 自定义字段关联对象外键回归：使用本机 Chrome channel，避免 sandbox Playwright 浏览器缓存缺失。
 */
export default defineConfig({
  testDir: './',
  testMatch: '**/custom-field-associated-fk.spec.ts',
  outputDir: './output/cf-fk-results',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: './output/cf-fk-results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:8100',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    viewport: { width: 1600, height: 900 },
    locale: 'zh-CN',
    channel: 'chrome',
  },
  globalSetup: './global-setup.ts',
});
