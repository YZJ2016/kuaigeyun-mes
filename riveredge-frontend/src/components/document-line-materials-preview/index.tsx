/**
 * 单据列表「明细」列契约（全站唯一）：
 * 前 2 条物料名 MarkerTag +「等共 N 条」（N=总数）+ 字号继承正文 + RemainderFlex。
 *
 * 明细列 Popover（hover）：全部行按「品名 - 品号 规格 型号」展示（单元格仍前 2 品名 + 等共 N 条）。
 *
 * 页面用法：
 *   title={t('app.kuaizhizao.common.colLineMaterials')}
 *   ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS
 *   render: (_, r) => renderDocumentLineMaterialsPreview(r.items, t)
 *
 * 出库 Hub 等已去掉独立「规格型号」列；规格/型号在明细列 Popover 查看。
 * renderDocumentLineMaterialSpecsPreview 仅保留给历史列配置兼容，新页勿再挂列。
 *
 * 专用段位（发货/退货等）可覆盖 key/dataIndex，但仍须走本 render，禁止手写 Tag。
 * 样式真源：inline-marker-tag-preview。
 */

import type { ReactNode } from 'react';
import type { TFunction } from 'i18next';
import { Popover } from 'antd';
import { renderInlineMarkerTagPreview } from '../inline-marker-tag-preview';

/** 列表明细物料预览列身份（rank 29.5，总数量/合计前） */
export const DOCUMENT_LINE_MATERIALS_KEY = 'line_materials';

/** 列表明细规格型号预览列身份（rank 29.6，紧随明细） */
export const DOCUMENT_LINE_MATERIAL_SPECS_KEY = 'line_material_specs';

export type DocumentLineMaterialPreviewItem = {
  material_name?: string | null;
  material_code?: string | null;
  material_spec?: string | null;
  material_model?: string | null;
};

/** 列表 Popover 单行：品名 - 品号 规格 型号（缺段省略，不拼占位符） */
export function formatDocumentLineMaterialSpecTooltipLine(
  it: DocumentLineMaterialPreviewItem,
): string {
  const name = String(it.material_name ?? '').trim();
  const code = String(it.material_code ?? '').trim();
  const spec = String(it.material_spec ?? '').trim();
  const model = String(it.material_model ?? '').trim();
  const head =
    name && code ? `${name} - ${code}` : name || code;
  const tail = [spec, model].filter((part) => part.length > 0).join(' ');
  if (head && tail) return `${head} ${tail}`;
  return head || tail;
}

function wrapLineMaterialsPopover(
  body: ReactNode,
  lines: string[],
  popoverTitle: ReactNode,
): ReactNode {
  if (!lines.length) {
    return body;
  }
  const content = (
    <ul
      className="uni-table-line-materials-popover"
      style={{
        margin: 0,
        paddingLeft: 18,
        maxHeight: 320,
        overflowY: 'auto',
        lineHeight: 1.55,
        maxWidth: 480,
        listStyleType: 'disc',
      }}
    >
      {lines.map((line, index) => (
        <li key={`${index}-${line}`} style={{ marginBottom: 4 }}>
          {line}
        </li>
      ))}
    </ul>
  );
  return (
    <Popover
      trigger="hover"
      placement="topLeft"
      title={popoverTitle}
      content={content}
      getPopupContainer={() => document.body}
    >
      <span
        className="uni-table-line-materials-hover"
        style={{ cursor: 'default', display: 'inline-block', maxWidth: '100%' }}
      >
        {body}
      </span>
    </Popover>
  );
}

export function renderDocumentLineMaterialsPreview(
  items: DocumentLineMaterialPreviewItem[] | undefined | null,
  t: TFunction,
): ReactNode {
  const rows = items || [];
  const names = rows
    .map((it) => String(it.material_name ?? '').trim())
    .filter((text) => text.length > 0);
  const body = renderInlineMarkerTagPreview(names, {
    formatMore: (totalCount) => t('app.kuaizhizao.common.linesAndMore', { count: totalCount }),
  });
  const detailLines = rows
    .map((it) => formatDocumentLineMaterialSpecTooltipLine(it))
    .filter((line) => line.length > 0);
  return wrapLineMaterialsPopover(body, detailLines, t('app.kuaizhizao.common.colLineMaterials'));
}

export function renderDocumentLineMaterialSpecsPreview(
  items: DocumentLineMaterialPreviewItem[] | undefined | null,
  t: TFunction,
): ReactNode {
  const specs = (items || [])
    .map((it) => String(it.material_spec ?? '').trim())
    .filter((text) => text.length > 0);
  return renderInlineMarkerTagPreview(specs, {
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

/** UniTable 列声明片段：KeepWidth 规格型号预览（紧随明细） */
export const DOCUMENT_LINE_MATERIAL_SPECS_COLUMN_WIDTH_FLAGS = {
  key: DOCUMENT_LINE_MATERIAL_SPECS_KEY,
  dataIndex: DOCUMENT_LINE_MATERIAL_SPECS_KEY,
  width: 140,
  minWidth: 140,
  uniTableKeepWidth: true,
  resizable: false,
  ellipsis: false,
  hideInSearch: true,
  onCell: () => ({ style: { whiteSpace: 'normal' as const } }),
} as const;

/** 列表行 `items` 明细预览文本拼串，供 Hub/本地关键词二次筛选（与后端明细反查一致） */
export function documentLineMaterialKeywordHaystack(
  row: Record<string, unknown> | { items?: unknown },
): string {
  const items =
    'items' in row && row.items !== undefined
      ? row.items
      : (row as Record<string, unknown>).items;
  if (!Array.isArray(items)) return '';
  return items
    .flatMap((it) => {
      if (!it || typeof it !== 'object') return [];
      const line = it as Record<string, unknown>;
      return [
        line.material_name,
        line.material_code,
        line.material_spec,
        line.material_model,
        line.name,
        line.code,
      ];
    })
    .map((x) => String(x ?? '').toLowerCase())
    .join(' ');
}
