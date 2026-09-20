/** 与 index.html 首屏看门狗约定的全局标记（主 bundle 已开始执行） */
export const APP_BOOT_STARTED_FLAG = '__RE_APP_BOOT_STARTED__';

declare global {
  interface Window {
    [APP_BOOT_STARTED_FLAG]?: boolean;
  }
}

/**
 * 主 bundle 同步入口调用：卸掉 index.html 静态首屏占位，并通知看门狗勿再整页 reload。
 * 须在 mountApp 内任何 await 之前执行，避免 i18n/持久化耗时时误触 15s 自动刷新。
 */
export function signalAppBootStarted(): void {
  if (typeof window === 'undefined') return;
  window[APP_BOOT_STARTED_FLAG] = true;
  document.getElementById('app-loading')?.remove();
  document.querySelector('[data-app-first-paint]')?.remove();
}

export function isAppBootStarted(): boolean {
  return typeof window !== 'undefined' && window[APP_BOOT_STARTED_FLAG] === true;
}
