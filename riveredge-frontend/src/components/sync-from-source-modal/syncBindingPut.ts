/**
 * 按 SyncFromSourceConfig.historySourceType 保存入站同步绑定（含 sources: [] 清空）。
 * 后端 upsert 在 sources=[] 时清除绑定，便于接口管理硬删前解绑。
 */
import { apiRequest } from '../../services/api';
import type { SyncSourceItem } from './types';

export type SyncBindingPutPayload = {
  sources: SyncSourceItem[];
  match_key_field?: string;
  sync_mode?: string;
  schedule_interval_minutes?: number;
  schedule_window_start?: string | null;
  schedule_window_end?: string | null;
};

/** historySourceType → PUT sync-binding 路径（与各 getBinding 一致） */
const SYNC_BINDING_PUT_PATH: Record<string, string> = {
  customer: '/apps/master-data/supply-chain/customers/sync-binding',
  supplier: '/apps/master-data/supply-chain/suppliers/sync-binding',
  warehouse: '/apps/master-data/warehouse/warehouses/sync-binding',
  storage_location: '/apps/master-data/warehouse/storage-locations/sync-binding',
  warehouse_location_ref: '/apps/master-data/warehouse/warehouses/location-ref/sync-binding',
  unit: '/apps/master-data/materials/units/sync-binding',
  material: '/apps/master-data/materials/sync-binding',
  material_multi_unit: '/apps/master-data/materials/multi-unit/sync-binding',
  material_batch_manage: '/apps/master-data/materials/batch-manage/sync-binding',
  material_group: '/apps/master-data/materials/groups/sync-binding',
  engineering_bom: '/apps/master-data/materials/bom/sync-binding',
  process_operation: '/apps/master-data/process/operations/sync-binding',
  sales_order: '/apps/kuaizhizao/sales-orders/sync-binding',
  purchase_order: '/apps/kuaizhizao/purchase-orders/sync-binding',
  work_order: '/apps/kuaizhizao/work-orders/sync-binding',
  reporting_record: '/apps/kuaizhizao/reporting/sync-binding',
  material_batch: '/apps/kuaizhizao/reports/inventory/sync-binding',
};

export function resolveSyncBindingPutPath(historySourceType: string): string | null {
  const key = String(historySourceType || '').trim();
  return SYNC_BINDING_PUT_PATH[key] || null;
}

export async function putSyncBindingByHistorySourceType(
  historySourceType: string,
  payload: SyncBindingPutPayload,
): Promise<void> {
  const path = resolveSyncBindingPutPath(historySourceType);
  if (!path) {
    throw new Error(`未配置同步绑定保存路径：${historySourceType}`);
  }
  await apiRequest(path, {
    method: 'PUT',
    data: payload,
  });
}
