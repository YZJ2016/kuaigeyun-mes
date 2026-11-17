import type { Key } from 'react';
import type { TFunction } from 'i18next';

import {
  downloadRecordsAsXlsx,
  type ExportXlsxColumn,
} from '../../../../../utils/exportRecordsXlsx';
import { formatAmount, formatDateTime, formatQuantity } from '../../../../../utils/format';
import { fetchInboundHubDetail } from '../inbound/inboundHubDetail';
import {
  inboundReceiptTypeLabel,
  inboundSourceDocNo,
  resolveInboundHubDateRaw,
  resolveInboundHubOperator,
  type InboundHubOrder,
  type InboundReceiptType,
} from '../inbound/inboundHubTypes';
import {
  resolveInboundHubDetailItems,
  resolveInboundHubLineQuantity,
  resolveInboundHubStatusLabel,
} from '../inbound/inboundHubNormalize';
import {
  getOutboundIssueTypeLabel,
  outboundDocumentCode,
  outboundSourceDocNo,
  resolveOutboundHubOperator,
  type OutboundHubOrder,
  type OutboundIssueType,
} from '../outbound/outboundHubTypes';
import { fetchOutboundHubDetail } from './outboundHubDetail';

const EXPORT_DETAIL_CONCURRENCY = 6;

export type WarehouseDocExportContext = {
  t: TFunction;
  sheetName: string;
  /** Hub 页展示单据类型列；独立单据页可 false */
  includeDocTypeColumn?: boolean;
};

function formatDateTimeCell(value: unknown): string {
  if (!value) return '';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD HH:mm');
}

function formatDateOnlyCell(value: unknown): string {
  if (!value) return '';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD');
}

function resolveOutboundHubDateRaw(record: OutboundHubOrder): unknown {
  const row = record as Record<string, unknown>;
  const candidates = [
    row.delivery_date,
    row.delivery_time,
    row.picking_time,
    row.borrow_time,
    row.issued_at,
    row.return_time,
  ];
  for (const value of candidates) {
    if (value == null) continue;
    if (typeof value === 'string' && value.trim() === '') continue;
    return value;
  }
  return null;
}

function resolveOutboundLineQuantity(row: Record<string, unknown>): number | undefined {
  const raw =
    row.outbound_quantity ??
    row.issue_quantity ??
    row.picked_quantity ??
    row.delivered_quantity ??
    row.borrow_quantity ??
    row.return_quantity ??
    row.quantity;
  if (raw == null || raw === '') return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}

function resolveInboundDocCode(order: InboundHubOrder): string {
  const row = order as Record<string, unknown>;
  return String(
    row.receipt_code ??
      row.return_code ??
      row.inbound_code ??
      row.registration_code ??
      row.code ??
      '',
  ).trim();
}

function resolvePartnerNameInbound(order: InboundHubOrder): string {
  return String(order.supplier_name ?? order.customer_name ?? '').trim();
}

function resolvePartnerNameOutbound(order: OutboundHubOrder): string {
  return String(order.customer_name ?? order.supplier_name ?? '').trim();
}

function lineItemsFromDetail(detail: Record<string, unknown> | null): Record<string, unknown>[] {
  if (!detail) return [];
  const items = detail.items;
  if (!Array.isArray(items)) return [];
  return items.filter((it) => it != null && typeof it === 'object') as Record<string, unknown>[];
}

async function enrichInBatches<T extends { id?: number }>(
  headers: T[],
  loadDetail: (row: T) => Promise<Record<string, unknown> | null>,
): Promise<T[]> {
  const out: T[] = [];
  for (let i = 0; i < headers.length; i += EXPORT_DETAIL_CONCURRENCY) {
    const batch = headers.slice(i, i + EXPORT_DETAIL_CONCURRENCY);
    const enriched = await Promise.all(
      batch.map(async (header) => {
        if (header.id == null) return header;
        const detail = await loadDetail(header);
        if (!detail) return header;
        const merged = { ...header, ...detail } as T & { items?: unknown[] };
        const detailItems = lineItemsFromDetail(detail);
        if (detailItems.length > 0) {
          (merged as Record<string, unknown>).items = detailItems;
        }
        return merged;
      }),
    );
    out.push(...enriched);
  }
  return out;
}

export async function enrichInboundHubOrdersForExport(
  headers: InboundHubOrder[],
): Promise<InboundHubOrder[]> {
  return enrichInBatches(headers, fetchInboundHubDetail);
}

export async function enrichOutboundHubOrdersForExport(
  headers: OutboundHubOrder[],
): Promise<OutboundHubOrder[]> {
  return enrichInBatches(headers, fetchOutboundHubDetail);
}

export function flattenInboundHubForExport(orders: InboundHubOrder[]): Array<Record<string, unknown>> {
  const rows: Array<Record<string, unknown>> = [];
  for (const order of orders) {
    const rowKey = `${order.receipt_type}::${order.id}`;
    const header = {
      doc_code: resolveInboundDocCode(order),
      doc_type: order.receipt_type,
      status: order.status,
      source_doc_no: inboundSourceDocNo(order),
      partner_name: resolvePartnerNameInbound(order),
      warehouse_name: order.warehouse_name,
      doc_date: resolveInboundHubDateRaw(order),
      operator: resolveInboundHubOperator(order),
      header_total_quantity: order.total_quantity,
      header_total_amount: order.total_amount ?? order.net_amount ?? order.settlement_gross,
      header_notes: (order as Record<string, unknown>).notes,
      created_at: order.created_at,
      updated_at: order.updated_at,
    };
    const lines = resolveInboundHubDetailItems(order);
    if (lines.length === 0) {
      rows.push({ ...header, _rowKey: rowKey });
      continue;
    }
    for (const line of lines) {
      const lineRec = line as Record<string, unknown>;
      rows.push({
        ...header,
        material_code: lineRec.material_code,
        material_name: lineRec.material_name,
        material_spec: lineRec.material_spec,
        material_model: lineRec.material_model,
        material_unit: lineRec.material_unit ?? lineRec.unit,
        line_quantity: resolveInboundHubLineQuantity(lineRec),
        unit_price: lineRec.unit_price,
        line_amount: lineRec.total_amount,
        batch_number: lineRec.batch_number,
        location_code: lineRec.location_code,
        line_notes: lineRec.notes,
        _rowKey: rowKey,
      });
    }
  }
  return rows;
}

export function flattenOutboundHubForExport(orders: OutboundHubOrder[]): Array<Record<string, unknown>> {
  const rows: Array<Record<string, unknown>> = [];
  for (const order of orders) {
    const rowKey = `${order.outbound_type}::${order.id}`;
    const header = {
      doc_code: outboundDocumentCode(order),
      doc_type: order.outbound_type,
      status: order.status,
      source_doc_no: outboundSourceDocNo(order),
      partner_name: resolvePartnerNameOutbound(order),
      warehouse_name: order.warehouse_name,
      doc_date: resolveOutboundHubDateRaw(order),
      operator: resolveOutboundHubOperator(order),
      header_total_quantity: order.total_quantity,
      header_total_amount: order.total_amount,
      header_notes: order.notes,
      created_at: order.created_at,
      updated_at: order.updated_at,
    };
    const fullItems = lineItemsFromDetail(order as unknown as Record<string, unknown>);
    if (fullItems.length === 0) {
      rows.push({ ...header, _rowKey: rowKey });
      continue;
    }
    for (const line of fullItems) {
      rows.push({
        ...header,
        material_code: line.material_code,
        material_name: line.material_name,
        material_spec: line.material_spec,
        material_model: line.material_model,
        material_unit: line.material_unit ?? line.unit,
        line_quantity: resolveOutboundLineQuantity(line),
        unit_price: line.unit_price,
        line_amount: line.total_amount,
        batch_number: line.batch_number,
        location_code: line.location_code,
        line_notes: line.notes,
        _rowKey: rowKey,
      });
    }
  }
  return rows;
}

/** 独立页（其它入出库、还料等）扁平化：单号字段各异，无 Hub 类型列 */
export function flattenStandaloneWarehouseDocsForExport(
  orders: Array<Record<string, unknown>>,
  options: {
    docCodeField: string;
    docTypeLabel?: string;
    partnerField?: 'supplier_name' | 'customer_name' | 'borrower_name' | 'returner_name';
    dateFields?: string[];
    operatorFields?: string[];
  },
): Array<Record<string, unknown>> {
  const rows: Array<Record<string, unknown>> = [];
  for (const order of orders) {
    const id = order.id;
    const rowKey = id != null ? String(id) : resolveInboundDocCode(order as InboundHubOrder);
    const dateRaw =
      options.dateFields
        ?.map((f) => order[f])
        .find((v) => v != null && String(v).trim() !== '') ?? order.receipt_time ?? order.return_time;
    const operator =
      options.operatorFields
        ?.map((f) => order[f])
        .map((v) => String(v ?? '').trim())
        .find((s) => s) ?? '';
    const partnerKey = options.partnerField;
    const header = {
      doc_code: String(order[options.docCodeField] ?? '').trim(),
      doc_type: options.docTypeLabel,
      status: order.status,
      source_doc_no: String(order.borrow_code ?? order.purchase_order_code ?? order.sales_order_code ?? '').trim(),
      partner_name: partnerKey ? String(order[partnerKey] ?? '').trim() : '',
      warehouse_name: order.warehouse_name,
      doc_date: dateRaw,
      operator,
      header_total_quantity: order.total_quantity,
      header_total_amount: order.total_amount,
      header_notes: order.notes,
      created_at: order.created_at,
      updated_at: order.updated_at,
    };
    const items = lineItemsFromDetail(order);
    if (items.length === 0) {
      rows.push({ ...header, _rowKey: rowKey });
      continue;
    }
    for (const line of items) {
      rows.push({
        ...header,
        material_code: line.material_code,
        material_name: line.material_name,
        material_spec: line.material_spec,
        material_model: line.material_model,
        material_unit: line.material_unit ?? line.unit,
        line_quantity: resolveInboundHubLineQuantity(line) ?? resolveOutboundLineQuantity(line),
        unit_price: line.unit_price,
        line_amount: line.total_amount,
        batch_number: line.batch_number,
        location_code: line.location_code,
        line_notes: line.notes,
        _rowKey: rowKey,
      });
    }
  }
  return rows;
}

export async function resolveWarehouseListExportHeaders<T>(
  type: 'currentPage' | 'selected' | 'all',
  keys: Key[] | undefined,
  pageData: T[] | undefined,
  listRowsRef: Map<string, T>,
  loadAll: () => Promise<T[]>,
): Promise<T[]> {
  if (type === 'currentPage' && pageData?.length) return pageData;
  if (type === 'selected' && keys?.length) {
    const picked = keys
      .map((key) => listRowsRef.get(String(key)))
      .filter((row): row is T => row != null);
    if (picked.length > 0) return picked;
  }
  return loadAll();
}

export function isWarehouseFlatExportRow(record: Record<string, unknown>): boolean {
  return typeof record._rowKey === 'string' && record._rowKey.length > 0;
}

export function filterWarehouseFlatRowsByExportKeys(
  flatRows: Array<Record<string, unknown>>,
  keys: Key[] | undefined,
): Array<Record<string, unknown>> {
  if (!keys?.length) return flatRows;
  const keySet = new Set(keys.map(String));
  return flatRows.filter((row) => {
    const rowKey = String(row._rowKey ?? '');
    if (keySet.has(rowKey)) return true;
    const docCode = String(row.doc_code ?? '');
    return docCode && keySet.has(docCode);
  });
}

export async function fetchAllPaged<T>(
  fetchPage: (current: number, pageSize: number) => Promise<{ data: T[]; total: number }>,
  pageSize = 200,
  maxPages = 500,
): Promise<T[]> {
  const all: T[] = [];
  let total = Number.POSITIVE_INFINITY;
  for (let current = 1; current <= maxPages; current += 1) {
    const { data, total: pageTotal } = await fetchPage(current, pageSize);
    if (typeof pageTotal === 'number') total = pageTotal;
    if (!data.length) break;
    all.push(...data);
    if (all.length >= total) break;
  }
  return all;
}

export function buildWarehouseDocExportColumns(ctx: WarehouseDocExportContext): ExportXlsxColumn[] {
  const { t, includeDocTypeColumn = true } = ctx;
  const columns: ExportXlsxColumn[] = [
    { key: 'doc_code', title: t('app.kuaizhizao.warehouseCommon.colCode'), text: true },
  ];
  if (includeDocTypeColumn) {
    columns.push({ key: 'doc_type', title: t('app.kuaizhizao.warehouseInbound.col.receiptType') });
  }
  columns.push(
    { key: 'status', title: t('common.status') },
    { key: 'source_doc_no', title: t('app.kuaizhizao.warehouseInbound.col.sourceDocNo'), text: true },
    { key: 'partner_name', title: t('app.kuaicaiwu.otherIncome.col.counterparty') },
    { key: 'warehouse_name', title: t('app.kuaizhizao.warehouseCommon.colWarehouse') },
    { key: 'doc_date', title: t('app.kuaizhizao.warehouseInbound.field.documentDate') },
    { key: 'operator', title: t('app.kuaizhizao.warehouseCommon.colExecutor') },
    { key: 'header_total_quantity', title: t('app.kuaizhizao.warehouseCommon.colTotalQuantity') },
    { key: 'header_total_amount', title: t('app.kuaizhizao.warehouseCommon.colAmount') },
    { key: 'material_code', title: t('app.kuaizhizao.warehouseCommon.colMaterialCode'), text: true },
    { key: 'material_name', title: t('app.kuaizhizao.warehouseCommon.colMaterialName') },
    { key: 'material_spec', title: t('app.kuaizhizao.salesOrder.materialSpec') },
    { key: 'material_model', title: t('app.kuaizhizao.quality.common.columns.materialModel') },
    { key: 'material_unit', title: t('common.unit') },
    { key: 'line_quantity', title: t('common.quantity') },
    { key: 'unit_price', title: t('app.kuaizhizao.warehouseCommon.colUnitPrice') },
    { key: 'line_amount', title: t('app.kuaizhizao.warehouseCommon.colAmount') },
    { key: 'batch_number', title: t('app.kuaizhizao.warehouseInbound.col.batchNumber'), text: true },
    { key: 'location_code', title: t('app.kuaizhizao.warehouseInbound.col.locationCode'), text: true },
    { key: 'line_notes', title: t('app.kuaizhizao.purchaseRequisition.form.lineNotes') },
    { key: 'header_notes', title: t('common.remark') },
    { key: 'created_at', title: t('common.createdAt') },
    { key: 'updated_at', title: t('common.updatedAt') },
  );
  return columns;
}

function formatInboundDocType(t: TFunction, value: unknown): string {
  const key = String(value ?? '').trim() as InboundReceiptType;
  if (!key) return '';
  try {
    return inboundReceiptTypeLabel(t, key);
  } catch {
    return key;
  }
}

function formatOutboundDocType(t: TFunction, value: unknown): string {
  const key = String(value ?? '').trim() as OutboundIssueType;
  if (!key) return '';
  return getOutboundIssueTypeLabel(t, key);
}

export function mapWarehouseDocExportRow(
  row: Record<string, unknown>,
  ctx: WarehouseDocExportContext & { direction: 'inbound' | 'outbound' | 'standalone' },
): Record<string, unknown> {
  const { t, direction } = ctx;
  const receiptType = row.doc_type as InboundReceiptType | undefined;
  const statusRaw = String(row.status ?? '');
  const statusLabel =
    direction === 'inbound' && receiptType
      ? resolveInboundHubStatusLabel(t, statusRaw, receiptType)
      : statusRaw;
  const docTypeLabel =
    direction === 'inbound'
      ? formatInboundDocType(t, row.doc_type)
      : direction === 'outbound'
        ? formatOutboundDocType(t, row.doc_type)
        : String(row.doc_type ?? '');
  return {
    doc_code: String(row.doc_code ?? ''),
    doc_type: docTypeLabel,
    status: statusLabel === '-' ? statusRaw : statusLabel,
    source_doc_no: String(row.source_doc_no ?? ''),
    partner_name: String(row.partner_name ?? ''),
    warehouse_name: String(row.warehouse_name ?? ''),
    doc_date: formatDateOnlyCell(row.doc_date),
    operator: String(row.operator ?? ''),
    header_total_quantity: formatQuantity(row.header_total_quantity),
    header_total_amount: formatAmount(row.header_total_amount),
    material_code: String(row.material_code ?? ''),
    material_name: String(row.material_name ?? ''),
    material_spec: String(row.material_spec ?? ''),
    material_model: String(row.material_model ?? ''),
    material_unit: String(row.material_unit ?? ''),
    line_quantity: formatQuantity(row.line_quantity),
    unit_price: formatAmount(row.unit_price),
    line_amount: formatAmount(row.line_amount),
    batch_number: String(row.batch_number ?? ''),
    location_code: String(row.location_code ?? ''),
    line_notes: String(row.line_notes ?? ''),
    header_notes: String(row.header_notes ?? ''),
    created_at: formatDateTimeCell(row.created_at),
    updated_at: formatDateTimeCell(row.updated_at),
  };
}

export async function exportWarehouseDocLinesXlsx(
  flatRows: Array<Record<string, unknown>>,
  fileName: string,
  ctx: WarehouseDocExportContext & { direction: 'inbound' | 'outbound' | 'standalone' },
): Promise<void> {
  const columns = buildWarehouseDocExportColumns(ctx);
  const rows = flatRows.map((row) => mapWarehouseDocExportRow(row, ctx));
  await downloadRecordsAsXlsx(rows, fileName, {
    columns,
    sheetName: ctx.sheetName,
  });
}

export async function enrichStandaloneDocsWithDetail<T extends { id?: number }>(
  headers: T[],
  loadDetail: (id: number) => Promise<Record<string, unknown>>,
): Promise<Array<Record<string, unknown>>> {
  const out: Array<Record<string, unknown>> = [];
  for (let i = 0; i < headers.length; i += EXPORT_DETAIL_CONCURRENCY) {
    const batch = headers.slice(i, i + EXPORT_DETAIL_CONCURRENCY);
    const enriched = await Promise.all(
      batch.map(async (header) => {
        const base = { ...(header as Record<string, unknown>) };
        if (header.id == null) return base;
        const detail = await loadDetail(header.id);
        if (!detail) return base;
        const merged = { ...base, ...detail };
        const detailItems = lineItemsFromDetail(detail);
        if (detailItems.length > 0) merged.items = detailItems;
        return merged;
      }),
    );
    out.push(...enriched);
  }
  return out;
}
