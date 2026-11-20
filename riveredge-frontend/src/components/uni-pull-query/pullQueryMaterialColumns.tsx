import type { TFunction } from 'i18next';
import type { ColumnType } from 'antd/es/table';
import { renderPullQueryOptionalText } from './renderPullQueryEmptyValue';

/** 开口行取单：规格列紧挨物料名称，在 current_stock 之前 */
export function buildPullQueryMaterialSpecColumn<T extends { material_spec?: string | null }>(
  t: TFunction,
  options?: { width?: number; titleKey?: string },
): ColumnType<T> {
  return {
    title: t(options?.titleKey ?? 'app.kuaizhizao.purchaseOrder.col.spec'),
    dataIndex: 'material_spec',
    width: options?.width ?? 140,
    ellipsis: true,
    render: (v: string | null | undefined) => renderPullQueryOptionalText(v),
  };
}