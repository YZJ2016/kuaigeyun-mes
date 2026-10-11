/**
 * KU-AI 运营层指标卡（设计 §2/§4.3 / spec 181）。
 *
 * - value 为 null/undefined 显示「—」：数据源失败不得伪造为 0；
 * - onClick 存在且未禁用时整卡可点，键盘 Enter/Space 可触发并带可见 focus；
 * - 禁用态用 Tooltip 说明原因（无权限/路由缺失），不产生 404 跳转。
 */

import React from 'react';
import { Tooltip } from 'antd';
import '../ops.less';

export interface MetricCardProps {
  title: React.ReactNode;
  /** null/undefined → 「—」（接口失败或缺失） */
  value?: number | null;
  unit?: React.ReactNode;
  description?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  disabledReason?: React.ReactNode;
}

const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  unit,
  description,
  onClick,
  disabled = false,
  disabledReason,
}) => {
  const clickable = Boolean(onClick) && !disabled;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!clickable) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick?.();
    }
  };

  const card = (
    <div
      className={`kuaiai-ops-metric${clickable ? ' kuaiai-ops-metric--clickable' : ''}`}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      aria-disabled={disabled || undefined}
      onClick={clickable ? onClick : undefined}
      onKeyDown={handleKeyDown}
    >
      <div className="kuaiai-ops-metric-title">{title}</div>
      <div className="kuaiai-ops-metric-value">
        {value === null || value === undefined ? '—' : value}
        {value !== null && value !== undefined && unit ? (
          <span className="kuaiai-ops-metric-unit">{unit}</span>
        ) : null}
      </div>
      {description ? <div className="kuaiai-ops-metric-desc">{description}</div> : null}
    </div>
  );

  if (disabled && disabledReason) {
    return <Tooltip title={disabledReason}>{card}</Tooltip>;
  }
  return card;
};

export default MetricCard;
