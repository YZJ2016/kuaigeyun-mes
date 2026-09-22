/**
 * 单据列表「明细」列契约（全站唯一）：
 * 前 2 条物料名 MarkerTag +「等共 N 条」（N=总数）+ 字号继承正文 + RemainderFlex。
 *
 * 页面用法：
 *   title={t('app.kuaizhizao.common.colLineMaterials')}
 *   ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS
 *   render: (_, r) => renderDocumentLineMaterialsPreview(r.items, t)
 *
 * 专用段位（发货/退货等）可覆盖 key/dataIndex，但仍须走本 render，禁止手写 Tag。
 * 样式真源：inline-marker-tag-preview。
 */

import type { ReactNode } from 'react';
import type { TFunction } from 'i18next';
import { renderInlineMarkerTagPreview } from '../inline-marker-tag-preview';

/** 列表明细物料预览列身份（rank 30.5，总数量/合计前） */
export const DOCUMENT_LINE_MATERIALS_KEY = 'line_materials';

export type DocumentLineMaterialPreviewItem = {
  material_name?: string | null;
};

export function renderDocumentLineMaterialsPreview(
  items: DocumentLineMaterialPreviewItem[] | undefined | null,
  t: TFunction,
): ReactNode {
  const names = (items || [])
    .map((it) => String(it.material_name ?? '').trim())
    .filter((text) => text.length > 0);
  return renderInlineMarkerTagPreview(names, {
    formatMore: (totalCount) => t('app.kuaizhizao.common.linesAndMore', { count: totalCount }),
  });
}

/** UniTable 列声明片段：RemainderFlex 明细预览（页面补 title + render 数据源） */
export const DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS = {
  key: DOCUMENT_LINE_MATERIALS_KEY,
  dataIndex: DOCUMENT_LINE_MATERIALS_KEY,
  minWidth: 160,
  uniTablePrimaryFlex: true,
  uniTableRemainderFlex: true,
  resizable: false,
  ellipsis: false,
  hideInSearch: true,
  onCell: () => ({ style: { whiteSpace: 'normal' as const } }),
} as const;
