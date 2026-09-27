/**
 * P5-13b：@ant-design/charts 组件懒加载，避免业务页静态绑 charts chunk。
 */
import React, { Suspense, type ComponentType, type ReactNode } from 'react';

export const LazyArea = React.lazy(() =>
  import('@ant-design/charts').then((m) => ({ default: m.Area as ComponentType<any> })),
);
export const LazyColumn = React.lazy(() =>
  import('@ant-design/charts').then((m) => ({ default: m.Column as ComponentType<any> })),
);
export const LazyLine = React.lazy(() =>
  import('@ant-design/charts').then((m) => ({ default: m.Line as ComponentType<any> })),
);
export const LazyPie = React.lazy(() =>
  import('@ant-design/charts').then((m) => ({ default: m.Pie as ComponentType<any> })),
);
export const LazyScatter = React.lazy(() =>
  import('@ant-design/charts').then((m) => ({ default: m.Scatter as ComponentType<any> })),
);
export const LazyBar = React.lazy(() =>
  import('@ant-design/charts').then((m) => ({ default: m.Bar as ComponentType<any> })),
);
export const LazySankey = React.lazy(() =>
  import('@ant-design/charts').then((m) => ({ default: m.Sankey as ComponentType<any> })),
);

export function ChartSuspense({
  children,
  fallback = null,
}: {
  children: ReactNode;
  fallback?: ReactNode;
}) {
  return <Suspense fallback={fallback}>{children}</Suspense>;
}
