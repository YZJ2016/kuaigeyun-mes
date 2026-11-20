/**
 * 请求体字段勾选行：日期/时间选择 + 「快捷」成对填充 start_/end_
 */

import React, { useMemo, useState } from 'react';
import { Button, DatePicker, Dropdown, Input, Space } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import {
  JSON_FIELD_NOW_TOKEN,
  buildJsonDateShortcutMenuItems,
  formatJsonFieldDateValue,
  isJsonDateOnlyFieldKey,
  parseJsonDateRangePair,
  parseJsonFieldDateValue,
  resolveJsonDateRangePreset,
  type JsonDateRangePreset,
  type JsonDateShortcutMenuItem,
  type JsonDateShortcutMenuKey,
} from './jsonFieldDateShortcuts';

export type JsonFieldDateValueEditorProps = {
  fieldKey: string;
  value: string;
  disabled?: boolean;
  onChange: (next: string) => void;
  onPairFill: (startValue: string, endValue: string) => void;
  onClearPair: () => void;
};

export const JsonFieldDateValueEditor: React.FC<JsonFieldDateValueEditorProps> = ({
  fieldKey,
  value,
  disabled = false,
  onChange,
  onPairFill,
  onClearPair,
}) => {
  const dateOnly = isJsonDateOnlyFieldKey(fieldKey);
  const pair = parseJsonDateRangePair(fieldKey);
  const isNow = value.trim() === JSON_FIELD_NOW_TOKEN;
  const parsed = useMemo(
    () => (isNow ? null : parseJsonFieldDateValue(value, dateOnly)),
    [value, dateOnly, isNow],
  );
  // 仅在打开下拉时生成，避免挂载阶段强依赖站点时区
  const [menuItems, setMenuItems] = useState<JsonDateShortcutMenuItem[]>([]);

  const handleShortcut = (key: JsonDateShortcutMenuKey) => {
    if (key === 'clear') {
      onClearPair();
      return;
    }
    if (key === 'now') {
      onChange(JSON_FIELD_NOW_TOKEN);
      return;
    }
    const preset = key as JsonDateRangePreset;
    const { start, end } = resolveJsonDateRangePreset(preset);
    const startText = formatJsonFieldDateValue(start, dateOnly);
    const endText = formatJsonFieldDateValue(end, dateOnly);
    if (pair) {
      onPairFill(startText, endText);
      return;
    }
    onChange(startText);
  };

  const dropdownItems: MenuProps['items'] = menuItems.map((item) => ({
    key: item.key,
    label: item.label,
  }));

  return (
    <Space.Compact className="custom-field-json-tree__date-value" style={{ width: '100%' }}>
      {isNow ? (
        <Input
          readOnly
          disabled={disabled}
          value="此刻（每次调用）"
          title="每次实际调用时替换为当前站点时间"
          style={{ flex: 1, minWidth: 0 }}
        />
      ) : (
        <DatePicker
          showTime={dateOnly ? false : { format: 'HH:mm:ss' }}
          format={dateOnly ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH:mm:ss'}
          value={parsed ?? undefined}
          disabled={disabled}
          allowClear
          placeholder={dateOnly ? '选择日期' : '选择日期时间'}
          style={{ flex: 1, minWidth: 0, width: '100%' }}
          onChange={(next) => {
            if (!next) {
              onChange('');
              return;
            }
            onChange(formatJsonFieldDateValue(next, dateOnly));
          }}
        />
      )}
      <Dropdown
        disabled={disabled}
        trigger={['click']}
        onOpenChange={(open) => {
          if (open) setMenuItems(buildJsonDateShortcutMenuItems(dateOnly));
        }}
        menu={{
          items: dropdownItems,
          onClick: ({ key }) => handleShortcut(key as JsonDateShortcutMenuKey),
        }}
      >
        <Button disabled={disabled}>
          快捷 <DownOutlined />
        </Button>
      </Dropdown>
    </Space.Compact>
  );
};
