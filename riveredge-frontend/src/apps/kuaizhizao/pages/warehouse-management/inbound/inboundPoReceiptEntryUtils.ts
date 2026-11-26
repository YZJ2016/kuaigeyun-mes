import type { Material } from '../../../../master-data/types/material';
import { resolvePrimaryDefaultWarehouseFromMaterial } from '../../../../master-data/utils/materialDefaultWarehouse';
import {
  storageAreaApi,
  storageLocationApi,
} from '../../../../master-data/services/warehouse';
import type { PurchaseOrder, PurchaseOrderItem } from '../../../services/purchase';

export function formatStorageAreaOrLocationLabel(code?: string, name?: string): string {
  const c = (code || '').trim();
  const n = (name || '').trim();
  if (c && n && c === n) return c;
  return [c, n].filter(Boolean).join(' ').trim();
}

/** 库位/库区下拉展示：仅名称，无名称时再回退编码（不拼接编号+名称） */
export function storageLocationDisplayName(name?: string, code?: string): string {
  const n = (name || '').trim();
  if (n) return n;
  return (code || '').trim();
}

type StorageLocationListItem = {
  id: number;
  code?: string;
  name?: string;
  storageAreaId?: number | string | null;
  storage_area_id?: number | string | null;
  storageAreaCode?: string;
  storage_area_code?: string;
  storageAreaName?: string;
  storage_area_name?: string;
};

function storageLocationAreaId(loc: StorageLocationListItem): number | null {
  const raw = loc.storageAreaId ?? loc.storage_area_id;
  if (raw == null || raw === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

type WarehouseLocationOption = { value: number; label: string; code: string };

/** 同一仓库的库位下拉只打一次本地列表，不在打开下拉时重复请求。 */
const storageLocationOptionsCache = new Map<number, Promise<WarehouseLocationOption[]>>();

export function invalidateStorageLocationOptionsCache(warehouseId?: number): void {
  if (warehouseId == null) {
    storageLocationOptionsCache.clear();
    return;
  }
  const wid = Number(warehouseId);
  if (Number.isFinite(wid) && wid > 0) {
    storageLocationOptionsCache.delete(wid);
  }
}

/**
 * 某仓库可选库位：只查本仓（直挂 + 本仓库区下），读本地主数据，不同步金蝶。
 */
export async function fetchStorageLocationsForWarehouse(
  warehouseId: number,
): Promise<WarehouseLocationOption[]> {
  const wid = Number(warehouseId);
  if (!Number.isFinite(wid) || wid <= 0) return [];
  const cached = storageLocationOptionsCache.get(wid);
  if (cached) return cached;
  const pending = loadStorageLocationsForWarehouse(wid).catch((err) => {
    storageLocationOptionsCache.delete(wid);
    throw err;
  });
  storageLocationOptionsCache.set(wid, pending);
  return pending;
}

async function loadStorageLocationsForWarehouse(
  wid: number,
): Promise<WarehouseLocationOption[]> {
  const [saRes, locRes] = await Promise.all([
    storageAreaApi.list({
      warehouse_id: wid,
      limit: 500,
      is_active: true,
    } as Parameters<typeof storageAreaApi.list>[0]),
    storageLocationApi.list({
      warehouse_id: wid,
      limit: 1000,
      is_active: true,
    } as Parameters<typeof storageLocationApi.list>[0]),
  ]);

  // 兼容 { items } / { data: { items } } / 偶发数组本体
  const unwrapItems = <T,>(raw: unknown): T[] => {
    if (Array.isArray(raw)) return raw as T[];
    if (!raw || typeof raw !== 'object') return [];
    const row = raw as { items?: T[]; data?: T[] | { items?: T[] } };
    if (Array.isArray(row.items)) return row.items;
    if (Array.isArray(row.data)) return row.data;
    if (row.data && typeof row.data === 'object' && Array.isArray((row.data as { items?: T[] }).items)) {
      return (row.data as { items: T[] }).items;
    }
    return [];
  };

  const areas = unwrapItems<{ id: number; code?: string; name?: string }>(saRes);
  const areaById = new Map(
    areas.map((a) => [
      a.id,
      storageLocationDisplayName(a.name, a.code) || `库区${a.id}`,
    ]),
  );
  const allowedAreaIds = new Set(areaById.keys());

  const locs = unwrapItems<StorageLocationListItem>(locRes);

  return locs
    .filter((l) => {
      const areaId = storageLocationAreaId(l);
      const locWh = Number(
        (l as { warehouseId?: number; warehouse_id?: number }).warehouseId ??
          (l as { warehouse_id?: number }).warehouse_id ??
          0,
      );
      if (areaId != null) return allowedAreaIds.has(areaId);
      if (Number.isFinite(locWh) && locWh > 0) return locWh === wid;
      return true;
    })
    .map((l) => {
      const areaId = storageLocationAreaId(l);
      const areaLabel =
        (areaId != null ? areaById.get(areaId) : undefined) ||
        storageLocationDisplayName(
          l.storageAreaName ?? l.storage_area_name,
          l.storageAreaCode ?? l.storage_area_code,
        );
      const locLabel = storageLocationDisplayName(l.name, l.code) || String(l.id);
      return {
        value: l.id,
        label: areaLabel ? `${areaLabel} - ${locLabel}` : locLabel,
        code: String(l.code || ''),
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function normalizePurchaseOrderItem(raw: Record<string, unknown>): PurchaseOrderItem {
  const auxQtyRaw = raw.aux_quantity ?? raw.auxQuantity;
  const auxQty = auxQtyRaw != null && auxQtyRaw !== '' ? Number(auxQtyRaw) : undefined;
  const rateRaw = raw.unit_conversion_rate ?? raw.unitConversionRate;
  const rate = rateRaw != null && rateRaw !== '' ? Number(rateRaw) : undefined;
  const auxUnitRaw = raw.aux_unit ?? raw.auxUnit;
  return {
    ...(raw as PurchaseOrderItem),
    id: Number(raw.id) || undefined,
    material_id: Number(raw.material_id ?? raw.materialId) || undefined,
    material_code: String(raw.material_code ?? raw.materialCode ?? '').trim(),
    material_name: String(raw.material_name ?? raw.materialName ?? '').trim(),
    material_spec: String(raw.material_spec ?? raw.materialSpec ?? '').trim() || undefined,
    material_model: String(raw.material_model ?? raw.materialModel ?? '').trim() || undefined,
    ordered_quantity: Number(raw.ordered_quantity ?? raw.orderedQuantity ?? 0),
    received_quantity: Number(raw.received_quantity ?? raw.receivedQuantity ?? 0),
    outstanding_quantity: Number(raw.outstanding_quantity ?? raw.outstandingQuantity ?? 0),
    max_receivable_quantity: Number(
      raw.max_receivable_quantity ?? raw.maxReceivableQuantity ?? NaN,
    ),
    over_receipt_tolerance_pct: Number(
      raw.over_receipt_tolerance_pct ?? raw.overReceiptTolerancePct ?? NaN,
    ),
    unit: String(raw.unit ?? raw.material_unit ?? raw.materialUnit ?? '').trim() || undefined,
    aux_quantity: Number.isFinite(auxQty as number) ? (auxQty as number) : undefined,
    aux_unit: auxUnitRaw != null && String(auxUnitRaw).trim() ? String(auxUnitRaw).trim() : undefined,
    unit_conversion_rate: Number.isFinite(rate as number) && (rate as number) > 0 ? rate : undefined,
  };
}

export function getPoItemReceivableMax(it: PurchaseOrderItem): number {
  const toleranced = Number(it.max_receivable_quantity);
  if (Number.isFinite(toleranced) && toleranced >= 0) {
    return toleranced;
  }
  return Number(it.outstanding_quantity ?? 0);
}

export function normalizePurchaseOrderDetail(detail: PurchaseOrder): PurchaseOrder {
  const raw = detail as PurchaseOrder & Record<string, unknown>;
  return {
    ...detail,
    order_code: String(detail.order_code ?? raw.orderCode ?? ''),
    supplier_name: String(detail.supplier_name ?? raw.supplierName ?? ''),
    buyer_name: String(detail.buyer_name ?? raw.buyerName ?? ''),
    supplier_contact: String(detail.supplier_contact ?? raw.supplierContact ?? ''),
    supplier_phone: String(detail.supplier_phone ?? raw.supplierPhone ?? ''),
    currency: String(detail.currency ?? raw.currency ?? ''),
    order_date: detail.order_date ?? (raw.orderDate as string | undefined),
    delivery_date: detail.delivery_date ?? (raw.deliveryDate as string | undefined),
    items: (detail.items || []).map((it) =>
      normalizePurchaseOrderItem(it as unknown as Record<string, unknown>),
    ),
  };
}

export function resolveDocumentLineMaterialSpec(
  line: Record<string, unknown>,
  material?: Material,
): string | undefined {
  const fromLine = String(line.material_spec ?? line.materialSpec ?? '').trim();
  if (fromLine) return fromLine;
  const fromMat = String(material?.specification ?? '').trim();
  return fromMat || undefined;
}

export function resolveDocumentLineMaterialModel(
  line: Record<string, unknown>,
  material?: Material,
): string | undefined {
  const fromLine = String(line.material_model ?? line.materialModel ?? '').trim();
  if (fromLine) return fromLine;
  const fromMat = String(material?.model ?? '').trim();
  return fromMat || undefined;
}

export function enrichPurchaseOrderItemsMaterial(
  items: PurchaseOrderItem[],
  materialById: Map<string, Material>,
): PurchaseOrderItem[] {
  return items.map((it) => {
    const m = it.material_id ? materialById.get(String(it.material_id)) : undefined;
    const lineRec = it as unknown as Record<string, unknown>;
    return {
      ...it,
      material_code: it.material_code || m?.mainCode || m?.code || '',
      material_name: it.material_name || m?.name || '',
      unit: it.unit || m?.baseUnit || it.unit,
      material_spec:
        it.material_spec != null && String(it.material_spec).trim()
          ? it.material_spec
          : resolveDocumentLineMaterialSpec(lineRec, m),
      material_model: resolveDocumentLineMaterialModel(lineRec, m),
    };
  });
}

export function getOutstandingPoItems(order: PurchaseOrder | null): PurchaseOrderItem[] {
  return (order?.items || []).filter((it) => getPoItemReceivableMax(it) > 0);
}

/** 采购入库行：显式行仓 → 订单行仓 → 物料默认仓 → 订单头仓 */
export function resolvePurchaseReceiptLineWarehouse(
  poItem: PurchaseOrderItem,
  material: Material | undefined,
  options?: {
    explicitWarehouseId?: number | null;
    headerWarehouseId?: number | null;
  },
): { warehouse_id?: number; warehouse_name?: string } {
  const explicit = Number(options?.explicitWarehouseId ?? 0);
  if (explicit > 0) {
    return {
      warehouse_id: explicit,
      warehouse_name: String(poItem.warehouse_name ?? '').trim() || undefined,
    };
  }
  const poLineWh = Number(
    (poItem as { warehouse_id?: number; warehouseId?: number }).warehouse_id ??
      (poItem as { warehouseId?: number }).warehouseId ??
      0,
  );
  if (poLineWh > 0) {
    return {
      warehouse_id: poLineWh,
      warehouse_name: String(poItem.warehouse_name ?? '').trim() || undefined,
    };
  }
  const fromMaterial = resolvePrimaryDefaultWarehouseFromMaterial(material);
  if (fromMaterial) {
    return { warehouse_id: fromMaterial.id, warehouse_name: fromMaterial.name || undefined };
  }
  const headerWh = Number(options?.headerWarehouseId ?? 0);
  if (headerWh > 0) {
    return { warehouse_id: headerWh };
  }
  return {};
}
