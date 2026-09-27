/**
 * 全局 window resize 单例总线：一次 addEventListener，多处订阅分发（rAF 合并）。
 * 替代各组件独立挂 resize，减少重复计算。
 */

type ResizeListener = () => void;

const listeners = new Set<ResizeListener>();
let attached = false;
let rafId = 0;

function flush(): void {
  rafId = 0;
  listeners.forEach((listener) => {
    try {
      listener();
    } catch {
      /* 单订阅失败不影响其他 */
    }
  });
}

function onWindowResize(): void {
  if (rafId) return;
  rafId = window.requestAnimationFrame(flush);
}

function ensureAttached(): void {
  if (attached || typeof window === 'undefined') return;
  window.addEventListener('resize', onWindowResize, { passive: true });
  attached = true;
}

function maybeDetach(): void {
  if (!attached || listeners.size > 0 || typeof window === 'undefined') return;
  window.removeEventListener('resize', onWindowResize);
  attached = false;
  if (rafId) {
    window.cancelAnimationFrame(rafId);
    rafId = 0;
  }
}

/** 供组件订阅；返回 unsubscribe */
export function subscribeResizeBus(listener: ResizeListener): () => void {
  listeners.add(listener);
  ensureAttached();
  return () => {
    listeners.delete(listener);
    maybeDetach();
  };
}
