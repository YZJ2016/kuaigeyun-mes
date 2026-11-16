import React from 'react';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../constants/statusBadges';

export type MaterialUnitRole = 'primary' | 'aux';

export type MaterialUnitRoleBadgeProps = {
  role: MaterialUnitRole;
  /** 单位名称（纯文字，不包进徽章） */
  unit?: string;
  className?: string;
  style?: React.CSSProperties;
};

/** 多单位主/副标识（非状态，filled 徽章） */
export const MaterialUnitRoleBadge: React.FC<MaterialUnitRoleBadgeProps> = ({
  role,
  unit,
  className,
  style,
}) => {
  const { t } = useTranslation();
  const label =
    role === 'primary'
      ? t('common.materialUnitRole.primary')
      : t('common.materialUnitRole.aux');
  const color = role === 'primary' ? 'processing' : 'default';

  return (
    <span
      className={className}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexShrink: 0, ...style }}
    >
      <MarkerTag color={color} style={{ marginInlineEnd: 0 }}>
        {label}
      </MarkerTag>
      {unit ? <span>{unit}</span> : null}
    </span>
  );
};
