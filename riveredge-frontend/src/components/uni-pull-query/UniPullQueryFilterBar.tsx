import React, { useMemo } from 'react';
import { DatePicker, Flex, Input, theme } from 'antd';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ThemedSegmented } from '../themed-segmented';
import type { UniPullQueryScopeOption } from './types';

const { RangePicker } = DatePicker;

export interface UniPullQueryFilterBarProps {
  searchDraft: string;
  onSearchDraftChange: (value: string) => void;
  onSearchApply: (value: string) => void;
  onSearchClear: () => void;
  searchPlaceholder?: string;
  scopeOptions?: UniPullQueryScopeOption[];
  scope?: string;
  onScopeChange?: (scope: string) => void;
  /** 搜索框右侧扩展筛选（如分类、来源类型） */
  filterExtra?: ReactNode;
  /** inline：放在搜索框右侧（默认）；block：独占下一行，不与搜索框抢宽 */
  filterExtraPlacement?: 'inline' | 'block';
  enableDateFilter?: boolean;
  dateDraftFrom?: string;
  dateDraftTo?: string;
  onDateDraftChange?: (from?: string, to?: string) => void;
  onDateApply?: (from?: string, to?: string) => void;
  onDateClear?: () => void;
}

/**
 * 加载取单筛选栏，样式对齐 UniMaterialBatchPicker。
 */
export const UniPullQueryFilterBar: React.FC<UniPullQueryFilterBarProps> = ({
  searchDraft,
  onSearchDraftChange,
  onSearchApply,
  onSearchClear,
  searchPlaceholder,
  scopeOptions,
  scope,
  onScopeChange,
  filterExtra,
  filterExtraPlacement = 'inline',
  enableDateFilter = true,
  dateDraftFrom,
  dateDraftTo,
  onDateDraftChange,
  onDateApply,
  onDateClear,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const placeExtraBelow = filterExtraPlacement === 'block' && filterExtra != null;

  const dateRangeValue = useMemo((): [Dayjs | null, Dayjs | null] | null => {
    if (!dateDraftFrom && !dateDraftTo) return null;
    const start = dateDraftFrom ? dayjs(dateDraftFrom, 'YYYY-MM-DD') : null;
    const end = dateDraftTo ? dayjs(dateDraftTo, 'YYYY-MM-DD') : null;
    if (!start?.isValid() && !end?.isValid()) return null;
    return [start?.isValid() ? start : null, end?.isValid() ? end : null];
  }, [dateDraftFrom, dateDraftTo]);

  const searchRow = (
    <Flex gap={8} align="center" style={{ width: '100%' }}>
      {scopeOptions && scopeOptions.length > 0 && scope != null && onScopeChange ? (
        <ThemedSegmented
          surfaceBackground
          value={scope}
          options={scopeOptions}
          onChange={(value) => onScopeChange(String(value))}
          style={{ flexShrink: 0 }}
        />
      ) : null}
      {enableDateFilter && onDateDraftChange && onDateApply ? (
        <RangePicker
          allowClear
          size="medium"
          format="YYYY-MM-DD"
          placeholder={[
            t('components.uniPullQuery.dateFromPlaceholder'),
            t('components.uniPullQuery.dateToPlaceholder'),
          ]}
          value={dateRangeValue}
          style={{ flexShrink: 0, width: 240 }}
          onChange={(values) => {
            if (!values || (!values[0] && !values[1])) {
              onDateDraftChange(undefined, undefined);
              onDateClear?.();
              onDateApply(undefined, undefined);
              return;
            }
            const from = values[0]?.isValid() ? values[0].format('YYYY-MM-DD') : undefined;
            const to = values[1]?.isValid() ? values[1].format('YYYY-MM-DD') : undefined;
            onDateDraftChange(from, to);
            if (from && to) {
              onDateApply(from, to);
            }
          }}
        />
      ) : null}
      <Input.Search
        allowClear
        placeholder={searchPlaceholder}
        style={{ flex: 1, minWidth: 0 }}
        value={searchDraft}
        onChange={(e) => onSearchDraftChange(e.target.value)}
        onSearch={(value) => onSearchApply(value)}
        onClear={onSearchClear}
      />
      {placeExtraBelow ? null : filterExtra}
    </Flex>
  );

  return (
    <div
      style={{
        padding: 12,
        marginBottom: 12,
        background: token.colorFillAlter,
        borderRadius: token.borderRadius,
        border: `1px solid ${token.colorBorderSecondary}`,
      }}
    >
      {placeExtraBelow ? (
        <Flex vertical gap={12} style={{ width: '100%' }}>
          {searchRow}
          <div style={{ width: '100%' }}>{filterExtra}</div>
        </Flex>
      ) : (
        searchRow
      )}
    </div>
  );
};
