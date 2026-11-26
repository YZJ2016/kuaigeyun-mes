import { apiRequest } from '../../../../../services/api';
import { getBusinessConfig } from '../../../../../services/businessConfig';
import { materialSerialApi } from '../../../../master-data/services/material';
import {
  normalizeFifoMode,
  sortBatchesForFifo,
  type WarehouseFifoMode,
} from './outboundFifoSort';

export type InventoryPickOption = {
  value: string;
  label: string;
  primary_quantity?: number;
  quantity?: number;
  warehouseName?: string;
  /** MaterialBatch.id（主仓）；用于 FIFO 建档序 */
  batchId?: number;
  productionDate?: string | null;
  expiryDate?: string | null;
  /** 当前策略下建议优先出库 */
  fifoRecommended?: boolean;
};

/** 与后端库存过账一致：空批号视为 DEFAULT */
export function normalizeOutboundBatchNo(raw: unknown): string {
  const bn = String(raw ?? '').trim();
  return bn || 'DEFAULT';
}

function resolveMainBatchId(row: Record<string, unknown>): number | undefined {
  const rawId = Number(row.id ?? 0);
  // report_service 主仓行：id = 1000000 + MaterialBatch.id；线边 >= 2_000_000
  if (rawId >= 1_000_000 && rawId < 2_000_000) return rawId - 1_000_000;
  const explicit = Number(row.batch_id ?? row.material_batch_id ?? 0);
  return explicit > 0 ? explicit : undefined;
}

function earlierDay(a?: string | null, b?: string | null): string | null | undefined {
  const da = String(a ?? '').trim().slice(0, 10);
  const db = String(b ?? '').trim().slice(0, 10);
  if (!da) return db || a;
  if (!db) return da || b;
  return da <= db ? da : db;
}

/** 确认出库批号：须为在库选项；仅一条时自动选中，禁止无依据默认 DEFAULT */
export function resolveOutboundConfirmBatchValue(
  saved: unknown,
  options: InventoryPickOption[],
): string | undefined {
  if (!options.length) return undefined;
  const raw = String(saved ?? '').trim();
  if (raw) {
    const normalized = normalizeOutboundBatchNo(raw);
    const hit = options.find((o) => o.value === raw || o.value === normalized);
    if (hit) return hit.value;
  }
  if (options.length === 1) return options[0].value;
  return undefined;
}

export function isValidOutboundBatchSelection(
  batch: unknown,
  options: InventoryPickOption[],
): boolean {
  const raw = String(batch ?? '').trim();
  if (!raw || !options.length) return false;
  const normalized = normalizeOutboundBatchNo(raw);
  return options.some((o) => o.value === raw || o.value === normalized);
}

function isOutboundDeductibleInventoryRow(
  row: Record<string, unknown>,
  opts?: { includeLineSide?: boolean },
): boolean {
  const qty = Number(row.primary_quantity ?? row.quantity ?? 0);
  if (!(qty > 0)) return false;
  const status = String(row.status ?? '').trim();
  // 与 InventoryService 默认扣减口径一致：仅自购(company_owned)+在库；客供不计入可出库库存
  const ownership = String(row.ownership_type ?? 'company_owned').trim() || 'company_owned';
  const customerId = Number(row.customer_id ?? 0) || 0;
  if (ownership !== 'company_owned' || customerId !== 0) return false;
  if (status === '已过期' || status === '无库存' || status === 'out_stock' || status === '已出库') {
    return false;
  }
  const rowId = Number(row.id ?? 0);
  // 线边行（id>=2e6）：未指定仓的全仓汇总不计入，避免虚高；
  // 出库单仓库本身是线边仓时，后端只返回该仓 LineSideInventory，必须计入，否则库存数量恒为 0。
  if (rowId >= 2_000_000 && !opts?.includeLineSide) return false;
  return status === 'in_stock' || status === '在库' || status === '';
}

function rowsToBatchOptionMap(
  rows: Record<string, unknown>[],
  labelFn?: (batch: string, qty: number, warehouseName?: string) => string,
  fifoMode: WarehouseFifoMode = 'batch_id',
  opts?: { includeLineSide?: boolean },
): Record<number, InventoryPickOption[]> {
  const map: Record<number, InventoryPickOption[]> = {};
  for (const row of rows) {
    if (!isOutboundDeductibleInventoryRow(row, opts)) continue;
    const mid = row.material_id as number;
    if (!mid) continue;
    const qty = Number(row.primary_quantity ?? row.quantity ?? 0);
    const bn = normalizeOutboundBatchNo(row.batch_no);
    if (!map[mid]) map[mid] = [];
    const existing = map[mid].find((o) => o.value === bn);
    const warehouseName = String(row.warehouse_name ?? '').trim() || undefined;
    const batchId = resolveMainBatchId(row);
    const productionDate = (row.production_date as string | null | undefined) ?? null;
    const expiryDate = (row.expiry_date as string | null | undefined) ?? null;
    if (existing) {
      existing.quantity = (Number(existing.quantity) || 0) + qty;
      existing.label = labelFn
        ? labelFn(bn, existing.quantity, warehouseName ?? existing.warehouseName)
        : `${bn}（${existing.quantity}）`;
      if (batchId != null) {
        existing.batchId =
          existing.batchId == null ? batchId : Math.min(existing.batchId, batchId);
      }
      existing.productionDate = earlierDay(existing.productionDate, productionDate) ?? null;
      existing.expiryDate = earlierDay(existing.expiryDate, expiryDate) ?? null;
      continue;
    }
    map[mid].push({
      value: bn,
      label: labelFn ? labelFn(bn, qty, warehouseName) : `${bn}（${qty}）`,
      quantity: qty,
      warehouseName,
      batchId,
      productionDate,
      expiryDate,
    });
  }
  for (const mid of Object.keys(map)) {
    const sorted = sortBatchesForFifo(map[Number(mid)], fifoMode);
    sorted.forEach((opt, idx) => {
      opt.fifoRecommended = idx === 0;
    });
    map[Number(mid)] = sorted;
  }
  return map;
}

function sumDeductibleQtyByMaterialId(
  rows: Record<string, unknown>[],
  opts?: { includeLineSide?: boolean },
): Record<number, number> {
  const out: Record<number, number> = {};
  for (const row of rows) {
    if (!isOutboundDeductibleInventoryRow(row, opts)) continue;
    const mid = Number(row.material_id);
    if (!Number.isFinite(mid) || mid <= 0) continue;
    out[mid] = (out[mid] ?? 0) + (Number(row.primary_quantity ?? row.quantity) || 0);
  }
  return out;
}

async function fetchBatchQueryRows(
  materialIds: number[],
  warehouseId?: number,
  options?: { companyOwnedOnly?: boolean },
): Promise<Record<string, unknown>[]> {
  const companyOwnedOnly = options?.companyOwnedOnly === true;
  const res = await apiRequest<{ items?: Record<string, unknown>[] }>(
    '/apps/kuaizhizao/reports/inventory/batch-query',
    {
      method: 'GET',
      params: {
        material_ids: materialIds,
        include_expired: false,
        ...(warehouseId != null && warehouseId > 0 ? { warehouse_id: warehouseId } : {}),
        // 与 InventoryService 默认扣减一致：仅自购库存
        ...(companyOwnedOnly
          ? { ownership_type: 'company_owned', customer_id: 0 }
          : {}),
      },
    },
  );
  return res.items ?? [];
}

async function resolveWarehouseFifoMode(): Promise<WarehouseFifoMode> {
  try {
    const cfg = await getBusinessConfig();
    return normalizeFifoMode(cfg?.parameters?.warehouse?.fifo_mode);
  } catch {
    return 'batch_id';
  }
}

/** 租户仓存参数：是否允许负库存出库（与 InventoryService 扣减真源一致） */
export async function resolveAllowNegativeInventory(): Promise<boolean> {
  try {
    const cfg = await getBusinessConfig();
    return Boolean(cfg?.parameters?.warehouse?.allow_negative_inventory);
  } catch {
    return false;
  }
}

export async function loadBatchOptionsByMaterialId(
  materialIds: number[],
  warehouseId?: number,
  labelFn?: (batch: string, qty: number, warehouseName?: string) => string,
): Promise<Record<number, InventoryPickOption[]>> {
  if (!materialIds.length) return {};

  const includeLineSide = warehouseId != null && warehouseId > 0;
  const [rows, fifoMode] = await Promise.all([
    fetchBatchQueryRows(materialIds, warehouseId, { companyOwnedOnly: true }),
    resolveWarehouseFifoMode(),
  ]);
  return rowsToBatchOptionMap(rows, labelFn, fifoMode, { includeLineSide });
}

/** 出库预览：汇总物料在库可用数量（各批号 quantity 之和） */
export function sumInventoryPickOptionQty(options: InventoryPickOption[] | undefined): number {
  if (!options?.length) return 0;
  return options.reduce((sum, o) => sum + (Number(o.quantity) || 0), 0);
}

/**
 * 出库预览库存数量：与确认过账扣减口径一致（自购 company_owned + 在库）。
 * 客供库存不计入，避免出现 101（自购1+客供100）vs 过账可用1 的偏差。
 */
export async function loadAvailableQtyByMaterialId(
  materialIds: number[],
  warehouseId?: number,
): Promise<Record<number, number>> {
  if (!materialIds.length) return {};
  // 指定出库仓时后端已按仓过滤；线边仓场景只返回 LineSideInventory，必须计入。
  const includeLineSide = warehouseId != null && warehouseId > 0;
  const rows = await fetchBatchQueryRows(materialIds, warehouseId, { companyOwnedOnly: true });
  const out = sumDeductibleQtyByMaterialId(rows, { includeLineSide });
  for (const mid of materialIds) {
    if (out[mid] == null) out[mid] = 0;
  }
  return out;
}

/**
 * 按物料 × 仓库汇总可出库库存（自购在库，与 loadAvailableQtyByMaterialId 同口径）。
 * 用于领料/出库选仓下拉展示「仓名（库存 n）」，不改变扣减规则。
 */
export async function loadAvailableQtyByMaterialWarehouse(
  materialIds: number[],
): Promise<Record<number, Record<number, number>>> {
  if (!materialIds.length) return {};
  const rows = await fetchBatchQueryRows(materialIds, undefined, { companyOwnedOnly: true });
  const out: Record<number, Record<number, number>> = {};
  for (const mid of materialIds) {
    out[mid] = {};
  }
  for (const row of rows) {
    // 按仓汇总：线边行带 warehouse_id 时计入对应仓（与确认过账按仓类型扣减一致）
    if (!isOutboundDeductibleInventoryRow(row, { includeLineSide: true })) continue;
    const mid = Number(row.material_id);
    const wid = Number(row.warehouse_id);
    if (!Number.isFinite(mid) || mid <= 0) continue;
    if (!Number.isFinite(wid) || wid <= 0) continue;
    if (!out[mid]) out[mid] = {};
    out[mid][wid] = (out[mid][wid] ?? 0) + (Number(row.primary_quantity ?? row.quantity) || 0);
  }
  return out;
}

export type LocationStockMaps = {
  /** location_id → qty */
  byId: Record<number, number>;
  /** location_code → qty（无 id 或对码回退） */
  byCode: Record<string, number>;
};

/** 主数据「整仓」库位（ensure_whole_warehouse_location 写入的名称/编码后缀） */
export function isWholeWarehouseLocationOption(label: string, code: string): boolean {
  const n = String(label || '').trim();
  const c = String(code || '').trim();
  if (n === '整仓' || c === '整仓') return true;
  if (c.endsWith('-整仓') || n.endsWith('整仓')) return true;
  return false;
}

/**
 * 库位下拉展示用库存：先按 id/编码命中；
 * 无库位维度的在库量（byCode['']）归到「整仓」或仓下唯一库位，避免仓列有库存、整仓却显示无库存。
 */
export function resolveLocationOptionStockQty(
  maps: LocationStockMaps,
  loc: { value: number; code: string; label: string },
  allOptionsCount: number,
): number {
  const qtyFromId = Number(maps.byId[loc.value] ?? 0);
  const code = String(loc.code || '').trim();
  const label = String(loc.label || '').trim();
  const qtyFromCode = Number(maps.byCode[code] ?? 0);
  let qty = qtyFromId > 0 ? qtyFromId : qtyFromCode;
  if (qty > 0) return qty;

  if (isWholeWarehouseLocationOption(label, code)) {
    const byShortName = Number(maps.byCode['整仓'] ?? 0);
    if (byShortName > 0) return byShortName;
  }

  const unlocated = Number(maps.byCode[''] ?? 0);
  if (!(unlocated > 0)) return 0;
  if (isWholeWarehouseLocationOption(label, code) || allOptionsCount === 1) {
    return unlocated;
  }
  return 0;
}

/**
 * 按物料 × 仓库 × 库位汇总可出库库存（自购在库）。
 * 用于库位下拉展示「库位（库存 n）」；无库位维度的行计入空码键 ''。
 */
export async function loadAvailableQtyByMaterialLocation(
  materialId: number,
  warehouseId: number,
): Promise<LocationStockMaps> {
  const mid = Number(materialId);
  const wid = Number(warehouseId);
  const empty: LocationStockMaps = { byId: {}, byCode: {} };
  if (!(mid > 0) || !(wid > 0)) return empty;

  const rows = await fetchBatchQueryRows([mid], wid, { companyOwnedOnly: true });
  const byId: Record<number, number> = {};
  const byCode: Record<string, number> = {};
  for (const row of rows) {
    if (!isOutboundDeductibleInventoryRow(row, { includeLineSide: true })) continue;
    if (Number(row.material_id) !== mid) continue;
    const rowWh = Number(row.warehouse_id);
    if (Number.isFinite(rowWh) && rowWh > 0 && rowWh !== wid) continue;
    const qty = Number(row.primary_quantity ?? row.quantity) || 0;
    if (!(qty > 0)) continue;
    const lid = Number(row.location_id ?? 0);
    const code = String(row.location_code ?? '').trim();
    if (lid > 0) {
      byId[lid] = (byId[lid] ?? 0) + qty;
    }
    if (code) {
      byCode[code] = (byCode[code] ?? 0) + qty;
    } else if (!(lid > 0)) {
      byCode[''] = (byCode[''] ?? 0) + qty;
    }
  }
  return { byId, byCode };
}

/** 拉取物料全部在库序列号（分页合并，供出库确认多选） */
export async function loadInStockSerialOptions(materialUuid: string): Promise<InventoryPickOption[]> {
  const pageSize = 100;
  let page = 1;
  const serialNos: string[] = [];
  let total = 0;

  while (true) {
    const res = await materialSerialApi.list({
      materialUuid,
      status: 'in_stock',
      page,
      pageSize,
      sortBy: 'serial_no',
      sortOrder: 'asc',
    });
    total = res.total ?? 0;
    const items = res.items ?? [];
    for (const it of items) {
      const sn = String(it.serialNo ?? (it as { serial_no?: string }).serial_no ?? '').trim();
      if (sn && !serialNos.includes(sn)) serialNos.push(sn);
    }
    if (items.length < pageSize || serialNos.length >= total) break;
    page += 1;
  }

  return serialNos.map((sn) => ({ value: sn, label: sn }));
}

/** 仅保留仍在库的已选序列号（编辑回填时剔除已出库项） */
export function intersectSerialNumbersWithInStock(
  selected: string[] | undefined,
  inStock: InventoryPickOption[],
): string[] {
  const allowed = new Set(inStock.map((o) => o.value));
  return (selected ?? [])
    .map((s) => String(s ?? '').trim())
    .filter((s) => s && allowed.has(s));
}
