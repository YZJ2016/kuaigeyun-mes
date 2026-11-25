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
    taxRate: (() => {
      const raw = line.taxRate ?? line.tax_rate;
      if (raw == null || raw === '') return undefined;
      const num = Number(raw);
      return Number.isFinite(num) && num >= 0 ? num : undefined;
    })(),
  };
}

export type PaymentApplicationPoHeaderFromPreview = {
  invoiceStatus?: string;
  paymentMethod?: string;
};

export type CollectPoPreviewLinesResult = {
  newLines: Record<string, unknown>[];
  skipped: number;
  headerFromPo?: PaymentApplicationPoHeaderFromPreview;
};

function headerFromPurchaseOrderPreview(
  preview: Record<string, unknown>,
): PaymentApplicationPoHeaderFromPreview {
  const invoiceStatus = String(
    preview.invoiceStatus ?? preview.invoice_status ?? '',
  ).trim();
  const paymentMethod = String(
    preview.paymentMethod ?? preview.payment_method ?? '',
  ).trim();
  return {
    ...(invoiceStatus ? { invoiceStatus } : {}),
    ...(paymentMethod ? { paymentMethod } : {}),
  };
}

type PoPreviewAttempt =
  | { poId: number; ok: true; preview: Record<string, unknown> }
  | { poId: number; ok: false };

/** 表单取单：按 PO 行 preview 合并明细（已存在的 sourceId 跳过） */
export async function collectPaymentApplicationItemsFromPurchaseOrderRows(
  rows: Array<{ id: number }>,
  usedPoIds: Set<number>,
): Promise<CollectPoPreviewLinesResult> {
  const targets = rows
    .map((row) => Number(row.id))
    .filter((poId) => poId > 0 && !usedPoIds.has(poId));

  const attempts: PoPreviewAttempt[] = await Promise.all(
    targets.map(async (poId): Promise<PoPreviewAttempt> => {
      try {
        const preview = (await previewPullPaymentApplicationFromPurchaseOrder(
          poId,
        )) as Record<string, unknown>;
        return { poId, ok: true, preview };
      } catch {
        return { poId, ok: false };
      }
    }),
  );

  const newLines: Record<string, unknown>[] = [];
  let skipped = 0;
  let headerFromPo: PaymentApplicationPoHeaderFromPreview | undefined;

  for (const attempt of attempts) {
    if (!attempt.ok) {
      skipped += 1;
      continue;
    }
    const { preview, poId } = attempt;
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
    if (!headerFromPo) {
      headerFromPo = headerFromPurchaseOrderPreview(preview);
    }
    for (const ln of items) {
      newLines.push(mapPreviewLineToFormRow(ln, previewAmounts));
    }
  }

  return { newLines, skipped, headerFromPo };
}