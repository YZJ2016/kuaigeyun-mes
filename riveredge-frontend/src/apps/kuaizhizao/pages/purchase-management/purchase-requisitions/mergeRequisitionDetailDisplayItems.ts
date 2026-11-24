import type { PurchaseRequisitionItem } from '../../../services/purchase-requisition';

function displayGroupKey(item: PurchaseRequisitionItem): string {
  const rid = Number(item.requisition_id ?? 0);
  const mid = Number(item.material_id ?? 0);
  const rd = String(item.required_date ?? '').trim();
  const notes = String(item.notes ?? '').trim();
  return `${rid}|${mid}|${rd}|${notes}`;
}

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** 详情只读：合并部分转单拆出的物理行，按物料+交期+行备注还原为逻辑申请行。 */
export function mergeRequisitionDetailDisplayItems(
  items: PurchaseRequisitionItem[] | undefined,
): PurchaseRequisitionItem[] {
  if (!items?.length) return [];
  const order: string[] = [];
  const buckets = new Map<string, PurchaseRequisitionItem>();

  for (const raw of items) {
    const key = displayGroupKey(raw);
    if (!buckets.has(key)) {
      order.push(key);
      buckets.set(key, { ...raw });
      continue;
    }
    const prev = buckets.get(key)!;
    const draft = toNum(prev.converted_quantity_draft) + toNum(raw.converted_quantity_draft);
    const confirmed =
      toNum(prev.converted_quantity_confirmed) + toNum(raw.converted_quantity_confirmed);
    const qty = toNum(prev.quantity) + toNum(raw.quantity);
    const auxQty =
      prev.aux_quantity != null || raw.aux_quantity != null
        ? toNum(prev.aux_quantity) + toNum(raw.aux_quantity)
        : undefined;
    const convertedAny = Boolean(prev.purchase_order_id) || Boolean(raw.purchase_order_id);
    buckets.set(key, {
      ...prev,
      id: prev.id,
      quantity: qty,
      aux_quantity: auxQty,
      converted_quantity_draft: draft,
      converted_quantity_confirmed: confirmed,
      purchase_order_id: convertedAny ? prev.purchase_order_id ?? raw.purchase_order_id : undefined,
      purchase_order_item_id: prev.purchase_order_item_id ?? raw.purchase_order_item_id,
    });
  }

  return order.map((k) => buckets.get(k)!);
}

export function renderMergedRequisitionConvertedTag(
  item: PurchaseRequisitionItem,
  t: (key: string) => string,
): 'yes' | 'no' | 'partial' {
  const qty = toNum(item.quantity);
  const pushed =
    toNum(item.converted_quantity_draft) + toNum(item.converted_quantity_confirmed);
  if (pushed <= 0) return 'no';
  if (qty > 0 && pushed + 1e-6 >= qty) return 'yes';
  return 'partial';
}