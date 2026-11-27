/** 取单明细表 rowKey（与 Table selectedRowKeys 须同为 string） */
export function pullReceiptDetailLineRowKey(row: PullReceiptFinanceDetailLine): string {
  return String(row.purchase_receipt_item_id);
}

export function pullReceiptSelectedIdsAsRowKeys(ids: number[]): string[] {
  return ids.map((id) => String(id));
}

export type PullReceiptFinanceDetailLine = {
  line_no: number;
  source_doc_code?: string;
  gross_amount?: number;
  purchase_receipt_item_id: number;
  purchase_receipt_id?: number;
  material_code: string;
  material_name: string;
  material_spec?: string | null;
  unit: string;
  quantity: number;
  unit_price: number;
  amount: number;
  gross_amount?: number;
  source_unit_price_incl?: number;
  tax_rate?: number;
  tax_amount?: number;
  occupied_amount: number;
  max_push_amount: number;
  max_push_quantity: number;
  warehouse_name?: string;
  location_code?: string;
  batch_number?: string;
  partner_statement_line_id?: number | null;
  outsource_order_receipt_id?: number;
  sales_delivery_id?: number;
  sales_order_id?: number;
  sales_order_item_id?: number;
};

export function seedPullReceiptLineInvoiceNumbers(
  selectedIds: number[],
  headerInvoiceNumber: string,
  prev: Record<number, string>,
): Record<number, string> {
  const header = String(headerInvoiceNumber ?? '').trim();
  if (!header) {
    return prev;
  }
  const next = { ...prev };
  for (const id of selectedIds) {
    const cur = String(next[id] ?? '').trim();
    if (!cur) {
      next[id] = header;
    }
  }
  return next;
}

export function applyHeaderInvoiceNumberToPullLines(
  selectedIds: number[],
  headerInvoiceNumber: string,
  prev: Record<number, string>,
  previousHeader: string,
): Record<number, string> {
  const header = String(headerInvoiceNumber ?? '').trim();
  const prevHeader = String(previousHeader ?? '').trim();
  const next = { ...prev };
  for (const id of selectedIds) {
    const cur = String(next[id] ?? '').trim();
    if (!cur || (prevHeader && cur === prevHeader)) {
      if (header) {
        next[id] = header;
      } else if (!cur) {
        delete next[id];
      }
    }
  }
  return next;
}

export function deriveInvoiceQtyFromLineAmount(
  line: PullReceiptFinanceDetailLine,
  incl: number,
): number {
  const cap = Number(line.max_push_amount ?? 0);
  const maxQty = Number(line.max_push_quantity ?? line.quantity ?? 0);
  if (!(incl > 0)) {
    return 0;
  }
  if (cap > 0.0009 && maxQty > 0) {
    return Math.round((maxQty * (incl / cap)) * 10000) / 10000;
  }
  return maxQty > 0 ? maxQty : Number(line.quantity ?? 0);
}

export function deriveLineInclFromInvoiceQty(
  line: PullReceiptFinanceDetailLine,
  qty: number,
): number {
  const cap = Number(line.max_push_amount ?? 0);
  const maxQty = Number(line.max_push_quantity ?? line.quantity ?? 0);
  const q = Number(qty) || 0;
  if (!(q > 0) || !(cap > 0)) {
    return 0;
  }
  if (maxQty > 0) {
    return Math.round((cap * (q / maxQty)) * 100) / 100;
  }
  return cap;
}

export function syncPullReceiptLineQuantitiesFromAmounts(
  selectedItemIds: number[],
  amounts: Record<number, number>,
  detailLines: PullReceiptFinanceDetailLine[],
): Record<number, number> {
  const byId = new Map(detailLines.map((row) => [row.purchase_receipt_item_id, row]));
  const out: Record<number, number> = {};
  for (const id of selectedItemIds) {
    const line = byId.get(id);
    if (!line) continue;
    const incl = Number(amounts[id] ?? 0);
    if (incl > 0) {
      out[id] = deriveInvoiceQtyFromLineAmount(line, incl);
    }
  }
  return out;
}

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
  invoice_number?: string;
};

export function buildPurchaseDetailItemsFromPullLines(
  selectedItemIds: number[],
  lineAmounts: Record<number, number>,
  detailLines: PullReceiptFinanceDetailLine[],
  taxRatePercent: number,
  fallbackSourceType: string,
  fallbackSourceDocId: number,
  lineQuantities?: Record<number, number>,
  lineInvoiceNumbers?: Record<number, string>,
  headerInvoiceNumber?: string,
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
    const explicitQty = lineQuantities?.[itemId];
    const qty =
      explicitQty != null && Number(explicitQty) > 0
        ? Math.round(Number(explicitQty) * 10000) / 10000
        : deriveInvoiceQtyFromLineAmount(line, incl);
    const unitExcl =
      qty > 0 ? Math.round((excl / qty) * 10000) / 10000 : Number(line.unit_price ?? 0);
    const salesDeliveryId = line.sales_delivery_id;
    const salesOrderId = line.sales_order_id;
    const outsourceReceiptId = line.outsource_order_receipt_id;
    const docType = salesDeliveryId
      ? 'sales_delivery'
      : salesOrderId
        ? 'sales_order'
        : outsourceReceiptId
          ? 'outsource_order_receipt'
          : line.purchase_receipt_id
            ? 'purchase_receipt'
            : fallbackSourceType;
    const docId =
      salesDeliveryId
      ?? salesOrderId
      ?? outsourceReceiptId
      ?? line.purchase_receipt_id
      ?? fallbackSourceDocId;
    const stmtLineId = line.partner_statement_line_id;
    const lineInvoiceNumber = String(
      lineInvoiceNumbers?.[itemId] ?? headerInvoiceNumber ?? '',
    ).trim();
    items.push({
      item_name: line.material_name,
      spec_model: line.material_spec,
      unit: line.unit,
      quantity: qty,
      unit_price: unitExcl,
      amount: excl,
      tax_rate: rateDec,
      tax_amount: tax,
      source_doc_type: docType,
      source_doc_id: docId,
      source_line_id: itemId,
      ...(stmtLineId && stmtLineId > 0 ? { partner_statement_line_id: stmtLineId } : {}),
      ...(lineInvoiceNumber ? { invoice_number: lineInvoiceNumber } : {}),
    });
  }
  return items;
}

export function initPullReceiptLineSelection(lines: PullReceiptFinanceDetailLine[]) {
  const selectedItemIds: number[] = [];
  const amounts: Record<number, number> = {};
  const quantities: Record<number, number> = {};
  for (const row of lines) {
    const cap = Number(row.max_push_amount ?? 0);
    const id = row.purchase_receipt_item_id;
    if (cap > 0) {
      selectedItemIds.push(id);
      amounts[id] = cap;
      quantities[id] = deriveInvoiceQtyFromLineAmount(row, cap);
    }
  }
  return { selectedItemIds, amounts, quantities };
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
