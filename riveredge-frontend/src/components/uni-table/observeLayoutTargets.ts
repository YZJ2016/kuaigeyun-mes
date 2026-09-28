/**
 * 单例 ResizeObserver：多元素 observe，按 element 分发回调；
 * 同时订阅全局 resize bus，禁止各处再挂 window.resize。
 */

import { subscribeResizeBus } from '../../hooks/useResizeBus'

type LayoutResizeCallback = () => void

const elementCallbacks = new Map<Element, Set<LayoutResizeCallback>>()
let sharedRo: ResizeObserver | null = null

function getSharedRo(): ResizeObserver | null {
  if (typeof ResizeObserver === 'undefined') return null
  if (!sharedRo) {
    sharedRo = new ResizeObserver((entries) => {
      const fired = new Set<LayoutResizeCallback>()
      for (const entry of entries) {
        const cbs = elementCallbacks.get(entry.target)
        if (!cbs) continue
        cbs.forEach((cb) => fired.add(cb))
      }
      fired.forEach((cb) => {
        try {
          cb()
        } catch {
          /* 单订阅失败不影响其他 */
        }
      })
    })
  }
  return sharedRo
}

/**
 * 观察一组布局相关元素；任一尺寸变化时调用 onResize；
 * window resize 默认同 onResize，可用 onWindowResize 覆盖（如 report 测高允许关限高）。
 * 返回 unsubscribe（unobserve + 退订 bus）。
 */
export function observeLayoutTargets(
  elements: Array<Element | null | undefined>,
  onResize: LayoutResizeCallback,
  options?: { onWindowResize?: LayoutResizeCallback },
): () => void {
  const ro = getSharedRo()
  const observed: Element[] = []

  for (const el of elements) {
    if (!el) continue
    let set = elementCallbacks.get(el)
    if (!set) {
      set = new Set()
      elementCallbacks.set(el, set)
      ro?.observe(el)
    }
    set.add(onResize)
    observed.push(el)
  }

  const unsubBus = subscribeResizeBus(options?.onWindowResize ?? onResize)

  return () => {
    for (const el of observed) {
      const set = elementCallbacks.get(el)
      if (!set) continue
      set.delete(onResize)
      if (set.size === 0) {
        elementCallbacks.delete(el)
        ro?.unobserve(el)
      }
    }
    unsubBus()
  }
}
