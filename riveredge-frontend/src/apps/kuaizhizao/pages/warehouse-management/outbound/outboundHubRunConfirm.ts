import type { TFunction } from 'i18next';
import dayjs from 'dayjs';
import { warehouseApi } from '../../../services/production';
import { formatApiErrorDetail } from '../../../../../services/api';
import type { OutboundHubOrder, OutboundIssueType } from './outboundHubTypes';
import {
  buildOutboundConfirmPayloadFromDetail,
  enrichOutboundDetailLinesWithHeaderWarehouse,
  hydrateOutboundDetailLinesDefaultBatch,
  hydrateOutboundDetailLinesDefaultLocation,
  resolveOutboundConfirmLineQuantity,
  validateOutboundDetailBeforeConfirm,
} from '../shared/outboundConfirmFromDetail';
import { loadConfirmPreviewMaterialMeta } from './outboundItemTracking';
import {
  fetchMaterialForUnitSelectCache,
  registerMaterialsForUnitSelect,
} from '../../../../../components/material-unit-select';
import type { WarehouseTrackingFlags } from '../shared/warehouseTrackingFlags';
import { toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';
import {
  loadBatchOptionsByMaterialId,
  type InventoryPickOption,
} from './outboundConfirmInventoryOptions';
import { fetchOutboundHubDetail } from '../shared/outboundHubDetail';

function headerFromDetail(
  outboundType: OutboundIssueType,
  detail: Record<string, unknown>,
): {
  delivery_time?: string;
  deliverer_id?: number;
  deliverer_name?: string;
  picker_id?: number;
  picker_name?: string;
} {
  const raw =
    detail.delivery_time ?? detail.picking_time ?? detail.delivery_date ?? detail.picking_date;
  let delivery_time: string | undefined;
  if (raw != null && String(raw).trim()) {
    const parsed = dayjs(String(raw));
    if (parsed.isValid()) delivery_time = toApiBusinessDocumentDateTime(parsed.startOf('day'));
  }
  if (outboundType === 'sales_delivery') {
    return {
      delivery_time,
      deliverer_id:
        detail.deliverer_id != null && Number(detail.deliverer_id) > 0
          ? Number(detail.deliverer_id)
          : undefined,
      deliverer_name: String(detail.deliverer_name ?? detail.delivered_by ?? '').trim() || undefined,
    };
  }
  if (outboundType === 'production_picking') {
    return {
      delivery_time,
      picker_id:
        detail.picker_id != null && Number(detail.picker_id) > 0
          ? Number(detail.picker_id)
          : undefined,
      picker_name: String(detail.picker_name ?? detail.picker ?? '').trim() || undefined,
    };
  }
  return { delivery_time };
}

async function prefetchMaterialsForLines(items: Record<string, unknown>[]) {
  const materialById = new Map<string, import('../../../../master-data/types/material').Material>();
  await Promise.all(
    [...new Set(items.map((it) => it.material_id).filter(Boolean))].map(async (mid) => {
      const m = await fetchMaterialForUnitSelectCache(Number(mid));
      if (m) materialById.set(String(mid), m);
    }),
  );
  registerMaterialsForUnitSelect([...materialById.values()]);
  return materialById;
}

async function loadBatchOptionsForConfirmLines(
  outboundType: OutboundIssueType,
  items: Record<string, unknown>[],
  headerWhId: number,
): Promise<Record<string, InventoryPickOption[]>> {
  const lineBatchKey = (materialId: number, warehouseId: number) => `${materialId}:${warehouseId}`;
  const batchOptionsByKey: Record<string, InventoryPickOption[]> = {};
  const pairs = new Map<string, { mid: number; whId: number }>();
  for (const it of items) {
    const qty = resolveOutboundConfirmLineQuantity(outboundType, it);
    if (!(qty > 0)) continue;
    const mid = Number(it.material_id);
    const whId = Number(it.warehouse_id ?? headerWhId);
    if (!(mid > 0 && whId > 0)) continue;
    pairs.set(lineBatchKey(mid, whId), { mid, whId });
  }
  await Promise.all(
    [...pairs.values()].map(async ({ mid, whId }) => {
      const map = await loadBatchOptionsByMaterialId([mid], whId);
      batchOptionsByKey[lineBatchKey(mid, whId)] = map[mid] ?? [];
    }),
  );
  return batchOptionsByKey;
}

function readExternalPushMessage(resp: unknown): string | undefined {
  if (!resp || typeof resp !== 'object') return undefined;
  const msg = (resp as { external_push_message?: unknown }).external_push_message;
  const text = typeof msg === 'string' ? msg.trim() : '';
  return text || undefined;
}

async function validateOutboundDetailForHubConfirm(options: {
  t: TFunction;
  outboundType: OutboundIssueType;
  detail: Record<string, unknown>;
  trackingFlags: WarehouseTrackingFlags;
}): Promise<Record<string, unknown>> {
  const { t, outboundType, detail, trackingFlags } = options;
  const headerWhId = Number(detail.warehouse_id ?? 0);
  let items = await hydrateOutboundDetailLinesDefaultLocation(
    enrichOutboundDetailLinesWithHeaderWarehouse(detail),
  );
  const materialById = await prefetchMaterialsForLines(items);
  const materialMeta = await loadConfirmPreviewMaterialMeta(items, materialById);
  const lineBatchKey = (materialId: number, warehouseId: number) => `${materialId}:${warehouseId}`;
  const batchOptionsByKey = await loadBatchOptionsForConfirmLines(outboundType, items, headerWhId);
  items = hydrateOutboundDetailLinesDefaultBatch({
    outboundType,
    lines: items,
    materialMeta,
    trackingFlags,
    batchOptionsByKey,
    lineBatchKey,
    headerWarehouseId: headerWhId,
  });
  await validateOutboundDetailBeforeConfirm(
    t,
    outboundType,
    items,
    materialMeta,
    trackingFlags,
    batchOptionsByKey,
    lineBatchKey,
    headerWhId,
  );
  return { ...detail, items };
}

export async function runOutboundHubConfirmFromRecord(options: {
  t: TFunction;
  record: OutboundHubOrder;
  trackingFlags: WarehouseTrackingFlags;
  /**
   * 销售出库：外层已弹 OQC 待检确认并放行时传 true，避免重复 ensure。
   * 未跳过时若需检且不可出库，抛出 ensure.message（批量兜底；列表确认应走弹窗）。
   */
  skipOqcEnsure?: boolean;
}): Promise<{ externalPushMessage?: string }> {
  const { t, record, trackingFlags, skipOqcEnsure = false } = options;
  const outboundType = record.outbound_type;
  if (!record.id || !outboundType) {
    throw new Error(t('app.kuaizhizao.warehouseOutbound.msg.noneConfirmable'));
  }
  if (outboundType === 'outsource_issue') {
    throw new Error(t('app.kuaizhizao.warehouseOutbound.msg.noneConfirmable'));
  }

  const id = String(record.id);

  if (outboundType === 'purchase_return') {
    const detail = await fetchOutboundHubDetail(record);
    if (!detail) {
      throw new Error(t('app.kuaizhizao.warehouseOutbound.msg.loadDetailFailed'));
    }
    await validateOutboundDetailForHubConfirm({ t, outboundType, detail, trackingFlags });
    const resp = await warehouseApi.purchaseReturn.confirm(id);
    return { externalPushMessage: readExternalPushMessage(resp) };
  }

  if (outboundType === 'sales_delivery' && !skipOqcEnsure) {
    const ensure = await warehouseApi.salesDelivery.ensureOqc(id);
    if (ensure.requires_oqc && ensure.can_confirm_outbound === false) {
      throw new Error(
        ensure.message || t('app.kuaizhizao.warehouseOutbound.oqcReview.blockedHint'),
      );
    }
  }

  const detail = await fetchOutboundHubDetail(record);
  if (!detail) {
    throw new Error(t('app.kuaizhizao.warehouseOutbound.msg.loadDetailFailed'));
  }

  const detailForPayload = await validateOutboundDetailForHubConfirm({
    t,
    outboundType,
    detail,
    trackingFlags,
  });

  const payload = buildOutboundConfirmPayloadFromDetail(
    outboundType,
    detailForPayload,
    headerFromDetail(outboundType, detail),
  );

  if (outboundType === 'production_picking') {
    const resp = await warehouseApi.productionPicking.confirm(id, payload);
    return { externalPushMessage: readExternalPushMessage(resp) };
  }
  if (outboundType === 'sales_delivery') {
    const resp = await warehouseApi.salesDelivery.confirm(id, payload);
    return { externalPushMessage: readExternalPushMessage(resp) };
  }
  if (outboundType === 'other_outbound') {
    const resp = await warehouseApi.otherOutbound.confirm(id, payload);
    return { externalPushMessage: readExternalPushMessage(resp) };
  }
  if (outboundType === 'material_borrow') {
    const resp = await warehouseApi.materialBorrow.confirm(id, payload);
    return { externalPushMessage: readExternalPushMessage(resp) };
  }
  throw new Error(t('app.kuaizhizao.warehouseOutbound.confirm.typeNotSupported'));
}

export function formatOutboundConfirmError(error: unknown, t: TFunction): string {
  const err = error as { message?: string; response?: { data?: { detail?: unknown } } };
  return (
    formatApiErrorDetail(err?.response?.data?.detail) ||
    err?.message ||
    t('app.kuaizhizao.warehouseOutbound.confirm.failed')
  );
}
