import type { TFunction } from 'i18next';
import {
  lineLocationSelectionRequired,
  resolveFirstStorageLocationForWarehouse,
} from '../../../../../components/uni-wh-dropdown';
import {
  buildOutboundConfirmPayloadFromForm,
  type OutboundConfirmationPayload,
} from '../outbound/outboundItemTracking';
import type { OutboundIssueType } from '../outbound/outboundHubTypes';
import {
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  type WarehouseTrackingFlags,
} from './warehouseTrackingFlags';
import type { ConfirmPreviewMaterialMeta } from '../inbound/inboundItemTracking';
import {
  isValidOutboundBatchAllocations,
  pickAndAllocateBatchesFifo,
  type OutboundBatchAllocation,
} from '../outbound/outboundBatchAllocation';
import type { InventoryPickOption } from '../outbound/outboundConfirmInventoryOptions';

export function resolveOutboundConfirmLineQuantity(
  outboundType: OutboundIssueType,
  it: Record<string, unknown>,
): number {
  if (outboundType === 'purchase_return') {
    return Number(it.return_quantity ?? 0);
  }
  return Number(
    it.delivery_quantity ?? it.picked_quantity ?? it.outbound_quantity ?? it.borrow_quantity ?? 0,
  );
}

export function enrichOutboundDetailLinesWithHeaderWarehouse(
  detail: Record<string, unknown>,
): Record<string, unknown>[] {
  const headerWhId = Number(detail.warehouse_id ?? 0);
  const headerWhName = String(detail.warehouse_name ?? '');
  const lines = (Array.isArray(detail.items) ? detail.items : []) as Record<string, unknown>[];
  return lines.map((it) => ({
    ...it,
    warehouse_id: Number(it.warehouse_id ?? headerWhId),
    warehouse_name: String(it.warehouse_name ?? headerWhName),
  }));
}

/** 出库 Hub 列表确认：未存库位时按仓默认首库位，与后端 `_require_line_location` 对齐。 */
export async function hydrateOutboundDetailLinesDefaultLocation(
  lines: Record<string, unknown>[],
): Promise<Record<string, unknown>[]> {
  const resolvedByWarehouse = new Map<number, { id: number; code: string } | null>();
  const out: Record<string, unknown>[] = [];
  for (const it of lines) {
    const whId = Number(it.warehouse_id ?? 0);
    const needLoc = await lineLocationSelectionRequired(whId, it.location_id, it.location_code);
    if (!needLoc) {
      out.push(it);
      continue;
    }
    if (!resolvedByWarehouse.has(whId)) {
      resolvedByWarehouse.set(whId, await resolveFirstStorageLocationForWarehouse(whId));
    }
    const resolved = resolvedByWarehouse.get(whId);
    if (!resolved) {
      out.push(it);
      continue;
    }
    out.push({
      ...it,
      location_id: resolved.id,
      location_code: resolved.code,
    });
  }
  return out;
}

function normalizeLineBatchAllocations(raw: unknown): OutboundBatchAllocation[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((a) => {
      const row = a as { batchNo?: string; batch_number?: string; quantity?: number };
      return {
        batchNo: String(row.batchNo ?? row.batch_number ?? '').trim(),
        quantity: Number(row.quantity ?? 0),
      };
    })
    .filter((a) => a.batchNo && a.quantity > 0);
}

export function formValuesFromOutboundDetailLines(lines: Record<string, unknown>[]): Record<string, unknown> {
  const vals: Record<string, unknown> = {};
  for (const it of lines) {
    const lineId = Number(it.id);
    if (!Number.isFinite(lineId) || lineId <= 0) continue;
    const whId = Number(it.warehouse_id);
    if (Number.isFinite(whId) && whId > 0) {
      vals[`warehouse_${lineId}`] = whId;
    }
    const whName = String(it.warehouse_name ?? '').trim();
    if (whName) vals[`warehouse_name_${lineId}`] = whName;
    const locId = it.location_id;
    if (locId != null && locId !== '') vals[`location_${lineId}`] = locId;
    const locCode = String(it.location_code ?? '').trim();
    if (locCode) vals[`location_code_${lineId}`] = locCode;
    const batch = String(it.batch_number ?? '').trim();
    if (batch) vals[`batch_${lineId}`] = batch;
    const allocs = normalizeLineBatchAllocations(it.batch_allocations);
    if (allocs.length) {
      vals[`batch_alloc_${lineId}`] = allocs;
    }
    if (Array.isArray(it.serial_numbers)) {
      vals[`serial_${lineId}`] = it.serial_numbers;
    }
  }
  return vals;
}

/**
 * 确认出库前：批号管理行若未存批号，按在库可选批 FIFO 分摊写入本次确认载荷。
 * 与编辑态「按可用量分摊」同一真源；解决已审核不可编辑时无法补选批号的死锁。
 */
export function hydrateOutboundDetailLinesDefaultBatch(options: {
  outboundType: OutboundIssueType;
  lines: Record<string, unknown>[];
  materialMeta: Record<number, ConfirmPreviewMaterialMeta>;
  trackingFlags: WarehouseTrackingFlags;
  batchOptionsByKey: Record<string, InventoryPickOption[]>;
  lineBatchKey: (materialId: number, warehouseId: number) => string;
  headerWarehouseId?: number;
}): Record<string, unknown>[] {
  const {
    outboundType,
    lines,
    materialMeta,
    trackingFlags,
    batchOptionsByKey,
    lineBatchKey,
    headerWarehouseId,
  } = options;
  return lines.map((it) => {
    const mid = Number(it.material_id);
    const rowId = Number(it.id);
    const meta = materialMeta[rowId] ?? materialMeta[mid];
    if (!isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) return it;
    const qty = resolveOutboundConfirmLineQuantity(outboundType, it);
    if (!(qty > 0)) return it;
    const whId = Number(it.warehouse_id ?? headerWarehouseId ?? 0);
    if (!(whId > 0)) return it;
    const opts = batchOptionsByKey[lineBatchKey(mid, whId)] ?? [];
    if (!opts.length) return it;

    const existing = normalizeLineBatchAllocations(it.batch_allocations);
    if (existing.length && isValidOutboundBatchAllocations(existing, opts, qty)) {
      return it;
    }
    const batchStr = String(it.batch_number ?? '').trim();
    if (batchStr && !existing.length) {
      // 单批已落库：补成 allocations，便于确认 payload 统一走分摊字段
      const single = [{ batchNo: batchStr, quantity: qty }];
      if (isValidOutboundBatchAllocations(single, opts, qty)) {
        return { ...it, batch_allocations: single };
      }
      return it;
    }
    if (batchStr) return it;

    let allocs = pickAndAllocateBatchesFifo(qty, opts);
    if (
      isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged) &&
      allocs.length > 1
    ) {
      const one = opts.find((o) => Number(o.quantity) >= qty);
      if (!one) return it;
      allocs = [{ batchNo: String(one.value).trim(), quantity: qty }];
    }
    if (!isValidOutboundBatchAllocations(allocs, opts, qty)) return it;
    return {
      ...it,
      batch_allocations: allocs,
      batch_number: allocs[0]?.batchNo,
    };
  });
}

export function buildOutboundConfirmPayloadFromDetail(
  outboundType: OutboundIssueType,
  detail: Record<string, unknown>,
  header?: {
    delivery_time?: string;
    deliverer_id?: number;
    deliverer_name?: string;
    picker_id?: number;
    picker_name?: string;
  },
): OutboundConfirmationPayload {
  const lines = enrichOutboundDetailLinesWithHeaderWarehouse(detail);
  const whId = Number(detail.warehouse_id ?? 0);
  const whName = String(detail.warehouse_name ?? '').trim();
  const formValues = formValuesFromOutboundDetailLines(lines);
  return buildOutboundConfirmPayloadFromForm(
    outboundType,
    lines,
    formValues,
    whId > 0 ? whId : undefined,
    whName || undefined,
    header,
  );
}

export async function validateOutboundDetailBeforeConfirm(
  t: TFunction,
  outboundType: OutboundIssueType,
  lines: Record<string, unknown>[],
  materialMeta: Record<number, ConfirmPreviewMaterialMeta>,
  trackingFlags: WarehouseTrackingFlags,
  batchOptionsByKey: Record<string, InventoryPickOption[]>,
  lineBatchKey: (materialId: number, warehouseId: number) => string,
  headerWarehouseId?: number,
): Promise<void> {
  if (outboundType === 'purchase_return') {
    const headerWh = Number(headerWarehouseId ?? 0);
    if (!(headerWh > 0)) {
      throw new Error(t('app.kuaizhizao.purchaseReturn.pull.selectWarehouse'));
    }
  }
  for (const it of lines) {
    const mid = Number(it.material_id);
    const rowId = Number(it.id);
    const meta = materialMeta[rowId] ?? materialMeta[mid];
    const qty = resolveOutboundConfirmLineQuantity(outboundType, it);
    if (!(qty > 0)) continue;
    const whId = Number(it.warehouse_id ?? headerWarehouseId ?? 0);
    if (!(whId > 0)) {
      throw new Error(
        t('app.kuaizhizao.warehouseOutbound.msg.selectLineWarehouse', {
          material: String(it.material_code ?? it.material_name ?? mid),
        }),
      );
    }
    const needLoc = await lineLocationSelectionRequired(whId, it.location_id, it.location_code);
    if (needLoc) {
      throw new Error(
        t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', {
          material: String(it.material_code ?? it.material_name ?? mid),
        }),
      );
    }
    if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
      const key = lineBatchKey(mid, whId);
      const opts = batchOptionsByKey[key] ?? [];
      const normalized = normalizeLineBatchAllocations(it.batch_allocations);
      const batchStr = String(it.batch_number ?? '').trim();
      if (normalized.length) {
        if (!isValidOutboundBatchAllocations(normalized, opts, qty)) {
          throw new Error(
            t('app.kuaizhizao.warehouseOutbound.confirm.batchAllocationRequired', {
              material: String(it.material_code ?? it.material_name ?? ''),
              qty,
              batches: opts.map((o) => o.value).join('、') || '—',
            }),
          );
        }
      } else if (!batchStr) {
        throw new Error(
          t('app.kuaizhizao.warehouseOutbound.confirm.batchAllocationRequired', {
            material: String(it.material_code ?? it.material_name ?? ''),
            qty,
            batches: opts.map((o) => o.value).join('、') || '—',
          }),
        );
      }
    }
    if (isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) {
      const serials = Array.isArray(it.serial_numbers) ? it.serial_numbers : [];
      const expected = Math.floor(qty);
      if (serials.length !== expected) {
        throw new Error(
          t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
            material: String(it.material_code ?? it.material_name ?? ''),
            required: expected,
            actual: serials.length,
          }),
        );
      }
    }
  }
}
