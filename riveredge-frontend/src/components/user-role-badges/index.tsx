import React from 'react';
import { Space } from 'antd';
import { renderInlineMarkerTagGroup } from '../inline-marker-tag-preview';

export type UserRoleBadgeItem = {
  uuid?: string;
  name: string;
  code?: string;
};

/** 角色多枚徽章：走 inline-marker-tag-preview，禁止 Space+Tag 分叉 */
export function UserRoleBadges({ roles }: { roles?: UserRoleBadgeItem[] | null }) {
  if (!roles?.length) return null;
  return renderInlineMarkerTagGroup(
    roles.map((role, index) => ({
      key: role.uuid || role.code || `${role.name}-${index}`,
      label: role.name,
      color: 'processing',
    })),
    { empty: null },
  );
}

export function renderUserPickOptionLabel(
  label: React.ReactNode,
  roles?: UserRoleBadgeItem[] | null,
): React.ReactNode {
  return (
    <Space size={6} wrap style={{ rowGap: 4 }}>
      <span>{label}</span>
      <UserRoleBadges roles={roles} />
    </Space>
  );
}
