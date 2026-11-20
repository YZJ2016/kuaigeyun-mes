/**
 * 客户/供应商名称展示（角色字段权限 party_name：明文 / 脱敏 / 隐藏）
 */

import React from 'react';
import { Tooltip } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { useUserFieldMasks } from '../../hooks/useUserFieldMasks';
import { resolveFieldMaskLevel } from '../../utils/fieldMaskPermission';

export interface PartyNameDisplayProps {
  resource?: string;
  /** customer_name / supplier_name；未传时按 party_name 策略类解析 */
  fieldName?: 'customer_name' | 'supplier_name' | 'party_name';
  value?: string | null;
  maskText?: string;
  className?: string;
  style?: React.CSSProperties;
}

export const PartyNameDisplay: React.FC<PartyNameDisplayProps> = ({
  resource,
  fieldName = 'party_name',
  value,
  maskText = '***',
  className,
  style,
}) => {
  const fieldMasks = useUserFieldMasks();
  const level = resolveFieldMaskLevel(fieldMasks, resource, fieldName);

  const text = String(value ?? '').trim();

  if (level === 'hidden') {
    return (
      <span className={className} style={{ color: 'rgba(0, 0, 0, 0.25)', ...style }}>
        —
      </span>
    );
  }

  if (level === 'masked') {
    return (
      <Tooltip title="无权限查看客户/供应商名称">
        <span
          className={className}
          style={{ color: 'rgba(0, 0, 0, 0.45)', cursor: 'help', ...style }}
        >
          {maskText} <LockOutlined style={{ fontSize: 10 }} />
        </span>
      </Tooltip>
    );
  }

  if (!text) {
    return (
      <span className={className} style={style}>
        —
      </span>
    );
  }

  return (
    <span className={className} style={style}>
      {text}
    </span>
  );
};

export default PartyNameDisplay;