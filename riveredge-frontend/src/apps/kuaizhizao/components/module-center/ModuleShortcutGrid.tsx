import React, { cloneElement, isValidElement } from 'react';
import { Typography, theme } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useThemeStore } from '../../../../stores/themeStore';
import type { ModuleShortcutDef } from './types';
import { isModuleDashboardPlain } from './moduleDashboardTheme';

const { Text } = Typography;

function normalizeShortcutIcon(icon: React.ReactNode, colorPrimary: string): React.ReactNode {
  if (!isValidElement(icon)) return icon;
  const prev = (icon.props as { style?: React.CSSProperties }).style;
  return cloneElement(icon, {
    style: { ...prev, color: colorPrimary, fontSize: 20, lineHeight: 1 },
  } as { style?: React.CSSProperties });
}

/** 模块中心工作台快捷入口：图标与底纹统一主题色，不用 QuickEntry 多色芯片（右侧/顶部快捷入口不受影响） */
export function ModuleShortcutGrid({ items }: { items: ModuleShortcutDef[] }) {
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const themeStyle = useThemeStore((s) => s.resolved.themeStyle);
  const plain = isModuleDashboardPlain(themeStyle);

  return (
    <div
      className={plain ? 'module-shortcut-grid module-shortcut-grid--plain' : 'module-shortcut-grid'}
      style={{
        borderRadius: token.borderRadiusLG,
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorderSecondary}`,
        boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        padding: 8,
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'flex-start',
        alignItems: 'stretch',
        gap: 8,
      }}
    >
      {items.map((sc) => (
        <div
          key={sc.key}
          role="button"
          tabIndex={0}
          className="module-shortcut-grid__item"
          onClick={() => navigate(sc.path)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              navigate(sc.path);
            }
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-start',
            gap: 8,
            flex: '1 1 0',
            minWidth: 128,
            minHeight: 44,
            padding: '10px 12px',
            boxSizing: 'border-box',
            borderRadius: token.borderRadius,
            cursor: 'pointer',
            userSelect: 'none',
            transition: 'background 0.2s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = token.colorFillAlter;
            e.currentTarget.style.boxShadow = 'none';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.boxShadow = 'none';
          }}
        >
          <span
            className="module-shortcut-grid__icon"
            style={{
              width: 36,
              height: 36,
              borderRadius: token.borderRadius,
              background: token.colorPrimaryBg,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {normalizeShortcutIcon(sc.icon, token.colorPrimary)}
          </span>
          <Text
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: token.colorText,
              lineHeight: 1.35,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              minWidth: 0,
            }}
          >
            {sc.title}
          </Text>
        </div>
      ))}
    </div>
  );
}

export default ModuleShortcutGrid;
