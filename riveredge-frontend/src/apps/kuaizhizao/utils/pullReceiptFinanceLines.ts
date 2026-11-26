export type PullReceiptFinanceDetailLine = {
  line_no: number;
  purchase_receipt_item_id: number;
  purchase_receipt_id?: number;
  material_code: string;
  material_name: string;
  material_spec?: string | null;
  unit: string;
  quantity: number;
  unit_price: number;
  amount: number;
  tax_rate?: number;
  tax_amount?: number;
  occupied_amount: number;
  max_push_amount: number;
  max_push_quantity: number;
};

export type PurchaseInvoiceDetailItemPayload = {
  item_name: string;
  spec_model?: string | null;
  unit?: string;
  quantity?: number;
  unit_price?: number;
  amount: number;
  tax_rate: number;
  tax_amount: number;
  source_doc_type: string;
  source_doc_id: number;
  source_line_id: number;
  partner_statement_line_id?: number | null;
};

export function buildPurchaseDetailItemsFromPullLines(
  selectedItemIds: number[],
  lineAmounts: Record<number, number>,
  detailLines: PullReceiptFinanceDetailLine[],
  taxRatePercent: number,
  fallbackSourceType: string,
  fallbackSourceDocId: number,
): PurchaseInvoiceDetailItemPayload[] {
  const rateDec = taxRatePercent / 100;
  const detailById = new Map(detailLines.map((row) => [row.purchase_receipt_item_id, row]));
  const items: PurchaseInvoiceDetailItemPayload[] = [];
  for (const itemId of selectedItemIds) {
    const line = detailById.get(itemId);
    if (!line) continue;
    const incl = Math.round((Number(lineAmounts[itemId] ?? 0) || 0) * 100) / 100;
    if (!(incl > 0)) continue;
    const excl = Math.round((incl / (1 + rateDec)) * 100) / 100;
    const tax = Math.round((incl - excl) * 100) / 100;
    const cap = Number(line.max_push_amount ?? 0);
    const maxQty = Number(line.max_push_quantity ?? line.quantity ?? 0);
    const qty =
      cap > 0.0009 && maxQty > 0
        ? Math.round((maxQty * (incl / cap)) * 10000) / 10000
        : line.quantity;
    const docType = line.purchase_receipt_id ? 'purchase_receipt' : fallbackSourceType;
    const docId = line.purchase_receipt_id ?? fallbackSourceDocId;
    items.push({
      item_name: line.material_name,
      spec_model: line.material_spec,
      unit: line.unit,
      quantity: qty,
      unit_price: line.unit_price,
      amount: excl,
      tax_rate: rateDec,
      tax_amount: tax,
      source_doc_type: docType,
      source_doc_id: docId,
      source_line_id: itemId,
    });
  }
  return items;
}

export function initPullReceiptLineSelection(lines: PullReceiptFinanceDetailLine[]) {
  const selectedItemIds: number[] = [];
  const amounts: Record<number, number> = {};
  for (const row of lines) {
    const cap = Number(row.max_push_amount ?? 0);
    if (cap > 0) {
      selectedItemIds.push(row.purchase_receipt_item_id);
      amounts[row.purchase_receipt_item_id] = cap;
    }
  }
  return { selectedItemIds, amounts };
}

export function sumPullReceiptLineAmounts(
  selectedItemIds: number[],
  amounts: Record<number, number>,
): number {
  let sum = 0;
  for (const id of selectedItemIds) {
    sum += Number(amounts[id] ?? 0);
  }
  return Math.round(sum * 100) / 100;
}

export function buildPullReceiptLinesPayload(
  selectedItemIds: number[],
  amounts: Record<number, number>,
): { purchase_receipt_item_id: number; amount: number }[] {
  return selectedItemIds
    .map((id) => ({
      purchase_receipt_item_id: id,
      amount: Number(amounts[id] ?? 0),
    }))
    .filter((row) => row.amount > 0);
}

/** 按行号顺序将表头价税合计分摊到已选行（不超过各行 max_push_amount），用于分批开票/立应付。 */
export function allocatePullReceiptLineAmountsToHeader(
  selectedItemIds: number[],
  detailLines: PullReceiptFinanceDetailLine[],
  targetHeaderAmount: number,
): Record<number, number> {
  const target = Math.round(Number(targetHeaderAmount) * 100) / 100;
  if (!(target > 0) || selectedItemIds.length === 0) {
    return {};
  }
  const capById = new Map(
    detailLines.map((d) => [d.purchase_receipt_item_id, Number(d.max_push_amount ?? 0)]),
  );
  const lineNoById = new Map(
    detailLines.map((d) => [d.purchase_receipt_item_id, Number(d.line_no ?? 0)]),
  );
  const orderedIds = [...selectedItemIds].sort(
    (a, b) => (lineNoById.get(a) ?? 0) - (lineNoById.get(b) ?? 0),
  );
  let remaining = target;
  const out: Record<number, number> = {};
  for (const id of orderedIds) {
    if (remaining <= 0) {
      out[id] = 0;
      continue;
    }
    const cap = Math.max(0, capById.get(id) ?? 0);
    const take = Math.min(cap, remaining);
    out[id] = Math.round(take * 100) / 100;
    remaining = Math.round((remaining - take) * 100) / 100;
  }
  return out;
}

export function reconcilePullReceiptLinesForHeaderAmount(
  selectedItemIds: number[],
  detailLines: PullReceiptFinanceDetailLine[],
  targetHeaderAmount: number,
  currentAmounts?: Record<number, number>,
): {
  selectedItemIds: number[];
  amounts: Record<number, number>;
  payload: { purchase_receipt_item_id: number; amount: number }[];
  lineSum: number;
} {
  const target = Math.round(Number(targetHeaderAmount) * 100) / 100;
  if (currentAmounts && selectedItemIds.length > 0) {
    const currentSum = sumPullReceiptLineAmounts(selectedItemIds, currentAmounts);
    if (Math.abs(currentSum - target) <= 0.009) {
      const effectiveIds = selectedItemIds.filter((id) => Number(currentAmounts[id] ?? 0) > 0);
      return {
        selectedItemIds: effectiveIds,
        amounts: currentAmounts,
        payload: buildPullReceiptLinesPayload(effectiveIds, currentAmounts),
        lineSum: currentSum,
      };
    }
  }
  const amounts = allocatePullReceiptLineAmountsToHeader(
    selectedItemIds,
    detailLines,
    target,
  );
  const effectiveIds = selectedItemIds.filter((id) => Number(amounts[id] ?? 0) > 0);
  const lineSum = sumPullReceiptLineAmounts(effectiveIds, amounts);
  return {
    selectedItemIds: effectiveIds,
    amounts,
    payload: buildPullReceiptLinesPayload(effectiveIds, amounts),
    lineSum,
  };
}
