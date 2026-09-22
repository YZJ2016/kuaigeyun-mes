import React, { Children } from 'react';
import { Col, Grid } from 'antd';
import { MODULE_CENTER_GUTTER } from './constants';

export interface ModuleActionMasonryProps {
  children: React.ReactNode;
  /** 大屏列数，默认 2 */
  columns?: number;
}

function distributeRoundRobin(items: React.ReactNode[], columnCount: number): React.ReactNode[][] {
  const cols: React.ReactNode[][] = Array.from({ length: columnCount }, () => []);
  items.forEach((child, index) => {
    cols[index % columnCount].push(child);
  });
  return cols;
}

/**
 * 事项区瀑布流：固定列宽的独立纵列，按 JSX 声明序左右轮流入列。
 * 禁止 CSS grid 同行拉齐；禁止 CSS column-count（Table / 图表列宽振荡）。
 */
export function ModuleActionMasonry({
  children,
  columns = 2,
}: ModuleActionMasonryProps) {
  const screens = Grid.useBreakpoint();
  const items = Children.toArray(children).filter(Boolean);
  if (items.length === 0) return null;

  const columnCount = screens.lg && items.length > 1 ? columns : 1;
  const cols = distributeRoundRobin(items, columnCount);

  return (
    <Col span={24}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: MODULE_CENTER_GUTTER,
        }}
      >
        {cols.map((colItems, colIndex) => (
          <div
            key={colIndex}
            style={{
              flex: 1,
              minWidth: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: MODULE_CENTER_GUTTER,
            }}
          >
            {colItems}
          </div>
        ))}
      </div>
    </Col>
  );
}

export default ModuleActionMasonry;
