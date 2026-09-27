/**
 * P5-13b：@ant-design/graphs 组件懒加载；非组件导出（RCNode / getNodeSide）挂载时动态 import。
 */
import React, {
  Suspense,
  useEffect,
  useState,
  type ComponentType,
  type ReactNode,
} from 'react';

export const LazyMindMap = React.lazy(() =>
  import('@ant-design/graphs').then((m) => ({ default: m.MindMap as ComponentType<any> })),
);
export const LazyFlowGraph = React.lazy(() =>
  import('@ant-design/graphs').then((m) => ({ default: m.FlowGraph as ComponentType<any> })),
);

export type AntGraphsApi = {
  getNodeSide: (...args: any[]) => any;
  RCNode: any;
};

/** 挂载时加载 getNodeSide / RCNode 等非组件导出（无静态顶层 import） */
export function useAntGraphsApi(): AntGraphsApi | null {
  const [api, setApi] = useState<AntGraphsApi | null>(null);
  useEffect(() => {
    let cancelled = false;
    import('@ant-design/graphs').then((m) => {
      if (!cancelled) {
        setApi({ getNodeSide: m.getNodeSide, RCNode: m.RCNode });
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return api;
}

export function GraphSuspense({
  children,
  fallback = null,
}: {
  children: ReactNode;
  fallback?: ReactNode;
}) {
  return <Suspense fallback={fallback}>{children}</Suspense>;
}
