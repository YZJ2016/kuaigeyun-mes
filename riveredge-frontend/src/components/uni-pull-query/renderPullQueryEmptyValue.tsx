import React from 'react';
import { Typography } from 'antd';
import { EMPTY_VALUE_PLACEHOLDER } from '../../utils/format';

/** 取单表空值占位（与全站 EMPTY_VALUE_PLACEHOLDER 一致，禁止短横线 -） */
export function renderPullQueryEmptyValue(): React.ReactNode {
  return <Typography.Text type="secondary">{EMPTY_VALUE_PLACEHOLDER}</Typography.Text>;
}

export function renderPullQueryOptionalText(value: unknown): React.ReactNode {
  const text = value != null ? String(value).trim() : '';
  return text ? text : renderPullQueryEmptyValue();
}

export function renderPullQueryOptionalDate(
  raw: unknown,
  format: (s: string) => string,
): React.ReactNode {
  if (raw == null || String(raw).trim() === '') {
    return renderPullQueryEmptyValue();
  }
  return format(String(raw));
}