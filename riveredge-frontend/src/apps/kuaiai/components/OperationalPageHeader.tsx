/**
 * KU-AI 运营层标准页头（设计 §2.2 / spec 181）。
 *
 * 标题 Typography.Title level={3}（24/32、margin 0），副标题 14px 次要色，
 * 右侧动作区 32px 高；<768px 动作区换行到标题下方左对齐。
 */

import React from 'react';
import { Typography } from 'antd';
import '../ops.less';

export interface OperationalPageHeaderProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** 右侧动作区（按钮约定 32px 高） */
  extra?: React.ReactNode;
}

const OperationalPageHeader: React.FC<OperationalPageHeaderProps> = ({
  title,
  subtitle,
  extra,
}) => {
  return (
    <div className="kuaiai-ops-header">
      <div className="kuaiai-ops-header-text">
        <Typography.Title level={3} className="kuaiai-ops-header-title">
          {title}
        </Typography.Title>
        {subtitle != null && subtitle !== '' ? (
          <div className="kuaiai-ops-header-subtitle">{subtitle}</div>
        ) : null}
      </div>
      {extra ? <div className="kuaiai-ops-header-actions">{extra}</div> : null}
    </div>
  );
};

export default OperationalPageHeader;
