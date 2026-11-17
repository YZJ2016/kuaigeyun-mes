/**
 * 列表工具栏开关。开关在左、文案在右，尺寸与间距全站一致。
 */
import React from 'react';
import { Space, Switch } from 'antd';

export function UniTableToolbarSwitch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: React.ReactNode;
}) {
  return (
    <Space align="center" size={8} className="uni-table-toolbar-switch">
      <Switch size="medium" checked={checked} onChange={onChange} />
      <span className="uni-table-toolbar-plain-label">{label}</span>
    </Space>
  );
}
