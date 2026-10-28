/**
 * 侧栏菜单图标：hover 时同尺寸从空心正方形 Morphicons 形变到当前菜单图标。
 * 静止与离开后始终显示当前图标。
 *
 * antd/ProLayout 悬停常会重渲染图标；重挂载时补一次 :hover 检测，避免漏掉 mouseenter。
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { MorphIcon, type MorphHandle, type IconInput } from 'morphicons/react';
import type { IconNode } from 'lucide';
import { getLucideIconNode } from '../../utils/lucideIconNodes';
import {
  resolveLucidePascalFromComponent,
  resolveMenuIconComponent,
  resolveMenuIconLucidePascalName,
} from '../../utils/manufacturingIcons';
import './MenuMorphIcon.less';

/** 同尺寸起始形：Lucide 空心正方形（Square） */
const MENU_MORPH_START: IconInput | null =
  getLucideIconNode('Square') || getLucideIconNode('Circle') || getLucideIconNode('Shapes');

/** 约 0.8s 到位（临界阻尼 ζ≈1；Morphicons 无独立 speed，用 stiffness/damping） */
const MENU_MORPH_SPRING = { stiffness: 48, damping: 14 } as const;

const MENU_ITEM_SELECTOR =
  '.ant-menu-item, .ant-menu-submenu-title, .ant-pro-base-menu-inline-item, .ant-pro-base-menu-inline-submenu-title';

export type MenuMorphIconProps = {
  /** ManufacturingIcons 预置键或 Lucide PascalCase */
  iconKey?: string;
  /** 已知 lucide-react 组件时反查 PascalCase */
  lucideComponent?: React.ComponentType<any>;
  /** 直接指定 Lucide PascalCase */
  lucideName?: string;
  size?: number;
  className?: string;
  strokeWidth?: number;
  color?: string;
};

export const MenuMorphIcon: React.FC<MenuMorphIconProps> = ({
  iconKey,
  lucideComponent,
  lucideName: lucideNameProp,
  size = 16,
  className,
  strokeWidth = 2,
  color = 'currentColor',
}) => {
  const hostRef = useRef<HTMLSpanElement>(null);
  const morphRef = useRef<MorphHandle>(null);
  const endNodeRef = useRef<IconNode | null>(null);
  const [motionOk, setMotionOk] = useState(true);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const sync = () => setMotionOk(!mq.matches);
    sync();
    mq.addEventListener?.('change', sync);
    return () => mq.removeEventListener?.('change', sync);
  }, []);

  const lucideName = useMemo(() => {
    if (lucideNameProp?.trim()) return lucideNameProp.trim();
    if (iconKey?.trim()) return resolveMenuIconLucidePascalName(iconKey) ?? '';
    if (lucideComponent) return resolveLucidePascalFromComponent(lucideComponent) ?? '';
    return '';
  }, [iconKey, lucideComponent, lucideNameProp]);

  const endNode = useMemo(
    () => (lucideName ? getLucideIconNode(lucideName) : null),
    [lucideName],
  );
  endNodeRef.current = endNode;

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !endNode) return;
    const item = host.closest(MENU_ITEM_SELECTOR);
    if (!item) return;

    const showEnd = () => {
      const end = endNodeRef.current;
      if (end) morphRef.current?.set(end);
    };

    const playMorph = () => {
      const end = endNodeRef.current;
      const handle = morphRef.current;
      const start = MENU_MORPH_START;
      if (!end || !handle) return;
      if (!motionOk || !start || start === end) {
        handle.set(end);
        return;
      }
      handle.set(start);
      handle.morphTo(end, MENU_MORPH_SPRING);
    };

    const onEnter = () => playMorph();
    const onLeave = () => showEnd();

    item.addEventListener('mouseenter', onEnter);
    item.addEventListener('mouseleave', onLeave);

    // 悬停中被重挂载时补播形变
    if (typeof item.matches === 'function' && item.matches(':hover')) {
      playMorph();
    }

    return () => {
      item.removeEventListener('mouseenter', onEnter);
      item.removeEventListener('mouseleave', onLeave);
    };
  }, [endNode, motionOk]);

  const hostClass = ['menu-morph-icon', className].filter(Boolean).join(' ');
  const hostStyle: React.CSSProperties = {
    width: size,
    height: size,
  };

  if (endNode) {
    return (
      <span ref={hostRef} className={hostClass} style={hostStyle}>
        <MorphIcon
          ref={morphRef}
          icon={endNode}
          size={size}
          strokeWidth={strokeWidth}
          color={color}
          spring={MENU_MORPH_SPRING}
          reducedMotion="user"
        />
      </span>
    );
  }

  const Fallback =
    (iconKey ? resolveMenuIconComponent(iconKey) : null) || lucideComponent || null;
  if (!Fallback) return null;
  return (
    <span ref={hostRef} className={hostClass} style={hostStyle}>
      <Fallback size={size} strokeWidth={strokeWidth} color={color} />
    </span>
  );
};

export default MenuMorphIcon;
