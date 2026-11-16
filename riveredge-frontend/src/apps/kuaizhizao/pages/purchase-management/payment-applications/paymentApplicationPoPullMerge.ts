import { previewPullPaymentApplicationFromPurchaseOrder } from '../../../services/payment-application';

export function mapPreviewLineToFormRow(line: Record<string, unknown>): Record<string, unknown> {
  return {
    lineKind: line.lineKind ?? line.line_kind ?? 'prepayment',
    sourceType: line.sourceType ?? line.source_type,
    sourceId: line.sourceId ?? line.source_id,
    sourceCode: line.sourceCode ?? line.source_code,
    requestAmount: Number(line.requestAmount ?? line.request_amount ?? 0),
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
      const amount = Number(preview.max_push_quantity ?? 0);
      if (!(amount > 0)) {
        skipped += 1;
        continue;
      }
      const items = (preview.items as Record<string, unknown>[] | undefined) ?? [];
      if (!items.length) {
        skipped += 1;
        continue;
      }
      usedPoIds.add(poId);
      for (const ln of items) {
        newLines.push(mapPreviewLineToFormRow(ln));
      }
    } catch {
      skipped += 1;
    }
  }
  return { newLines, skipped };
}
