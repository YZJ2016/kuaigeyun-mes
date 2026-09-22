/**
 * 详情抽屉停靠侧、zIndex 等壳层偏好（由关联打开入口 / 抽屉壳注入）。
 * 列表页直开抽屉可不包 Provider；业务 Modal 用 useStackedOverlayZIndex 抬层。
 */
import React, { createContext, useContext, useMemo } from 'react';
import type { DrawerProps } from 'antd';

export type DetailDrawerChrome = {
  placement?: DrawerProps['placement'];
  /** 当前详情抽屉 zIndex；嵌套 Modal 应在此之上 */
  zIndex?: number;
};

const DetailDrawerChromeContext = createContext<DetailDrawerChrome | null>(null);

export function DetailDrawerChromeProvider({
  value,
  children,
}: {
  value: DetailDrawerChrome;
  children: React.ReactNode;
}) {
  const memo = useMemo(
    () => value,
    [value.placement, value.zIndex],
  );
  return (
    <DetailDrawerChromeContext.Provider value={memo}>
      {children}
    </DetailDrawerChromeContext.Provider>
  );
}

export function useOptionalDetailDrawerChrome(): DetailDrawerChrome | null {
  return useContext(DetailDrawerChromeContext);
}
