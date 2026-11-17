import type { TFunction } from 'i18next';

import {
  downloadRecordsAsXlsx,
  type ExportXlsxColumn,
} from '../../../../../utils/exportRecordsXlsx';
import { formatAmount, formatDateTime, formatQuantity } from '../../../../../utils/format';
import { deliveryNoticeApi } from '../../../services/delivery-notice';

type DeliveryNoticeLike = Record<string, unknown>;

function formatDateOnly(value: unknown): string {
  if (!value) return '';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD');
}

function formatDateTimeCell(value: unknown): string {
  if (!value) return '';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD HH:mm');
}

export async function enrichDeliveryNoticesForExport(
  headers: DeliveryNoticeLike[],
): Promise<DeliveryNoticeLike[]> {
  const out: DeliveryNoticeLike[] = [];
  for (const header of headers) {
    if (header.id == null) {
      out.push(header);
      continue;
    }
    try {
      const detail = (await deliveryNoticeApi.get(String(header.id))) as DeliveryNoticeLike;
      out.push({ ...header, ...detail });
    } catch {
      out.push(header);
    }
  }
  return out;
}

export function flattenDeliveryNoticesForExport(
  notices: DeliveryNoticeLike[],
): Array<Record<string, unknown>> {
  const rows: Array<Record<string, unknown>> = [];
  for (const notice of notices) {
    const rowKey = String(notice.id ?? notice.notice_code ?? '');
    const header = {
      notice_code: notice.notice_code,
      status: notice.status,
      customer_name: notice.customer_name,
      sales_delivery_code: notice.sales_delivery_code,
      sales_order_code: notice.sales_order_code,
      planned_delivery_date: notice.planned_delivery_date,
      carrier: notice.carrier,
      tracking_number: notice.tracking_number,
      shipping_address: notice.shipping_address,
      total_quantity: notice.total_quantity,
      total_amount: notice.total_amount,
      notes: notice.notes,
      sent_at: notice.sent_at,
      created_at: notice.created_at,
      updated_at: notice.updated_at,
    };
    const items = Array.isArray(notice.items) ? notice.items : [];
    if (items.length === 0) {
      rows.push({ ...header, _rowKey: rowKey });
      continue;
    }
    for (const raw of items) {
      const line = raw as Record<string, unknown>;
      rows.push({
        ...header,
        material_code: line.material_code,
        material_name: line.material_name,
        material_spec: line.material_spec,
        material_unit: line.unit ?? line.material_unit,
        line_quantity: line.quantity ?? line.delivery_quantity,
        unit_price: line.unit_price,
        line_amount: line.total_amount ?? line.amount,
        _rowKey: rowKey,
      });
    }
  }
  return rows;
}

export function buildDeliveryNoticeExportColumns(t: TFunction): ExportXlsxColumn[] {
  return [
    { key: 'notice_code', title: t('app.kuaizhizao.deliveryNote.col.noticeCode'), text: true },
    { key: 'status', title: t('common.status') },
    { key: 'customer_name', title: t('app.kuaizhizao.deliveryNote.field.customer') },
    { key: 'sales_delivery_code', title: t('app.kuaizhizao.deliveryNote.col.salesDeliveryCode'), text: true },
    { key: 'sales_order_code', title: t('app.kuaizhizao.salesOrder.orderCode'), text: true },
    { key: 'planned_delivery_date', title: t('app.kuaizhizao.deliveryNote.col.plannedDelivery') },
    { key: 'carrier', title: t('app.kuaizhizao.deliveryNote.col.carrier') },
    { key: 'tracking_number', title: t('app.kuaizhizao.deliveryNote.col.trackingNumber'), text: true },
    { key: 'shipping_address', title: t('app.kuaizhizao.salesOrder.shippingAddress') },
    { key: 'total_quantity', title: t('app.kuaizhizao.warehouseCommon.colTotalQuantity') },
    { key: 'total_amount', title: t('app.kuaizhizao.warehouseCommon.colAmount') },
    { key: 'material_code', title: t('app.kuaizhizao.warehouseCommon.colMaterialCode'), text: true },
    { key: 'material_name', title: t('app.kuaizhizao.warehouseCommon.colMaterialName') },
    { key: 'material_spec', title: t('app.kuaizhizao.salesOrder.materialSpec') },
    { key: 'material_unit', title: t('common.unit') },
    { key: 'line_quantity', title: t('common.quantity') },
    { key: 'unit_price', title: t('app.kuaizhizao.warehouseCommon.colUnitPrice') },
    { key: 'line_amount', title: t('app.kuaizhizao.warehouseCommon.colAmount') },
    { key: 'notes', title: t('common.remark') },
    { key: 'sent_at', title: t('app.kuaizhizao.deliveryNote.col.sentAt') },
    { key: 'created_at', title: t('common.createdAt') },
    { key: 'updated_at', title: t('common.updatedAt') },
  ];
}

export async function exportDeliveryNoticeLinesXlsx(
  flatRows: Array<Record<string, unknown>>,
  fileName: string,
  t: TFunction,
): Promise<void> {
  const columns = buildDeliveryNoticeExportColumns(t);
  const rows = flatRows.map((row) => ({
    notice_code: String(row.notice_code ?? ''),
    status: String(row.status ?? ''),
    customer_name: String(row.customer_name ?? ''),
    sales_delivery_code: String(row.sales_delivery_code ?? ''),
    sales_order_code: String(row.sales_order_code ?? ''),
    planned_delivery_date: formatDateOnly(row.planned_delivery_date),
    carrier: String(row.carrier ?? ''),
    tracking_number: String(row.tracking_number ?? ''),
    shipping_address: String(row.shipping_address ?? ''),
    total_quantity: formatQuantity(row.total_quantity),
    total_amount: formatAmount(row.total_amount),
    material_code: String(row.material_code ?? ''),
    material_name: String(row.material_name ?? ''),
    material_spec: String(row.material_spec ?? ''),
    material_unit: String(row.material_unit ?? ''),
    line_quantity: formatQuantity(row.line_quantity),
    unit_price: formatAmount(row.unit_price),
    line_amount: formatAmount(row.line_amount),
    notes: String(row.notes ?? ''),
    sent_at: formatDateTimeCell(row.sent_at),
    created_at: formatDateTimeCell(row.created_at),
    updated_at: formatDateTimeCell(row.updated_at),
  }));
  await downloadRecordsAsXlsx(rows, fileName, {
    columns,
    sheetName: t('app.kuaizhizao.deliveryNote.title'),
  });
}
