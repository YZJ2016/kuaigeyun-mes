import { isCancelledError } from '@tanstack/react-query';

/**
 * 请求被主动取消（租户切换 cancelQueries、AbortSignal、用户离开页面）。
 * 这是控制流，不是业务失败，不得弹 Toast / 不得当网络错误。
 */
export function isRequestCancellation(error: unknown): boolean {
  if (error == null) return false;
  if (isCancelledError(error)) return true;

  const err = error as {
    name?: string;
    message?: string;
    code?: string;
    originalError?: unknown;
  };

  const name = err.name;
  if (name === 'AbortError' || name === 'CancelledError' || name === 'CanceledError') {
    return true;
  }
  if (err.code === 'ERR_CANCELED' || err.code === 'ERR_ABORTED') {
    return true;
  }
  if (err.message === 'CancelledError' || err.message === 'CanceledError') {
    return true;
  }
  if (err.originalError && err.originalError !== error) {
    return isRequestCancellation(err.originalError);
  }
  return false;
}

/** 预取等 fire-and-forget：取消可结束；其它错误仍抛出让未处理拒绝暴露 */
export function swallowRequestCancellation(error: unknown): void {
  if (isRequestCancellation(error)) return;
  throw error;
}

/**
 * apiRequest 在途 AbortController 注册表。
 *
 * React Query 的 cancelQueries 不会自动 abort 未接 signal 的 fetch；
 * 切换组织前必须真正中断旧 HTTP，否则旧菜单徽章/导航树等仍占后端连接池，
 * 叠加新租户壳层请求易打满池并被网关打成 502。
 */
const inflightApiAbortControllers = new Set<AbortController>();

export function trackInflightApiAbortController(controller: AbortController): () => void {
  inflightApiAbortControllers.add(controller);
  return () => {
    inflightApiAbortControllers.delete(controller);
  };
}

export function abortAllInflightApiRequests(reason?: unknown): void {
  const abortReason =
    reason ??
    new DOMException('Aborted due to tenant switch', 'AbortError');
  for (const controller of [...inflightApiAbortControllers]) {
    try {
      controller.abort(abortReason);
    } catch {
      // 已结束的 controller 忽略
    }
  }
  inflightApiAbortControllers.clear();
}
