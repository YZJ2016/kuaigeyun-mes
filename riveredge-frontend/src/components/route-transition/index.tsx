/**
 * 主内容区路由容器（与左侧菜单 / 标签切换联动）
 * 仅做极轻 opacity 过渡，不用位移；禁止用 key remount 子树（会导致整页闪烁）。
 */

import React, { useLayoutEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import './route-transition.css';

export function RouteTransition({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const [entering, setEntering] = useState(false);

  useLayoutEffect(() => {
    setEntering(true);
    const frame = requestAnimationFrame(() => setEntering(false));
    return () => cancelAnimationFrame(frame);
  }, [location.pathname]);

  return (
    <div
      className={`riveredge-route-transition${entering ? ' riveredge-route-transition--enter' : ''}`}
      style={{
        flex: '1 1 auto',
        minHeight: 0,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
      }}
    >
      {children}
    </div>
  );
}
