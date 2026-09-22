import type { Key } from 'react';
import type { TFunction } from 'i18next';

import { resolveAuditPhase } from '../../../../../components/uni-audit/AuditPhaseBadge';
import type { ImportCodeLabelMap } from '../../../../../utils/loadImportDictionaryValues';
import {
  downloadRecordsAsXlsx,
  type ExportXlsxColumn,
} from '../../../../../utils/exportRecordsXlsx';
import { formatAmount, formatDateTime, formatQuantity } from '../../../../../utils/format';
import { translateLifecycleResult } from '../../../../../utils/globalLifecycleI18n';
import type { SalesOrder, SalesOrderItem } from '../../../services/sales-order';
import { getSalesOrderLifecycle } from '../../../utils/salesOrderLifecycle';
import { resolveLifecycleDisplayLabel } from '../shared/ListUniLifecycleCell';

const AUDIT_PHASE_I18N: Record<string, string> = {
  draft: 'components.uniAudit.phaseDraft',
  pending: 'components.uniAudit.phasePending',
  approved: 'components.uniAudit.phaseApproved',
  rejected: 'components.uniAudit.phaseRejected',
  none: 'components.uniAudit.phaseNone',
};

export type SalesOrderExportContext = {
  t: TFunction;
  auditEnabled: boolean;
  dictionaryLabels: {
    CURRENCY?: ImportCodeLabelMap;
    PAYMENT_TERMS?: ImportCodeLabelMap;
    SHIPPING_METHOD?: ImportCodeLabelMap;
  };
};

function dictLabel(map: ImportCodeLabelMap | undefined, code: unknown): string {
  const key = String(code ?? '').trim();
  if (!key) return '';
  return map?.[key] ?? key;
}

function formatPriceType(value: unknown, t: TFunction): string {
  if (value === 'tax_inclusive') return t('app.kuaizhizao.salesContract.priceTypeTaxInclusive');
  if (value === 'tax_exclusive') return t('app.kuaizhizao.salesContract.priceTypeTaxExclusive');
  return String(value ?? '').trim();
}

function formatDateOnly(value: unknown): string {
  if (!value) return '';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD');
}

function formatDateTimeCell(value: unknown): string {
  if (!value) return '';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD HH:mm');
}

function formatPercent(value: unknown): string {
  if (value == null || value === '') return '';
  const n = Number(value);
  if (!Number.isFinite(n)) return '';
  return `${n}%`;
}

function formatBool(value: unknown, t: TFunction): string {
  if (value === true || value === 'true' || value === 1 || value === '1') return t('common.yes');
  if (value === false || value === 'false' || value === 0 || value === '0') return t('common.no');
  return '';
}

function formatAuditPhaseLabel(row: Record<string, unknown>, t: TFunction): string {
  const phase = resolveAuditPhase(row as { audit?: Record<string, unknown>; review_status?: string });
  const i18nKey = AUDIT_PHASE_I18N[phase];
  return i18nKey ? t(i18nKey) : phase;
}

function formatLifecycleLabel(row: Record<string, unknown>, ctx: SalesOrderExportContext): string {
  const orderRecord = {
    id: row.sales_order_id,
    status: row.status,
    review_status: row.review_status,
    has_shippable_products: row.has_shippable_products,
    shippable_quantity: row.shippable_quantity,
    delivery_progress: row.delivery_progress,
    lifecycle: row.lifecycle,
    invoice_progress: row.invoice_progress,
  } as SalesOrder;
  const lifecycle = translateLifecycleResult(
    ctx.t,
    getSalesOrderLifecycle(orderRecord, ctx.auditEnabled, ctx.t),
  );
  return resolveLifecycleDisplayLabel(lifecycle);
}

export function buildSalesOrderItemExportColumns(ctx: SalesOrderExportContext): ExportXlsxColumn[] {
  const { t, auditEnabled } = ctx;
  const columns: ExportXlsxColumn[] = [
    { key: 'order_code', title: t('app.kuaizhizao.salesOrder.orderCode') },
    { key: 'lifecycle', title: t('app.kuaizhizao.salesOrder.lifecycle') },
    { key: 'customer_name', title: t('app.kuaizhizao.salesOrder.customerName') },
    { key: 'customer_contact', title: t('app.kuaizhizao.salesOrder.customerContact') },
    { key: 'customer_phone', title: t('app.kuaizhizao.salesOrder.customerPhone') },
    { key: 'order_date', title: t('app.kuaizhizao.salesOrder.orderDate') },
    { key: 'order_delivery_date', title: t('app.kuaizhizao.salesOrder.deliveryDate') },
    { key: 'contract_code', title: t('app.kuaizhizao.salesContract.contractCode') },
    { key: 'salesman_name', title: t('app.kuaizhizao.salesOrder.salesman') },
    { key: 'total_quantity', title: t('app.kuaizhizao.salesOrder.totalQuantity') },
    { key: 'total_amount', title: t('app.kuaizhizao.salesOrder.totalAmount') },
    { key: 'discount_amount', title: t('app.kuaizhizao.salesOrder.discountAmount') },
    { key: 'price_type', title: t('app.kuaizhizao.salesOrder.priceType') },
    { key: 'currency_code', title: t('app.kuaizhizao.quotation.form.currency') },
    { key: 'payment_terms', title: t('app.kuaizhizao.salesOrder.paymentTerms') },
    { key: 'shipping_method', title: t('app.kuaizhizao.salesOrder.shippingMethod') },
    { key: 'shipping_address', title: t('app.kuaizhizao.salesOrder.shippingAddress') },
    { key: 'delivery_progress', title: t('app.kuaizhizao.salesOrder.deliveryProgress') },
    { key: 'material_code', title: t('app.kuaizhizao.salesOrder.materialCode') },
    { key: 'material_name', title: t('app.kuaizhizao.salesOrder.materialName') },
    { key: 'material_spec', title: t('app.kuaizhizao.salesOrder.materialSpec') },
    { key: 'material_unit', title: t('common.unit') },
    { key: 'required_quantity', title: t('common.quantity') },
    { key: 'unit_price', title: t('app.kuaizhizao.salesOrder.unitPrice') },
    { key: 'tax_rate', title: t('app.kuaizhizao.salesOrder.taxRate') },
    { key: 'item_amount', title: t('app.kuaizhizao.salesOrder.inclAmount') },
    { key: 'delivered_quantity', title: t('app.kuaizhizao.salesOrder.deliveredQty') },
    { key: 'remaining_quantity', title: t('app.kuaizhizao.salesOrder.remainingQty') },
    { key: 'delivery_date', title: t('app.kuaizhizao.salesOrder.deliveryDate') },
    { key: 'is_gift', title: t('app.kuaizhizao.sales.isGift') },
    { key: 'gift_ref_unit_price', title: t('app.kuaizhizao.sales.giftRefUnitPrice') },
    { key: 'line_notes', title: t('app.kuaizhizao.purchaseRequisition.form.lineNotes') },
    { key: 'order_notes', title: t('common.remark') },
    { key: 'work_order_code', title: t('components.documentTrackingPanel.docType.work_order') },
    { key: 'created_by_name', title: t('common.createdBy') },
    { key: 'updated_by_name', title: t('common.updatedBy') },
    { key: 'created_at', title: t('common.createdAt') },
    { key: 'updated_at', title: t('common.updatedAt') },
  ];
  if (auditEnabled) {
    columns.splice(2, 0, {
      key: 'audit_phase',
      title: t('components.uniAudit.colAuditStatus', { defaultValue: '审核状态' }),
    });
  }
  return columns;
}

export function flattenSalesOrdersForExport(orders: SalesOrder[]): Array<Record<string, unknown>> {
  const flatRows: Array<Record<string, unknown>> = [];
  for (const order of orders) {
    const header = {
      sales_order_id: order.id ?? 0,
      order_code: order.order_code,
      customer_name: order.customer_name,
      customer_contact: order.customer_contact,
      customer_phone: order.customer_phone,
      order_date: order.order_date,
      order_delivery_date: order.delivery_date,
      contract_code: order.contract_code,
      salesman_name: order.salesman_name,
      shipping_address: order.shipping_address,
      shipping_method: order.shipping_method,
      payment_terms: order.payment_terms,
      currency_code: order.currency_code,
      price_type: order.price_type,
      total_quantity: order.total_quantity,
      total_amount: order.total_amount,
      discount_amount: order.discount_amount,
      delivery_progress: order.delivery_progress,
      invoice_progress: order.invoice_progress,
      order_notes: order.notes,
      status: order.status,
      review_status: order.review_status,
      pushed_to_computation: order.pushed_to_computation,
      has_shippable_products: order.has_shippable_products,
      shippable_quantity: order.shippable_quantity,
      lifecycle: order.lifecycle,
      audit: order.audit,
      created_by_name: order.created_by_name,
      updated_by_name: order.updated_by_name,
      created_at: order.created_at,
      updated_at: order.updated_at,
    };
    const items = order.items ?? [];
    if (items.length === 0) {
      flatRows.push({
        ...header,
        _rowKey: `order-${order.id}-empty`,
        material_code: '-',
        material_name: '-',
        required_quantity: 0,
        delivery_date: order.delivery_date ?? '',
      });
      continue;
    }
    items.forEach((item: SalesOrderItem, idx: number) => {
      const { notes: lineNotes, ...itemRest } = item;
      flatRows.push({
        ...header,
        ...itemRest,
        _rowKey: item.id ? `order-${order.id}-item-${item.id}` : `order-${order.id}-idx-${idx}`,
        required_quantity: item.required_quantity ?? item.order_quantity ?? 0,
        delivery_date: item.delivery_date ?? order.delivery_date ?? '',
        line_notes: lineNotes,
      });
    });
  }
  return flatRows;
}

export function isSalesOrderFlatExportRow(record: Record<string, unknown>): boolean {
  return typeof record._rowKey === 'string' && record._rowKey.length > 0;
}

export function filterFlatRowsByExportKeys(
  flatRows: Array<Record<string, unknown>>,
  keys: Key[] | undefined,
): Array<Record<string, unknown>> {
  if (!keys?.length) return flatRows;
  const keySet = new Set(keys.map(String));
  return flatRows.filter((row) => {
    const rowKey = String(row._rowKey ?? '');
    if (keySet.has(rowKey)) return true;
    const orderId = row.sales_order_id;
    return orderId != null && keySet.has(String(orderId));
  });
}

export function mapSalesOrderItemToExportRow(
  row: Record<string, unknown>,
  ctx: SalesOrderExportContext,
): Record<string, unknown> {
  const { t, dictionaryLabels } = ctx;
  return {
    order_code: String(row.order_code ?? ''),
    lifecycle: formatLifecycleLabel(row, ctx),
    audit_phase: formatAuditPhaseLabel(row, t),
    customer_name: String(row.customer_name ?? ''),
    customer_contact: String(row.customer_contact ?? ''),
    customer_phone: String(row.customer_phone ?? ''),
    order_date: formatDateOnly(row.order_date),
    order_delivery_date: formatDateOnly(row.order_delivery_date),
    contract_code: String(row.contract_code ?? ''),
    salesman_name: String(row.salesman_name ?? ''),
    total_quantity: formatQuantity(row.total_quantity),
    total_amount: formatAmount(row.total_amount),
    discount_amount: formatAmount(row.discount_amount),
    price_type: formatPriceType(row.price_type, t),
    currency_code: dictLabel(dictionaryLabels.CURRENCY, row.currency_code || 'CNY'),
    payment_terms: dictLabel(dictionaryLabels.PAYMENT_TERMS, row.payment_terms),
    shipping_method: dictLabel(dictionaryLabels.SHIPPING_METHOD, row.shipping_method),
    shipping_address: String(row.shipping_address ?? ''),
    delivery_progress: formatPercent(row.delivery_progress),
    material_code: String(row.material_code ?? ''),
    material_name: String(row.material_name ?? ''),
    material_spec: String(row.material_spec ?? ''),
    material_unit: String(row.material_unit ?? ''),
    required_quantity: formatQuantity(row.required_quantity),
    unit_price: formatAmount(row.unit_price),
    tax_rate: row.tax_rate != null && row.tax_rate !== '' ? String(row.tax_rate) : '',
    item_amount: formatAmount(row.item_amount),
    delivered_quantity: formatQuantity(row.delivered_quantity),
    remaining_quantity: formatQuantity(row.remaining_quantity),
    delivery_date: formatDateOnly(row.delivery_date),
    is_gift: formatBool(row.is_gift, t),
    gift_ref_unit_price: formatAmount(row.gift_ref_unit_price),
    line_notes: String(row.line_notes ?? row.notes ?? ''),
    order_notes: String(row.order_notes ?? ''),
    work_order_code: String(row.work_order_code ?? ''),
    created_by_name: String(row.created_by_name ?? ''),
    updated_by_name: String(row.updated_by_name ?? ''),
    created_at: formatDateTimeCell(row.created_at),
    updated_at: formatDateTimeCell(row.updated_at),
  };
}

export async function exportSalesOrderItemsXlsx(
  flatRows: Array<Record<string, unknown>>,
  fileName: string,
  ctx: SalesOrderExportContext,
): Promise<void> {
  const columns = buildSalesOrderItemExportColumns(ctx);
  const rows = flatRows.map((row) => mapSalesOrderItemToExportRow(row, ctx));
  await downloadRecordsAsXlsx(rows, fileName, {
    columns,
    sheetName: ctx.t('app.kuaizhizao.salesOrder.title'),
  });
}
