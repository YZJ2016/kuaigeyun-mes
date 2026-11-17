import type { TFunction } from 'i18next';
import type { Dayjs } from 'dayjs';
import { lineLocationSelectionRequired } from '../../../../../components/uni-wh-dropdown';
import { toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';
import { warehouseApi, outsourceMaterialReceiptApi } from '../../../services/production';
import type { InboundReceiptType } from '../inbound/inboundHubTypes';
import {
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  type WarehouseTrackingFlags,
} from './warehouseTrackingFlags';
import type { ConfirmPreviewMaterialMeta } from '../inbound/inboundItemTracking';
import { loadConfirmPreviewMaterialMeta } from '../inbound/inboundItemTracking';
import {
  fetchMaterialForUnitSelectCache,
  registerMaterialsForUnitSelect,
} from '../../../../../components/material-unit-select';
import { computeSimpleDocumentLineTotal } from '../../../utils/documentLineAmounts';

export type InboundConfirmLineInput = Record<string, unknown> & {
  id?: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string;
  material_unit?: string;
  unit?: string;
  receipt_quantity?: number;
  inbound_quantity?: number;
  return_quantity?: number;
  aux_quantity?: number;
  secondary_quantity?: number;
  unit_price?: number;
  qualified_quantity?: number;
  unqualified_quantity?: number;
  batch_number?: string;
  serial_numbers?: unknown;
  warehouse_id?: number;
  warehouse_name?: string;
  location_id?: number;
  location_code?: string;
  purchase_order_item_id?: number;
  status?: string;
  notes?: string;
};

function resolveInboundConfirmLineQuantity(it: InboundConfirmLineInput): number {
  return Number(it.receipt_quantity ?? it.inbound_quantity ?? it.return_quantity ?? 0);
}

function isServicePurchaseReceipt(
  receiptType: InboundReceiptType,
  detail: Record<string, unknown>,
): boolean {
  return receiptType === 'purchase' && String(detail.order_type ?? '').trim() === '服务采购';
}

export type InboundConfirmReceiverPayload = {
  receiver_id?: number;
  receiver_name?: string;
  returner_id?: number;
  returner_name?: string;
};

async function validateInboundLinesForConfirm(
  t: TFunction,
  receiptType: InboundReceiptType,
  items: InboundConfirmLineInput[],
  materialMeta: Record<number, ConfirmPreviewMaterialMeta>,
  trackingFlags: WarehouseTrackingFlags,
  servicePurchase = false,
): Promise<InboundConfirmLineInput[]> {
  const filtered = items.filter((it) => it.material_id != null && it.id != null);
  for (const it of filtered) {
    const qty = resolveInboundConfirmLineQuantity(it);
    if (!(qty > 0)) {
      throw new Error(
        t('app.kuaizhizao.warehouseInbound.msg.actualQtyMustBePositive', {
          material: it.material_code || it.material_name || '-',
        }),
      );
    }
    if (servicePurchase) {
      continue;
    }
    const lineWh = Number(it.warehouse_id ?? 0);
    if (!(lineWh > 0)) {
      throw new Error(
        t('app.kuaizhizao.warehouseInbound.msg.selectWarehouseForMaterial', {
          material: it.material_code || it.material_name || '-',
        }),
      );
    }
    const locId = it.location_id;
    const locCode = it.location_code;
    const needLoc = await lineLocationSelectionRequired(lineWh, locId, locCode);
    if (needLoc) {
      throw new Error(
        t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', {
          material: it.material_code || it.material_name || '-',
        }),
      );
    }
    const rowId = Number(it.id);
    const meta = materialMeta[rowId] ?? materialMeta[Number(it.material_id)];
    if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
      const batchStr = String(it.batch_number ?? '').trim();
      if (!batchStr) {
        throw new Error(
          t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
            material: it.material_code || it.material_name || '-',
            batches: '—',
          }),
        );
      }
    }
    if (isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) {
      const serialList = Array.isArray(it.serial_numbers)
        ? it.serial_numbers.map((s) => String(s).trim()).filter(Boolean)
        : [];
      const expected = Math.floor(qty);
      if (serialList.length !== expected) {
        throw new Error(
          t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
            material: it.material_code || it.material_name || '-',
            required: expected,
            actual: serialList.length,
          }),
        );
      }
    }
  }
  return filtered;
}

function mapInboundConfirmItems(
  receiptType: InboundReceiptType,
  items: InboundConfirmLineInput[],
  orderStatus?: string,
): Record<string, unknown>[] {
  return items.map((it) => {
    const rowId = Number(it.id);
    const qty = resolveInboundConfirmLineQuantity(it);
    const lineWh = Number(it.warehouse_id);
    const locId = it.location_id;
    const locCode = it.location_code;
    const unitPrice = Number(it.unit_price ?? 0);
    const qualified = Number(it.qualified_quantity ?? it.receipt_quantity ?? qty);
    const unqualified = Number(it.unqualified_quantity ?? 0);
    const batchStr = String(it.batch_number ?? '').trim();
    const serialList = Array.isArray(it.serial_numbers)
      ? it.serial_numbers.map((s) => String(s).trim()).filter(Boolean)
      : [];
    const mapped: Record<string, unknown> = {
      item_id: rowId,
      material_id: Number(it.material_id),
      material_code: it.material_code || '',
      material_name: it.material_name || '',
      material_spec: it.material_spec || undefined,
      material_unit: it.material_unit || it.unit || '个',
      receipt_quantity: qty,
      unit_price: unitPrice,
      total_amount: computeSimpleDocumentLineTotal(qty, unitPrice),
      qualified_quantity: Number((qualified + unqualified > qty ? qty : qualified).toFixed(2)),
      unqualified_quantity: Number((qualified + unqualified > qty ? 0 : unqualified).toFixed(2)),
      batch_number: batchStr || undefined,
      serial_numbers: serialList.length ? serialList : undefined,
      warehouse_id: lineWh,
      warehouse_name: it.warehouse_name ?? '',
      location_id: locId != null && Number(locId) > 0 ? Number(locId) : undefined,
      location_code: locCode ? String(locCode) : undefined,
      status: it.status || orderStatus || '草稿',
      notes: it.notes || undefined,
    };
    if (receiptType === 'purchase') {
      mapped.purchase_order_item_id = Number(it.purchase_order_item_id ?? 0);
    }
    return mapped;
  });
}

export async function executeInboundConfirmFromDetail(options: {
  t: TFunction;
  receiptType: InboundReceiptType;
  orderId: number;
  detail: Record<string, unknown>;
  trackingFlags: WarehouseTrackingFlags;
  receiverPayload: InboundConfirmReceiverPayload;
  documentDate?: Dayjs | null;
  productionReturnCustomData?: Record<string, unknown>;
  materialMeta?: Record<number, ConfirmPreviewMaterialMeta>;
  onSaveProductionReturnCustomFields?: (
    orderId: number,
    data: Record<string, unknown>,
  ) => Promise<void>;
}): Promise<{ externalPushMessage?: string }> {
  const {
    t,
    receiptType,
    orderId,
    detail,
    trackingFlags,
    receiverPayload,
    documentDate,
    productionReturnCustomData,
  } = options;

  const readExternalPushMessage = (resp: unknown): string | undefined => {
    if (!resp || typeof resp !== 'object') return undefined;
    const msg = (resp as { external_push_message?: unknown }).external_push_message;
    const text = typeof msg === 'string' ? msg.trim() : '';
    return text || undefined;
  };
  const rawItems = (Array.isArray(detail.items) ? detail.items : []) as InboundConfirmLineInput[];
  if (!rawItems.length) {
    throw new Error(t('app.kuaizhizao.warehouseInbound.msg.noInboundLines'));
  }

  const servicePurchase = isServicePurchaseReceipt(receiptType, detail);
  const detailHeaderWhId = Number(detail.warehouse_id ?? 0);
  const detailHeaderWhName = String(detail.warehouse_name ?? '');
  const items = rawItems.map((it) => ({
    ...it,
    warehouse_id: Number(it.warehouse_id ?? detailHeaderWhId) || undefined,
    warehouse_name: String(it.warehouse_name ?? detailHeaderWhName) || undefined,
  }));

  let materialMeta = options.materialMeta;
  if (!materialMeta) {
    const materialById = await prefetchMaterialsForConfirm(items);
    materialMeta = await loadConfirmPreviewMaterialMeta(items, materialById);
  }

  const validated = await validateInboundLinesForConfirm(
    t,
    receiptType,
    items,
    materialMeta,
    trackingFlags,
    servicePurchase,
  );
  const mappedItems = mapInboundConfirmItems(receiptType, validated, String(detail.status ?? ''));
  const headerWh = Number(mappedItems[0]?.warehouse_id ?? detail.warehouse_id ?? 0);
  const headerWhName = String(mappedItems[0]?.warehouse_name ?? detail.warehouse_name ?? '');
  const receiptTimePayload =
    documentDate?.isValid() ? { receipt_time: toApiBusinessDocumentDateTime(documentDate) } : {};

  const idStr = String(orderId);

  if (receiptType === 'purchase') {
    const confirmItems = validated.map((src) => {
      const rowId = Number(src.id);
      const qty = Number(src.receipt_quantity ?? 0);
      // 与其他入库一致：详情 API 真源是 aux_quantity，确认体 secondary 须回落行副数量
      const secondaryRaw = src.secondary_quantity ?? src.aux_quantity;
      const lineWh = Number(src.warehouse_id) || 0;
      return {
        item_id: rowId,
        warehouse_id: lineWh > 0 ? lineWh : undefined,
        warehouse_name: lineWh > 0 ? String(src.warehouse_name ?? '') : undefined,
        location_id:
          src.location_id != null && Number(src.location_id) > 0 ? Number(src.location_id) : undefined,
        location_code: src.location_code ? String(src.location_code) : undefined,
        batch_number: String(src.batch_number ?? '').trim() || undefined,
        serial_numbers: Array.isArray(src.serial_numbers)
          ? src.serial_numbers.map(String)
          : undefined,
        primary_quantity: qty,
        secondary_quantity:
          secondaryRaw != null && secondaryRaw !== '' ? Number(secondaryRaw) : undefined,
      };
    });
    const resp = await warehouseApi.purchaseReceipt.confirm(idStr, {
      warehouse_id: headerWh > 0 ? headerWh : undefined,
      warehouse_name: headerWh > 0 ? headerWhName : undefined,
      items: confirmItems,
      ...receiverPayload,
      ...receiptTimePayload,
    });
    return { externalPushMessage: readExternalPushMessage(resp) };
  }

  if (receiptType === 'finished_goods') {
    const resp = await warehouseApi.finishedGoodsReceipt.confirm(idStr, {
      warehouse_id: headerWh,
      warehouse_name: headerWhName,
      items: mappedItems,
      ...receiverPayload,
      ...receiptTimePayload,
    });
    return { externalPushMessage: readExternalPushMessage(resp) };
  }

  if (receiptType === 'semi_finished_goods') {
    const resp = await warehouseApi.semiFinishedGoodsReceipt.confirm(idStr, {
      warehouse_id: headerWh,
      warehouse_name: headerWhName,
      items: mappedItems,
      ...receiverPayload,
      ...receiptTimePayload,
    });
    return { externalPushMessage: readExternalPushMessage(resp) };
  }

  if (receiptType === 'production_return') {
    const resp = await warehouseApi.productionReturn.confirm(idStr, {
      warehouse_id: headerWh,
      warehouse_name: headerWhName,
      items: mappedItems,
      ...receiverPayload,
      ...receiptTimePayload,
    });
    if (
      productionReturnCustomData &&
      Object.keys(productionReturnCustomData).length > 0 &&
      options.onSaveProductionReturnCustomFields
    ) {
      await options.onSaveProductionReturnCustomFields(orderId, productionReturnCustomData);
    }
    return { externalPushMessage: readExternalPushMessage(resp) };
  }

  if (receiptType === 'sales_return') {
    const resp = await warehouseApi.salesReturn.confirm(idStr, {
      ...receiverPayload,
      ...receiptTimePayload,
    });
    return { externalPushMessage: readExternalPushMessage(resp) };
  }

  if (receiptType === 'other_inbound') {
    const confirmItems = validated.map((src) => {
      const rowId = Number(src.id);
      const qty = Number(src.inbound_quantity ?? 0);
      const secondaryRaw = src.secondary_quantity ?? src.aux_quantity;
      return {
        item_id: rowId,
        warehouse_id: Number(src.warehouse_id) || undefined,
        warehouse_name: String(src.warehouse_name ?? '') || undefined,
        location_id:
          src.location_id != null && Number(src.location_id) > 0 ? Number(src.location_id) : undefined,
        location_code: src.location_code ? String(src.location_code) : undefined,
        batch_number: String(src.batch_number ?? '').trim() || undefined,
        serial_numbers: Array.isArray(src.serial_numbers)
          ? src.serial_numbers.map(String)
          : undefined,
        primary_quantity: qty > 0 ? qty : undefined,
        secondary_quantity:
          secondaryRaw != null && secondaryRaw !== '' ? Number(secondaryRaw) : undefined,
      };
    });
    const resp = await warehouseApi.otherInbound.confirm(idStr, {
      warehouse_id: headerWh > 0 ? headerWh : undefined,
      warehouse_name: headerWhName || undefined,
      items: confirmItems,
      ...receiverPayload,
      ...receiptTimePayload,
    });
    return { externalPushMessage: readExternalPushMessage(resp) };
  }

  if (receiptType === 'material_return') {
    const resp = await warehouseApi.materialReturn.confirm(idStr, {
      ...receiverPayload,
      ...receiptTimePayload,
    });
    return { externalPushMessage: readExternalPushMessage(resp) };
  }

  if (receiptType === 'outsource_receipt') {
    await outsourceMaterialReceiptApi.complete(idStr, {
      ...receiverPayload,
      ...receiptTimePayload,
    });
    return {};
  }

  throw new Error(t('app.kuaizhizao.warehouseInbound.msg.unsupportedReceiptType'));
}

async function prefetchMaterialsForConfirm(
  items: InboundConfirmLineInput[],
): Promise<Map<string, import('../../../../master-data/types/material').Material>> {
  const ids = [...new Set(items.map((it) => it.material_id).filter(Boolean))] as number[];
  const materialById = new Map<string, import('../../../../master-data/types/material').Material>();
  await Promise.all(
    ids.map(async (mid) => {
      const m = await fetchMaterialForUnitSelectCache(mid);
      if (m) materialById.set(String(mid), m);
    }),
  );
  registerMaterialsForUnitSelect([...materialById.values()]);
  return materialById;
}
