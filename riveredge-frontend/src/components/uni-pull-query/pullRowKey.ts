import type React from 'react';

/** 选中 key 统一成字符串：antd Table 用 === 比对，数字 id 与 "id" 不一致时勾不亮、已选条仍有。 */
export function normalizePullKey(key: React.Key): string {
  return String(key);
}

export function resolvePullRowKey<T extends object>(
  record: T,
  rowKey: string | ((record: T) => React.Key),
): string {
  if (typeof rowKey === 'function') {
    return normalizePullKey(rowKey(record));
  }
  return normalizePullKey((record as Record<string, unknown>)[rowKey] as React.Key);
}
