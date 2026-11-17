/**
 * 仓储参数：批号/序列号管理总闸（parameters.warehouse.*）
 *
 * 与后端 InventoryService / _validate_batch_serial_policy 一致：
 * 租户关总闸后不强制、制单 UI 不展示录入列。
 * 另：MaterialForm 新建时用同一总闸作为物料 batch_managed / serial_managed 的默认值
 *（开则默认开，免漏点；单物料仍可手改）。
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getBusinessConfig, type BusinessConfig } from '../../../../../services/businessConfig';

export const WAREHOUSE_TRACKING_FLAGS_QUERY_KEY = ['businessConfigWarehouseTrackingFlags'] as const;

export type WarehouseTrackingFlags = {
  batchManagement: boolean;
  serialManagement: boolean;
};

/** 未配置时与后端 DEFAULT_BUSINESS_CONFIG 一致视为开启，避免配置未到时误藏列 */
export function resolveWarehouseTrackingFlags(
  config: BusinessConfig | null | undefined,
): WarehouseTrackingFlags {
  const wh = config?.parameters?.warehouse;
  return {
    batchManagement: wh?.batch_management === undefined ? true : Boolean(wh.batch_management),
    serialManagement: wh?.serial_management === undefined ? true : Boolean(wh.serial_management),
  };
}

export async function fetchWarehouseTrackingFlags(): Promise<WarehouseTrackingFlags> {
  const cfg = await getBusinessConfig();
  return resolveWarehouseTrackingFlags(cfg);
}

export function useWarehouseTrackingFlagsQuery() {
  return useQuery({
    queryKey: WAREHOUSE_TRACKING_FLAGS_QUERY_KEY,
    queryFn: getBusinessConfig,
    staleTime: 5 * 60 * 1000,
  });
}

export function useWarehouseTrackingFlags(): WarehouseTrackingFlags {
  const { data } = useWarehouseTrackingFlagsQuery();
  return useMemo(() => resolveWarehouseTrackingFlags(data), [data]);
}

/** 租户总闸 ∧ 物料标记：是否需要录入批号 */
export function isMaterialBatchEntryEnabled(
  flags: WarehouseTrackingFlags,
  materialBatchManaged?: boolean | null,
): boolean {
  return flags.batchManagement && !!materialBatchManaged;
}

/**
 * 出库确认预览：是否展示批号分摊列。
 * 销售出库在仓库确认前补录批号（与发货通知策略一致）；其余类型仍须物料启用批号管理。
 */
export function isOutboundConfirmBatchLineEnabled(
  outboundType: string | undefined,
  flags: WarehouseTrackingFlags,
  materialBatchManaged?: boolean | null,
): boolean {
  if (!flags.batchManagement) return false;
  if (materialBatchManaged) return true;
  return outboundType === 'sales_delivery';
}

/** 租户总闸 ∧ 物料标记：是否需要录入序列号 */
export function isMaterialSerialEntryEnabled(
  flags: WarehouseTrackingFlags,
  materialSerialManaged?: boolean | null,
): boolean {
  return flags.serialManagement && !!materialSerialManaged;
}

const BATCH_COLUMN_IDS = new Set([
  'batch',
  'batch_no',
  'batch_number',
  'batchNo',
  'batchNumber',
  // 销售出库等制单：分摊列 dataIndex，总闸关闭时须一并隐藏（否则单元格恒为「—」）
  'batch_allocations',
  'batchAllocations',
]);

const SERIAL_COLUMN_IDS = new Set([
  'serial',
  'serial_no',
  'serial_numbers',
  'serialNo',
  'serialNumbers',
]);

function columnIdentity(col: { key?: unknown; dataIndex?: unknown }): string {
  if (col.key != null && String(col.key).trim()) return String(col.key);
  if (Array.isArray(col.dataIndex)) return String(col.dataIndex[0] ?? '');
  if (col.dataIndex != null) return String(col.dataIndex);
  return '';
}

/** 按租户总闸过滤制单/确认表批号、序列号列（列须带 key 或 dataIndex） */
export function filterWarehouseTrackingColumns<T extends { key?: unknown; dataIndex?: unknown }>(
  columns: T[],
  flags: WarehouseTrackingFlags,
): T[] {
  return columns.filter((col) => {
    const id = columnIdentity(col);
    if (!id) return true;
    if (!flags.batchManagement && BATCH_COLUMN_IDS.has(id)) return false;
    if (!flags.serialManagement && SERIAL_COLUMN_IDS.has(id)) return false;
    return true;
  });
}
