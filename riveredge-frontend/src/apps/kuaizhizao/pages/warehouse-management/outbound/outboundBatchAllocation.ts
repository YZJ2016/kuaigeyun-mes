/**
 * 出库/领料批号分摊：一行物料可对应多批号，每批独立数量；
 * 提交时拆成多条明细（与库存「一批一扣」一致）。
 */

import type { InventoryPickOption } from './outboundConfirmInventoryOptions';
import { normalizeOutboundBatchNo } from './outboundConfirmInventoryOptions';

export type OutboundBatchAllocation = {
  batchNo: string;
  quantity: number;
};

const QTY_EPS = 1e-6;

export function sumBatchAllocationQty(allocs: OutboundBatchAllocation[] | undefined): number {
  if (!allocs?.length) return 0;
  return allocs.reduce((sum, a) => sum + (Number(a.quantity) || 0), 0);
}

/** 在已选批号间按可用量 FIFO 分摊 totalQty；尽量保留 previous 中仍有效的数量 */
export function allocateBatchQuantitiesFifo(
  totalQty: number,
  selectedBatchNos: string[],
  options: InventoryPickOption[],
  previous?: OutboundBatchAllocation[],
): OutboundBatchAllocation[] {
  const order = new Map(options.map((o, i) => [String(o.value ?? '').trim(), i] as const));
  const nos = selectedBatchNos
    .map((b) => String(b ?? '').trim())
    .filter(Boolean)
    .sort((a, b) => (order.get(a) ?? 9999) - (order.get(b) ?? 9999));
  if (!nos.length) return [];

  const avail = new Map<string, number>();
  for (const o of options) {
    const key = String(o.value ?? '').trim();
    if (!key) continue;
    avail.set(key, Number(o.quantity) || 0);
  }

  const prevMap = new Map<string, number>();
  for (const a of previous ?? []) {
    const key = String(a.batchNo ?? '').trim();
    if (!key) continue;
    prevMap.set(key, Number(a.quantity) || 0);
  }

  const target = Number.isFinite(totalQty) && totalQty > 0 ? totalQty : 0;
  let remaining = target;
  const result: OutboundBatchAllocation[] = nos.map((batchNo) => {
    const max = Math.max(0, avail.get(batchNo) ?? 0);
    const preferred = prevMap.get(batchNo);
    let qty = 0;
    if (preferred != null && preferred > QTY_EPS && remaining > QTY_EPS) {
      qty = Math.min(preferred, max, remaining);
      remaining -= qty;
    }
    return { batchNo, quantity: qty };
  });

  for (const row of result) {
    if (remaining <= QTY_EPS) break;
    const max = Math.max(0, avail.get(row.batchNo) ?? 0);
    const room = Math.max(0, max - row.quantity);
    if (room <= QTY_EPS) continue;
    const add = Math.min(room, remaining);
    row.quantity += add;
    remaining -= add;
  }

  return result;
}

/**
 * 按选项序（FIFO）自动勾选足够批号，并按可用量分摊 totalQty。
 * 「按可用量分摊」按钮真源：不依赖用户先勾选。
 */
export function pickAndAllocateBatchesFifo(
  totalQty: number,
  options: InventoryPickOption[],
): OutboundBatchAllocation[] {
  const target = Number.isFinite(totalQty) && totalQty > 0 ? totalQty : 0;
  if (!(target > QTY_EPS) || !options.length) return [];

  const nos: string[] = [];
  let remaining = target;
  for (const o of options) {
    const bn = String(o.value ?? '').trim();
    if (!bn) continue;
    const avail = Number(o.quantity) || 0;
    if (!(avail > QTY_EPS)) continue;
    nos.push(bn);
    remaining -= Math.min(avail, remaining);
    if (remaining <= QTY_EPS) break;
  }
  if (!nos.length) return [];
  return allocateBatchQuantitiesFifo(target, nos, options, []);
}

export function isValidOutboundBatchAllocations(
  allocs: OutboundBatchAllocation[] | undefined,
  options: InventoryPickOption[],
  totalQty: number,
): boolean {
  if (!options.length) return false;
  const list = (allocs ?? []).filter((a) => String(a.batchNo ?? '').trim() && Number(a.quantity) > QTY_EPS);
  if (!list.length) return false;
  const target = Number(totalQty) || 0;
  if (!(target > QTY_EPS)) return false;
  const sum = sumBatchAllocationQty(list);
  if (Math.abs(sum - target) > Math.max(QTY_EPS, target * 1e-9)) return false;

  const avail = new Map(
    options.map((o) => [String(o.value ?? '').trim(), Number(o.quantity) || 0] as const),
  );
  for (const a of list) {
    const batchNo = String(a.batchNo).trim();
    const normalized = normalizeOutboundBatchNo(batchNo);
    const max =
      avail.get(batchNo) ??
      avail.get(normalized) ??
      0;
    if (!(max > QTY_EPS) || a.quantity > max + QTY_EPS) return false;
  }
  return true;
}

/** 草稿兼容：旧版单批号 string → 分摊结构 */
export function coerceBatchAllocationsDraft(
  raw: unknown,
  issueQuantity: number,
): OutboundBatchAllocation[] | undefined {
  if (raw == null) return undefined;
  if (Array.isArray(raw)) {
    const list = raw
      .map((item) => {
        if (!item || typeof item !== 'object') return null;
        const rec = item as Record<string, unknown>;
        const batchNo = String(rec.batchNo ?? rec.batch_number ?? rec.batch_no ?? '').trim();
        const quantity = Number(rec.quantity ?? 0);
        if (!batchNo) return null;
        return { batchNo, quantity: Number.isFinite(quantity) ? quantity : 0 };
      })
      .filter((x): x is OutboundBatchAllocation => x != null);
    return list.length ? list : undefined;
  }
  if (typeof raw === 'string') {
    const batchNo = raw.trim();
    if (!batchNo) return undefined;
    const qty = Number(issueQuantity) || 0;
    return [{ batchNo, quantity: qty > 0 ? qty : 0 }];
  }
  return undefined;
}

/** 行上 batch_allocations / batch_number → 有效分摊列表 */
export function lineBatchAllocationsFromRow(
  row: Record<string, unknown> | null | undefined,
  qty: number,
): OutboundBatchAllocation[] {
  if (!row) return [];
  return (
    coerceBatchAllocationsDraft(row.batch_allocations, qty) ??
    coerceBatchAllocationsDraft(row.batch_number, qty) ??
    []
  ).filter((a) => String(a.batchNo).trim() && Number(a.quantity) > QTY_EPS);
}

/** 同步表单行：分摊数组 + 单批时写回 batch_number */
export function syncFormLineBatchFields(
  setFieldValue: (name: (string | number)[], value: unknown) => void,
  index: number,
  allocs: OutboundBatchAllocation[],
  listName = 'items',
) {
  setFieldValue([listName, index, 'batch_allocations'], allocs);
  setFieldValue(
    [listName, index, 'batch_number'],
    allocs.length === 1 ? allocs[0].batchNo : undefined,
  );
}

/** 提交 API：分摊 → batch_allocations + 单批 batch_number */
export function batchAllocationsToApiPayload(allocs: OutboundBatchAllocation[]): {
  batch_number?: string;
  batch_allocations?: { batch_number: string; quantity: number }[];
} {
  const list = allocs.filter((a) => String(a.batchNo).trim() && Number(a.quantity) > QTY_EPS);
  if (!list.length) return {};
  return {
    batch_allocations: list.map((a) => ({
      batch_number: a.batchNo,
      quantity: a.quantity,
    })),
    ...(list.length === 1 ? { batch_number: list[0].batchNo } : {}),
  };
}
