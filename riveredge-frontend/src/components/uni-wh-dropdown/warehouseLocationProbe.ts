import { fetchStorageLocationsForWarehouse } from '../../apps/kuaizhizao/pages/warehouse-management/inbound/inboundPoReceiptEntryUtils';

const warehouseHasLocationsCache: Record<number, boolean> = {};

export function readWarehouseHasLocationsCache(warehouseId: number): boolean | undefined {
  const wid = Number(warehouseId);
  if (!Number.isFinite(wid) || wid <= 0) return undefined;
  return warehouseHasLocationsCache[wid];
}

/** 仓下是否存在可选库位；无库位时 false（整仓由后端 ensure）。 */
export async function probeWarehouseHasLocations(warehouseId: number): Promise<boolean> {
  const wid = Number(warehouseId);
  if (!Number.isFinite(wid) || wid <= 0) return true;
  const cached = warehouseHasLocationsCache[wid];
  if (cached !== undefined) return cached;
  const opts = await fetchStorageLocationsForWarehouse(wid);
  const hasLoc = opts.length > 0;
  warehouseHasLocationsCache[wid] = hasLoc;
  return hasLoc;
}

export function invalidateWarehouseHasLocationsCache(warehouseId?: number): void {
  if (warehouseId == null) {
    for (const key of Object.keys(warehouseHasLocationsCache)) {
      delete warehouseHasLocationsCache[Number(key)];
    }
    return;
  }
  const wid = Number(warehouseId);
  if (Number.isFinite(wid) && wid > 0) {
    delete warehouseHasLocationsCache[wid];
  }
}

/** 有库位仓须已选库位；无库位仓返回 false（不必选手选）。 */
export async function lineLocationSelectionRequired(
  warehouseId: number,
  locationId?: number | null,
  locationCode?: string | null,
): Promise<boolean> {
  const wh = Number(warehouseId);
  if (!(wh > 0)) return true;
  const hasLoc = await probeWarehouseHasLocations(wh);
  if (!hasLoc) return false;
  const lid = Number(locationId);
  if (Number.isFinite(lid) && lid > 0) return false;
  return !String(locationCode || '').trim();
}
