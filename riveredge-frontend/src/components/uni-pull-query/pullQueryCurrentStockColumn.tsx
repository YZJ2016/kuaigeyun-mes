import type { TFunction } from 'i18next';
import type { ColumnType } from 'antd/es/table';
import { DocumentLineTotalStockCell } from '../../apps/kuaizhizao/components/DocumentLineTotalStock';

export function pullRowMaterialId(record: object): number | null {
  const id = Number((record as { material_id?: unknown }).material_id);
  return Number.isFinite(id) && id > 0 ? id : null;
}

/** 开口行取单：当前总库存，悬停展开各仓结存（与采购申请明细同一组件） */
export function buildPullQueryCurrentStockColumn<T extends object>(
  t: TFunction,
): ColumnType<T> {
  return {
    title: t('app.kuaizhizao.warehouseOutbound.pull.colCurrentStock'),
    dataIndex: 'current_stock',
    width: 112,
    align: 'right',
    render: (_value: unknown, record: T) => (
      <DocumentLineTotalStockCell materialId={pullRowMaterialId(record)} />
    ),
  };
}
