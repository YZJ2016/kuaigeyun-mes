import type { TFunction } from 'i18next';
import dayjs, { type Dayjs } from 'dayjs';
import { executeInboundConfirmFromDetail } from '../shared/inboundDocumentConfirm';
import type { WarehouseTrackingFlags } from '../shared/warehouseTrackingFlags';
import type { InboundHubOrder, InboundReceiptType } from './inboundHubTypes';
import { resolveInboundHubDateRaw } from './inboundHubTypes';
import { fetchInboundHubDetail } from './inboundHubDetail';
import { resolveInboundConfirmReceiverFromDetail } from './inboundEntryShared';

function receiverPayloadFromDetail(detail: Record<string, unknown>) {
  const r = resolveInboundConfirmReceiverFromDetail(detail);
  if (r.id != null && r.id > 0) {
    return { receiver_id: r.id, receiver_name: r.name };
  }
  return r.name ? { receiver_name: r.name } : {};
}

function documentDateFromDetail(record: InboundHubOrder, detail: Record<string, unknown>): Dayjs | null {
  const rawDate = resolveInboundHubDateRaw({
    ...(detail as InboundHubOrder),
    receipt_type: record.receipt_type,
  });
  if (rawDate == null || String(rawDate).trim() === '') return null;
  const parsed = dayjs(String(rawDate));
  return parsed.isValid() ? parsed.startOf('day') : null;
}

export async function runInboundHubConfirmFromRecord(options: {
  t: TFunction;
  record: InboundHubOrder;
  trackingFlags: WarehouseTrackingFlags;
  onSaveProductionReturnCustomFields?: (orderId: number, data: Record<string, unknown>) => Promise<void>;
}): Promise<{ externalPushMessage?: string }> {
  const { t, record, trackingFlags, onSaveProductionReturnCustomFields } = options;
  if (!record.id || !record.receipt_type) {
    throw new Error(t('app.kuaizhizao.warehouseInbound.msg.notConfirmable'));
  }
  const detail = await fetchInboundHubDetail(record);
  if (!detail) {
    throw new Error(t('app.kuaizhizao.warehouseInbound.msg.loadConfirmPreviewFailed'));
  }
  const receiverPayload = receiverPayloadFromDetail(detail);
  if (!receiverPayload.receiver_id && !receiverPayload.receiver_name) {
    throw new Error(t('app.kuaizhizao.warehouseInbound.msg.selectReceiverRequired'));
  }
  return executeInboundConfirmFromDetail({
    t,
    receiptType: record.receipt_type as InboundReceiptType,
    orderId: Number(record.id),
    detail,
    trackingFlags,
    receiverPayload,
    documentDate: documentDateFromDetail(record, detail),
    onSaveProductionReturnCustomFields,
  });
}
