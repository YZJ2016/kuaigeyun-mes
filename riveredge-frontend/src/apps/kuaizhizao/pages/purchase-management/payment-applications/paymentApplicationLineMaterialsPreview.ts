import type {
  DocumentLineMaterialPreviewItem,
} from '../../../../../components/document-line-materials-preview';
import type {
  PaymentApplicationLine,
  PaymentApplicationPurchaseOrderSource,
} from '../../../services/payment-application';
import { payableService } from '../../../../kuaicaiwu/services/finance/payable';
import { warehouseApi } from '../../../services/warehouse-execution';
import { getPurchaseOrder, type PurchaseOrderItem } from '../../../services/purchase';

const PAYABLE_SOURCE_PURCHASE_RECEIPT = '采购入库';

export function isPurchaseOrderSourceType(sourceType: unknown): boolean {
  const raw = String(sourceType ?? '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_');
  return raw === 'purchase_order' || raw === 'purchaseorder';
}

export function isPayableLineSourceType(sourceType: unknown): boolean {
  return String(sourceType ?? '').trim() === 'payable';
}

function normalizeSourceKey(sourceType: unknown): string {
  return String(sourceType ?? '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_');
}

export function isPurchaseReceiptPayableSource(sourceType: unknown): boolean {
  const st = String(sourceType ?? '').trim();
  const sl = normalizeSourceKey(sourceType);
  return (
    st === PAYABLE_SOURCE_PURCHASE_RECEIPT
    || sl === 'purchase_receipt'
    || sl === 'purchasereceipt'
  );
}

export function mapPurchaseOrderItemsToPreview(
  items: PurchaseOrderItem[] | PaymentApplicationPurchaseOrderSource['items'] | undefined,
): DocumentLineMaterialPreviewItem[] {
  if (!items?.length) return [];
  const out: DocumentLineMaterialPreviewItem[] = [];
  for (const it of items) {
    const row = it as Record<string, unknown>;
    const materialName = String(row.materialName ?? row.material_name ?? '').trim();
    const materialCode = String(row.materialCode ?? row.material_code ?? '').trim();
    const materialSpec = String(row.materialSpec ?? row.material_spec ?? '').trim();
    if (!materialName && !materialCode) continue;
    out.push({
      material_name: materialName || materialCode,
      material_code: materialCode || undefined,
      material_spec: materialSpec || undefined,
    });
  }
  return out;
}

export function mapPurchaseReceiptItemsToPreview(
  items: unknown[] | undefined,
): DocumentLineMaterialPreviewItem[] {
  if (!items?.length) return [];
  const out: DocumentLineMaterialPreviewItem[] = [];
  for (const it of items) {
    const row = it as Record<string, unknown>;
    const materialName = String(row.materialName ?? row.material_name ?? '').trim();
    const materialCode = String(row.materialCode ?? row.material_code ?? '').trim();
    const materialSpec = String(row.materialSpec ?? row.material_spec ?? '').trim();
    if (!materialName && !materialCode) continue;
    out.push({
      material_name: materialName || materialCode,
      material_code: materialCode || undefined,
      material_spec: materialSpec || undefined,
    });
  }
  return out;
}

export type PaymentApplicationLineMaterialPreviewContext = {
  purchaseOrderSources?: PaymentApplicationPurchaseOrderSource[];
  poPreviewByOrderId: Record<number, DocumentLineMaterialPreviewItem[]>;
  payablePreviewByPayableId: Record<number, DocumentLineMaterialPreviewItem[]>;
};

export function resolvePaymentApplicationLineMaterialPreview(
  row: PaymentApplicationLine | Record<string, unknown>,
  context: PaymentApplicationLineMaterialPreviewContext,
): DocumentLineMaterialPreviewItem[] {
  const name = String(row.materialName ?? '').trim();
  if (name) {
    return [
      {
        material_name: name,
        material_spec: (row.materialSpec as string | undefined) ?? undefined,
      },
    ];
  }
  if (isPurchaseOrderSourceType(row.sourceType)) {
    const sid = row.sourceId != null ? Number(row.sourceId) : 0;
    const code = String(row.sourceCode ?? '').trim();
    const po =
      (sid > 0
        ? context.purchaseOrderSources?.find((p) => Number(p.id) === sid)
        : undefined)
      ?? (code
        ? context.purchaseOrderSources?.find((p) => String(p.orderCode).trim() === code)
        : undefined);
    if (po?.items?.length) {
      return mapPurchaseOrderItemsToPreview(po.items);
    }
    if (sid > 0 && context.poPreviewByOrderId[sid]?.length) {
      return context.poPreviewByOrderId[sid];
    }
  }
  const payableId = Number(row.payableId ?? 0);
  if (payableId > 0 && context.payablePreviewByPayableId[payableId]?.length) {
    return context.payablePreviewByPayableId[payableId];
  }
  if (isPayableLineSourceType(row.sourceType) && payableId > 0) {
    return context.payablePreviewByPayableId[payableId] ?? [];
  }
  return [];
}

export async function fetchPayableLineMaterialPreviewItems(
  payableId: number,
): Promise<DocumentLineMaterialPreviewItem[]> {
  const payable = await payableService.getPayable(payableId);
  const sourceType = payable.source_type;
  const sourceId = Number(payable.source_id ?? 0);
  if (sourceId <= 0) {
    return [];
  }
  if (isPurchaseReceiptPayableSource(sourceType)) {
    const receipt = (await warehouseApi.purchaseReceipt.get(String(sourceId))) as {
      items?: unknown[];
    };
    return mapPurchaseReceiptItemsToPreview(receipt.items);
  }
  if (isPurchaseOrderSourceType(sourceType) || String(sourceType ?? '').trim() === '订单里程碑') {
    const po = await getPurchaseOrder(sourceId);
    return mapPurchaseOrderItemsToPreview(po.items);
  }
  return [];
}

export function collectPayableIdsNeedingMaterialPreview(
  items: unknown,
): number[] {
  const rows = Array.isArray(items) ? items : [];
  const ids = new Set<number>();
  for (const raw of rows) {
    const row = raw as Record<string, unknown>;
    if (String(row.materialName ?? '').trim()) {
      continue;
    }
    const payableId = Number(row.payableId ?? 0);
    if (payableId > 0 && isPayableLineSourceType(row.sourceType)) {
      ids.add(payableId);
    }
  }
  return [...ids];
}