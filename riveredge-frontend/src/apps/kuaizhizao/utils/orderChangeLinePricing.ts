import dayjs from 'dayjs';
import type { Material } from '../../master-data/types/material';
import {
  resolveOrderLinePurchasePrice,
  resolveOrderLineSalePrice,
} from '../../master-data/utils/resolve-partner-material-price';
import type { OrderChangeItem } from '../services/sales-order-change';

/** 源订单行：改数量不自动改 after_unit_price；纯新增 LINE_ADD 可走 resolver */
export function isOrderChangeLineUnitPriceLocked(row: OrderChangeItem): boolean {
  if (row.change_type === 'LINE_CANCEL') return true;
  if (row.source_item_id != null && row.change_type !== 'LINE_ADD') return true;
  return false;
}

export async function resolveOrderChangeLineAfterUnitPrice(
  side: 'sales' | 'purchase',
  partnerId: number | undefined,
  material: Material | Record<string, unknown>,
  quantity: number,
  asOf?: string | dayjs.Dayjs,
): Promise<number> {
  const materialId = Number((material as Material).id ?? (material as Record<string, unknown>).id);
  const qty = Number.isFinite(quantity) && quantity > 0 ? quantity : undefined;
  if (side === 'sales') {
    const { unitPrice } = await resolveOrderLineSalePrice(
      partnerId,
      Number.isFinite(materialId) ? materialId : undefined,
      undefined,
      material,
      asOf,
      qty,
    );
    return unitPrice;
  }
  const { unitPrice } = await resolveOrderLinePurchasePrice(
    partnerId,
    Number.isFinite(materialId) ? materialId : undefined,
    undefined,
    material,
    asOf,
    qty,
  );
  return unitPrice;
}
