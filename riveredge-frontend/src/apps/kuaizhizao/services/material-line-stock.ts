import { apiRequest } from '../../../services/api';

export type MaterialWarehouseStockLine = {
  warehouse_name: string;
  quantity: number;
};

/** 单据明细行总库存（分仓明细，与仓储即时库存同口径） */
export async function getMaterialLineWarehouseStock(
  materialIds: number[],
): Promise<{ by_material: Record<string, MaterialWarehouseStockLine[]> }> {
  if (!materialIds.length) {
    return { by_material: {} };
  }
  return apiRequest('/apps/kuaizhizao/inventory/material-line-warehouse-stock', {
    method: 'GET',
    params: { material_ids: materialIds },
  });
}