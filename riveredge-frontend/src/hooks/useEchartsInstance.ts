/**
 * 原生 echarts 实例生命周期：创建 + 容器/窗口 resize + 卸载 dispose。
 * P5-13c 低风险路径（不做单例 pool）。调用方须先 `echarts.use([...])` 注册图表。
 * 范例见 LoginLogsWorldMap。
 */
import { useCallback, useEffect, useLayoutEffect, useRef } from 'react';
import { init, type EChartsType } from 'echarts/core';
import { subscribeResizeBus } from './useResizeBus';

export type UseEchartsInstanceResult = {
  chartRef: React.MutableRefObject<EChartsType | null>;
  getOrCreate: () => EChartsType | null;
};

/**
 * @param containerRef 图表宿主 DOM
 * @param enabled 为 false 时不 init / 不监听 resize（卸载仍 dispose）
 */
export function useEchartsInstance(
  containerRef: React.RefObject<HTMLElement | null>,
  enabled = true,
): UseEchartsInstanceResult {
  const chartRef = useRef<EChartsType | null>(null);

  const getOrCreate = useCallback((): EChartsType | null => {
    const el = containerRef.current;
    if (!el || !enabled) return null;
    if (!chartRef.current) {
      chartRef.current = init(el);
    }
    return chartRef.current;
  }, [containerRef, enabled]);

  useLayoutEffect(() => {
    if (!enabled) return;
    const el = containerRef.current;
    if (!el) return;

    const resize = () => {
      chartRef.current?.resize();
    };
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    ro?.observe(el);
    const unsubBus = subscribeResizeBus(resize);
    return () => {
      ro?.disconnect();
      unsubBus();
    };
  }, [containerRef, enabled]);

  useEffect(() => {
    return () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return { chartRef, getOrCreate };
}
