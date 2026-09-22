/**
 * 列表单元格：前 N 条 MarkerTag +「等共总数条」溢出提示。
 * 字号继承表格正文；count 为总数（非剩余条数）。
 * 单据明细预览、质检步骤等共用，禁止页面再手写一套。
 */

import React from 'react';
import { MarkerTag } from '../../constants/statusBadges';

export const INLINE_MARKER_TAG_PREVIEW_MAX = 2;

const TAG_STYLE: React.CSSProperties = {
  fontSize: 'inherit',
  lineHeight: 'inherit',
};

export type InlineMarkerTagPreviewOptions = {
  /** 直接展示的条数，默认 2 */
  previewMax?: number;
  /** 溢出文案，入参为标签总数；未传则不显示「等共…」 */
  formatMore?: (totalCount: number) => React.ReactNode;
};

/**
 * @param labels 已排好序、已去空的文案列表
 */
export function renderInlineMarkerTagPreview(
  labels: string[],
  options?: InlineMarkerTagPreviewOptions,
): React.ReactNode {
  if (!labels.length) return '-';
  const previewMax = options?.previewMax ?? INLINE_MARKER_TAG_PREVIEW_MAX;
  const preview = labels.slice(0, previewMax);
  const totalCount = labels.length;
  const hasMore = totalCount > preview.length;
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 4,
        minWidth: 0,
        maxWidth: '100%',
      }}
    >
      {preview.map((text, index) => (
        <MarkerTag key={`${index}-${text}`} style={TAG_STYLE}>
          {text}
        </MarkerTag>
      ))}
      {hasMore && options?.formatMore ? (
        <MarkerTag color="default" style={TAG_STYLE}>
          {options.formatMore(totalCount)}
        </MarkerTag>
      ) : null}
    </div>
  );
}
