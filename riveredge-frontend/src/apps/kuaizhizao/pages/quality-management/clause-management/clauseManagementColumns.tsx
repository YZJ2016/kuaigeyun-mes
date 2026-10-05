import React, { ReactNode } from 'react';
import { theme, Typography } from 'antd';
import { TWO_COLUMN_LAYOUT, TWO_COLUMN_LEFT_PANEL_BACKGROUND } from '../../../../../components/layout-templates/constants';

type ClauseManagementColumnProps = {
  title: string;
  toolbar?: ReactNode;
  children: ReactNode;
  width?: number;
  flex?: number;
  isLast?: boolean;
  /** 内容区容器内边距（px），默认 8 */
  bodyPadding?: number;
  /** 滚动内容区 className（条款目录传 two-column-layout-left-tree 与全站左栏树一致） */
  bodyClassName?: string;
};

export const ClauseManagementColumn: React.FC<ClauseManagementColumnProps> = ({
  title,
  toolbar,
  children,
  width,
  flex,
  isLast,
  bodyPadding = 8,
  bodyClassName,
}) => {
  const { token } = theme.useToken();
  return (
    <div
      style={{
        width: width != null ? width : undefined,
        flex: flex ?? (width == null ? 1 : '0 0 auto'),
        minWidth: width ?? 280,
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        height: '100%',
        borderRight: isLast ? undefined : `1px solid ${token.colorBorder}`,
        backgroundColor: width != null ? TWO_COLUMN_LEFT_PANEL_BACKGROUND : token.colorBgContainer,
      }}
    >
      <div
        style={{
          height: TWO_COLUMN_LAYOUT.PANEL_HEADER_HEIGHT,
          minHeight: TWO_COLUMN_LAYOUT.PANEL_HEADER_HEIGHT,
          padding: '0 12px',
          borderBottom: `1px solid ${token.colorBorder}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          flexShrink: 0,
          boxSizing: 'border-box',
        }}
      >
        <Typography.Text strong ellipsis style={{ flex: 1, minWidth: 0 }}>
          {title}
        </Typography.Text>
        {toolbar ? <div style={{ flexShrink: 0 }}>{toolbar}</div> : null}
      </div>
      <div
        className={['scrollbar-like-modal', bodyClassName].filter(Boolean).join(' ')}
        style={{
          flex: 1,
          minHeight: 0,
          overflow: 'auto',
          padding: bodyPadding,
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {children}
      </div>
    </div>
  );
};
