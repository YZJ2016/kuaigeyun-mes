import { previewPullPaymentApplicationFromPurchaseOrder } from '../../../services/payment-application';

export function mapPreviewLineToFormRow(
  line: Record<string, unknown>,
  preview?: { sourceOrderAmount?: number; maxRequestAmount?: number },
): Record<string, unknown> {
  const maxRemaining = Number(
    preview?.maxRequestAmount ?? line.maxRequestAmount ?? line.max_request_amount ?? 0,
  );
  const sourceOrderAmount = Number(
    preview?.sourceOrderAmount ?? line.sourceOrderAmount ?? line.source_order_amount ?? 0,
  );
  const defaultRequest = Number(line.requestAmount ?? line.request_amount ?? 0);
  const requestAmount = maxRemaining > 0 ? maxRemaining : defaultRequest;
  return {
    lineKind: line.lineKind ?? line.line_kind ?? 'prepayment',
    sourceType: line.sourceType ?? line.source_type,
    sourceId: line.sourceId ?? line.source_id,
    sourceCode: line.sourceCode ?? line.source_code,
    sourceOrderAmount: sourceOrderAmount > 0 ? sourceOrderAmount : undefined,
    maxRequestAmount: maxRemaining > 0 ? maxRemaining : undefined,
    requestAmount,
    materialName: line.materialName ?? line.material_name,
    materialSpec: line.materialSpec ?? line.material_spec,
    quantity: line.quantity != null && line.quantity !== '' ? Number(line.quantity) : undefined,
    materialUnit: line.materialUnit ?? line.material_unit,
    sourceLineId:
      line.sourceLineId != null || line.source_line_id != null
        ? Number(line.sourceLineId ?? line.source_line_id)
        : undefined,
  };
}

export type CollectPoPreviewLinesResult = {
  newLines: Record<string, unknown>[];
  skipped: number;
};

/** 表单取单：按 PO 行 preview 合并明细（已存在的 sourceId 跳过） */
export async function collectPaymentApplicationItemsFromPurchaseOrderRows(
  rows: Array<{ id: number }>,
  usedPoIds: Set<number>,
): Promise<CollectPoPreviewLinesResult> {
  const newLines: Record<string, unknown>[] = [];
  let skipped = 0;
  for (const row of rows) {
    const poId = Number(row.id);
    if (!poId || usedPoIds.has(poId)) continue;
    try {
      const preview = await previewPullPaymentApplicationFromPurchaseOrder(poId);
      if (preview.has_blocking_issues) {
        skipped += 1;
        continue;
      }
      const maxRemaining = Number(preview.max_push_quantity ?? 0);
      if (!(maxRemaining > 0)) {
        skipped += 1;
        continue;
      }
      const items = (preview.items as Record<string, unknown>[] | undefined) ?? [];
      if (!items.length) {
        skipped += 1;
        continue;
      }
      const previewAmounts = {
        sourceOrderAmount: Number(preview.source_order_amount ?? preview.sourceOrderAmount ?? 0),
        maxRequestAmount: maxRemaining,
      };
      usedPoIds.add(poId);
      for (const ln of items) {
        newLines.push(mapPreviewLineToFormRow(ln, previewAmounts));
      }
    } catch {
      skipped += 1;
    }
  }
  return { newLines, skipped };
}
