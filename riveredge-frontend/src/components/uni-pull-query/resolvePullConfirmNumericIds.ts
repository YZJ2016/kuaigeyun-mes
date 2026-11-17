import type React from 'react';
import { normalizePullKey } from './pullRowKey';

/** 取单确认：把选中键与行数据解析为数值型源单 ID（键统一字符串化）。 */
export function resolvePullConfirmNumericIds<T extends object>(
  keys: React.Key[],
  rows: T[],
  rowKey: keyof T | string = 'id',
): number[] {
  const keySet = new Set(keys.map(normalizePullKey));
  const field = rowKey as keyof T;
  let selectedIds = rows
    .filter((row) => keySet.has(normalizePullKey(row[field] as React.Key)))
    .map((row) => Number(row[field]))
    .filter((id) => Number.isFinite(id) && id > 0);
  if (!selectedIds.length) {
    selectedIds = keys
      .map((k) => Number(normalizePullKey(k)))
      .filter((id) => Number.isFinite(id) && id > 0);
  }
  return selectedIds;
}
