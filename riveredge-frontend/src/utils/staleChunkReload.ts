/**
 * 发版后旧 tab / 磁盘缓存仍引用已下线的 hashed chunk 时，
 * 动态 import 会报 Failed to fetch dynamically imported module。
 * 生产环境自动硬刷新一次；换到新构建后标记才失效，便于下次发版再恢复。
 *
 * 自动刷新必须留痕：否则刷新会清空控制台，现场无法复盘（历史上「系统加载后
 * 过一会儿自己刷一下」就是这样查不到源头的）。原因写入 localStorage，
 * 下次启动打印一次。
 */

const RELOAD_FLAG_KEY = 're:stale-chunk-reload';
const RELOAD_REASON_KEY = 're:last-auto-reload';

/** 每个构建只允许自动刷一次：刷完仍是同一构建说明刷新解决不了，须暴露错误 */
function currentBuildId(): string {
  return typeof __BUILD_TIME__ === 'string' ? __BUILD_TIME__ : 'unknown';
}

export function isStaleChunkError(error: unknown): boolean {
  const name = error instanceof Error ? error.name : '';
  if (name === 'ChunkLoadError') return true;

  const msg = (
    error instanceof Error ? error.message : String(error ?? '')
  ).toLowerCase();

  return (
    msg.includes('failed to fetch dynamically imported module') ||
    msg.includes('error loading dynamically imported module') ||
    msg.includes('importing a module script failed') ||
    msg.includes('unable to preload css')
  );
}

function recordAutoReloadReason(reason: string, detail: string): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(
      RELOAD_REASON_KEY,
      JSON.stringify({
        at: new Date().toISOString(),
        reason,
        detail: detail.slice(0, 500),
        from: window.location.href,
        buildId: currentBuildId(),
      }),
    );
  } catch {
    // localStorage 不可用时不阻塞刷新
  }
}

/** 取上一次自动刷新的原因（诊断用；读后不清除，便于用户复述） */
export function getLastAutoReloadReason(): {
  at: string;
  reason: string;
  detail: string;
  from: string;
  buildId: string;
} | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(RELOAD_REASON_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/**
 * @param detail 触发刷新的原始错误信息，用于留痕
 * @returns true 表示已发起刷新，调用方勿再抛给用户
 */
export function reloadForStaleChunkOnce(detail = ''): boolean {
  if (typeof window === 'undefined' || typeof sessionStorage === 'undefined') {
    return false;
  }
  const buildId = currentBuildId();
  // 同一构建已自动刷过一次：再刷只会循环，交回调用方抛错
  if (sessionStorage.getItem(RELOAD_FLAG_KEY) === buildId) {
    return false;
  }
  try {
    sessionStorage.setItem(RELOAD_FLAG_KEY, buildId);
  } catch {
    // sessionStorage 不可用时仍尝试刷新一次
  }
  recordAutoReloadReason('stale-chunk', detail);
  window.location.reload();
  return true;
}

/**
 * 应用成功挂载后调用：仅当运行的已是另一个构建时才放行下一次自动刷新。
 * 刷新后仍是同一构建说明资源问题没被刷新解决，须保留标记避免无限自刷。
 */
export function clearStaleChunkReloadFlag(): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
    const flagged = sessionStorage.getItem(RELOAD_FLAG_KEY);
    if (flagged && flagged !== currentBuildId()) {
      sessionStorage.removeItem(RELOAD_FLAG_KEY);
    }
  } catch {
    // ignore
  }
}

/** 在入口注册：Vite preload 失败 + 未捕获的动态 import 失败 */
export function installStaleChunkReloadHandlers(): void {
  if (typeof window === 'undefined' || !import.meta.env.PROD) return;

  const last = getLastAutoReloadReason();
  if (last) {
    console.warn(
      `[auto-reload] 上次整页自动刷新：${last.reason} @ ${last.at}\n来源：${last.from}\n明细：${last.detail}`,
    );
  }

  window.addEventListener('vite:preloadError', (event) => {
    const payload = (event as Event & { payload?: unknown }).payload;
    const detail =
      payload instanceof Error ? `${payload.message}` : String(payload ?? 'vite:preloadError');
    if (reloadForStaleChunkOnce(detail)) {
      event.preventDefault();
    }
  });

  window.addEventListener('unhandledrejection', (event) => {
    if (!isStaleChunkError(event.reason)) return;
    const reason = event.reason;
    const detail = reason instanceof Error ? reason.message : String(reason ?? '');
    if (reloadForStaleChunkOnce(detail)) {
      event.preventDefault();
    }
  });
}
