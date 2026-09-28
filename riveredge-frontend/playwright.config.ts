import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { defineConfig } from '@playwright/test';

/**
 * RiverEdge 前端 E2E 验证配置
 *
 * 前置：前端 dev server (8100) 与后端 (8200) 已运行。
 * 账号：默认 xiaofeng / 12345678 @ tenant 3（测试）；可用 E2E_* 环境变量覆盖（见 e2e/helpers/session.ts）。
 *
 * Chromium：优先 headless_shell；若尚未装完则回退到完整 chromium-1228（避免 install 卡在下载）。
 */
const pwRoot = path.join(os.homedir(), 'AppData', 'Local', 'ms-playwright');
const headlessShell = path.join(
  pwRoot,
  'chromium_headless_shell-1228',
  'chrome-headless-shell-win64',
  'chrome-headless-shell.exe',
);
const fullChrome = path.join(pwRoot, 'chromium-1228', 'chrome-win64', 'chrome.exe');
const chromiumExecutable = fs.existsSync(headlessShell)
  ? undefined
  : fs.existsSync(fullChrome)
    ? fullChrome
    : undefined;

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/output/test-results',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  workers: 4,
  // 后端数据库为远程云主机，公网连接偶发抖动（10060/连接中断）；
  // 重试用于区分瞬时网络错误与真实代码缺陷，重试后仍失败的才是缺陷。
  retries: 2,
  reporter: [
    ['list'],
    ['json', { outputFile: 'e2e/output/results.json' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:8100',
    trace: 'off',
    screenshot: 'only-on-failure',
    video: 'off',
    viewport: { width: 1600, height: 900 },
    locale: 'zh-CN',
    ...(chromiumExecutable
      ? { launchOptions: { executablePath: chromiumExecutable } }
      : {}),
  },
  globalSetup: './e2e/global-setup.ts',
});
