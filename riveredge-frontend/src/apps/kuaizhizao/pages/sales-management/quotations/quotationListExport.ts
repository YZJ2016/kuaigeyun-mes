import type { TFunction } from 'i18next';

import { resolveAuditPhase } from '../../../../../components/uni-audit/AuditPhaseBadge';
import type { ImportCodeLabelMap } from '../../../../../utils/loadImportDictionaryValues';
import {
  downloadRecordsAsXlsx,
  type ExportXlsxColumn,
} from '../../../../../utils/exportRecordsXlsx';
import { formatDateTime, formatNumber, formatQuantity, formatAmount } from '../../../../../utils/format';
import { translateLifecycleResult } from '../../../../../utils/globalLifecycleI18n';
import type { Quotation } from '../../../services/quotation';
import { getQuotationLifecycle } from '../../../utils/quotationLifecycle';
import { resolveLifecycleDisplayLabel } from '../shared/ListUniLifecycleCell';
import { quotationDownstreamPushPercent } from '../shared/pushProgress';

const AUDIT_PHASE_I18N: Record<string, string> = {
  draft: 'components.uniAudit.phaseDraft',
  pending: 'components.uniAudit.phasePending',
  approved: 'components.uniAudit.phaseApproved',
  rejected: 'components.uniAudit.phaseRejected',
  none: 'components.uniAudit.phaseNone',
};

export type QuotationExportContext = {
  t: TFunction;
  quotationAuditRequired: boolean;
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
  const text = String(value ?? '').trim();
  return text;
}

function formatVersionState(record: Quotation, t: TFunction): string {
  const raw = pickField(record, 'is_latest_in_series', 'isLatestInSeries', 'is_latest', 'isLatest');
  if (raw === true || raw === 'true' || raw === 1 || raw === '1') {
    return t('app.kuaizhizao.quotation.latestTag');
  }
  if (raw === false || raw === 'false' || raw === 0 || raw === '0') {
    return t('app.kuaizhizao.quotation.historyTag');
  }
  return '';
}

function formatAuditPhaseLabel(record: Quotation, t: TFunction): string {
  const phase = resolveAuditPhase(record);
  const i18nKey = AUDIT_PHASE_I18N[phase];
  return i18nKey ? t(i18nKey) : phase;
}

function formatLifecycleLabel(record: Quotation, ctx: QuotationExportContext): string {
  const lifecycle = translateLifecycleResult(
    ctx.t,
    getQuotationLifecycle(record, ctx.quotationAuditRequired, ctx.t),
  );
  return resolveLifecycleDisplayLabel(lifecycle);
}

function formatPushProgress(record: Quotation, t: TFunction): string {
  const percent = quotationDownstreamPushPercent(record);
  return percent >= 100
    ? t('app.kuaizhizao.salesManagement.pushProgress.pushed')
    : t('app.kuaizhizao.salesManagement.pushProgress.notPushed');
}

function pickField(record: Quotation, ...keys: string[]): unknown {
  const raw = record as Record<string, unknown>;
  for (const key of keys) {
    const value = raw[key];
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return '';
}

function formatDateOnly(value: unknown): string {
  if (!value) return '';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD');
}

function formatDateTimeCell(value: unknown): string {
  if (!value) return '';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD HH:mm');
}

export function buildQuotationExportColumns(ctx: QuotationExportContext): ExportXlsxColumn[] {
  const { t, quotationAuditRequired } = ctx;
  const columns: ExportXlsxColumn[] = [
    { key: 'quotation_code', title: t('app.kuaizhizao.quotation.colQuotationCode') },
    { key: 'quotation_series_code', title: t('app.kuaizhizao.quotation.colSeries') },
    { key: 'version_no', title: t('app.kuaizhizao.quotation.colVersion') },
    { key: 'lifecycle', title: t('app.kuaizhizao.quotation.colLifecycle') },
    { key: 'customer_name', title: t('app.kuaizhizao.customerFollowUp.colCustomer') },
    { key: 'customer_contact', title: t('app.kuaizhizao.quotation.import.customerContact') },
    { key: 'customer_phone', title: t('app.kuaizhizao.quotation.import.customerPhone') },
    { key: 'quotation_date', title: t('app.kuaizhizao.quotation.colQuotationDate') },
    { key: 'valid_until', title: t('app.kuaizhizao.quotation.form.validUntil') },
    { key: 'delivery_date', title: t('app.kuaizhizao.quotation.form.expectedDeliveryDate') },
    { key: 'total_quantity', title: t('app.kuaizhizao.salesOrder.totalQuantity') },
    { key: 'total_amount', title: t('app.kuaizhizao.quotation.colTotalAmount') },
    { key: 'discount_amount', title: t('app.kuaizhizao.salesOrder.discountAmount') },
    { key: 'price_type', title: t('app.kuaizhizao.salesOrder.priceType') },
    { key: 'currency_code', title: t('app.kuaizhizao.quotation.form.currency') },
    { key: 'payment_terms', title: t('app.kuaizhizao.salesOrder.paymentTerms') },
    { key: 'shipping_method', title: t('app.kuaizhizao.salesOrder.shippingMethod') },
    { key: 'shipping_address', title: t('app.kuaizhizao.salesOrder.shippingAddress') },
    { key: 'salesman_name', title: t('app.kuaizhizao.quotation.colSalesPersonnel') },
    { key: 'downstream_push_progress', title: t('app.kuaizhizao.salesManagement.pushProgress.title') },
    { key: 'sales_order_code', title: t('app.kuaizhizao.quotation.form.linkedSalesOrder') },
    { key: 'contract_code', title: t('components.documentTrackingPanel.docType.sales_contract') },
    { key: 'sales_review_code', title: t('components.documentTrackingPanel.docType.sales_review') },
    { key: 'notes', title: t('common.remark') },
    { key: 'is_latest_in_series', title: t('app.kuaizhizao.quotation.colVersionState') },
    { key: 'created_by_name', title: t('common.createdBy') },
    { key: 'updated_by_name', title: t('common.updatedBy') },
    { key: 'created_at', title: t('common.createdAt') },
    { key: 'updated_at', title: t('common.updatedAt') },
  ];
  if (quotationAuditRequired) {
    columns.splice(4, 0, {
      key: 'audit_phase',
      title: t('components.uniAudit.colAuditStatus', { defaultValue: '审核状态' }),
    });
  }
  return columns;
}

export function mapQuotationToExportRow(
  record: Quotation,
  ctx: QuotationExportContext,
): Record<string, unknown> {
  const { t, dictionaryLabels } = ctx;
  const versionNo = Number(pickField(record, 'version_no', 'versionNo') || 1);
  return {
    quotation_code: String(pickField(record, 'quotation_code', 'quotation_number', 'quotationCode') ?? ''),
    quotation_series_code: String(
      pickField(record, 'quotation_series_code', 'quotationSeriesCode') ?? '',
    ),
    version_no: t('app.kuaizhizao.quotation.versionDisplay', { n: versionNo }),
    lifecycle: formatLifecycleLabel(record, ctx),
    audit_phase: formatAuditPhaseLabel(record, t),
    customer_name: String(pickField(record, 'customer_name', 'customerName') ?? ''),
    customer_contact: String(pickField(record, 'customer_contact', 'customerContact') ?? ''),
    customer_phone: String(pickField(record, 'customer_phone', 'customerPhone') ?? ''),
    quotation_date: formatDateOnly(pickField(record, 'quotation_date', 'quotationDate')),
    valid_until: formatDateOnly(pickField(record, 'valid_until', 'validUntil')),
    delivery_date: formatDateOnly(pickField(record, 'delivery_date', 'deliveryDate')),
    total_quantity: formatQuantity(pickField(record, 'total_quantity', 'totalQuantity')),
    total_amount: formatAmount(pickField(record, 'total_amount', 'totalAmount')),
    discount_amount: formatAmount(pickField(record, 'discount_amount', 'discountAmount')),
    price_type: formatPriceType(pickField(record, 'price_type', 'priceType'), t),
    currency_code: dictLabel(
      dictionaryLabels.CURRENCY,
      pickField(record, 'currency_code', 'currencyCode') || 'CNY',
    ),
    payment_terms: dictLabel(
      dictionaryLabels.PAYMENT_TERMS,
      pickField(record, 'payment_terms', 'paymentTerms'),
    ),
    shipping_method: dictLabel(
      dictionaryLabels.SHIPPING_METHOD,
      pickField(record, 'shipping_method', 'shippingMethod'),
    ),
    shipping_address: String(pickField(record, 'shipping_address', 'shippingAddress') ?? ''),
    salesman_name: String(pickField(record, 'salesman_name', 'salesmanName') ?? ''),
    downstream_push_progress: formatPushProgress(record, t),
    sales_order_code: String(pickField(record, 'sales_order_code', 'salesOrderCode') ?? ''),
    contract_code: String(pickField(record, 'contract_code', 'contractCode') ?? ''),
    sales_review_code: String(pickField(record, 'sales_review_code', 'salesReviewCode') ?? ''),
    notes: String(pickField(record, 'notes') ?? ''),
    is_latest_in_series: formatVersionState(record, t),
    created_by_name: String(pickField(record, 'created_by_name', 'createdByName') ?? ''),
    updated_by_name: String(pickField(record, 'updated_by_name', 'updatedByName') ?? ''),
    created_at: formatDateTimeCell(pickField(record, 'created_at', 'createdAt')),
    updated_at: formatDateTimeCell(pickField(record, 'updated_at', 'updatedAt')),
  };
}

export async function exportQuotationsXlsx(
  items: Quotation[],
  fileName: string,
  ctx: QuotationExportContext,
): Promise<void> {
  const columns = buildQuotationExportColumns(ctx);
  const rows = items.map((item) => mapQuotationToExportRow(item, ctx));
  await downloadRecordsAsXlsx(rows, fileName, {
    columns,
    sheetName: ctx.t('app.kuaizhizao.menu.sales-management.quotations'),
  });
}

export function buildQuotationItemExportColumns(ctx: QuotationExportContext): ExportXlsxColumn[] {
  const { t, quotationAuditRequired } = ctx;
  const columns: ExportXlsxColumn[] = [
    { key: 'quotation_code', title: t('app.kuaizhizao.quotation.colQuotationCode') },
    { key: 'version_no', title: t('app.kuaizhizao.quotation.colVersion') },
    { key: 'lifecycle', title: t('app.kuaizhizao.quotation.colLifecycle') },
    { key: 'customer_name', title: t('app.kuaizhizao.customerFollowUp.colCustomer') },
    { key: 'quotation_date', title: t('app.kuaizhizao.quotation.colQuotationDate') },
    { key: 'salesman_name', title: t('app.kuaizhizao.quotation.colSalesPersonnel') },
    { key: 'price_type', title: t('app.kuaizhizao.salesOrder.priceType') },
    { key: 'currency_code', title: t('app.kuaizhizao.quotation.form.currency') },
    { key: 'material_code', title: t('app.kuaizhizao.quotation.import.materialCode') },
    { key: 'material_name', title: t('app.kuaizhizao.quotation.import.materialName') },
    { key: 'material_spec', title: t('app.kuaizhizao.salesOrder.materialSpec') },
    { key: 'material_model', title: t('app.master-data.materials.model') },
    {
      key: 'partner_material_code',
      title: t('app.master-data.priceBook.customerMaterialCode'),
    },
    {
      key: 'partner_material_name',
      title: t('app.master-data.priceBook.customerMaterialName'),
    },
    { key: 'material_unit', title: t('common.unit') },
    { key: 'quote_quantity', title: t('common.quantity') },
    { key: 'unit_price', title: t('app.kuaizhizao.quotation.import.unitPrice') },
    { key: 'tax_rate', title: t('app.kuaizhizao.salesOrder.taxRate') },
    { key: 'total_amount', title: t('app.kuaizhizao.quotation.colTotalAmount') },
    { key: 'is_gift', title: t('app.kuaizhizao.sales.isGift') },
    { key: 'delivery_date', title: t('app.kuaizhizao.quotation.import.deliveryDate') },
    { key: 'line_notes', title: t('common.remark') },
    { key: 'order_notes', title: t('common.remark') },
  ];
  if (quotationAuditRequired) {
    columns.splice(3, 0, {
      key: 'audit_phase',
      title: t('components.uniAudit.colAuditStatus', { defaultValue: '审核状态' }),
    });
  }
  return columns;
}

function formatBool(value: unknown, t: TFunction): string {
  if (value === true || value === 'true' || value === 1 || value === '1') return t('common.yes');
  if (value === false || value === 'false' || value === 0 || value === '0') return t('common.no');
  return '';
}

export function isQuotationDetailExportRow(record: Record<string, unknown>): boolean {
  return typeof record._rowKey === 'string' && String(record._rowKey).startsWith('qt-');
}

export function flattenQuotationsForItemExport(
  quotations: Quotation[],
): Array<Record<string, unknown>> {
  const flatRows: Array<Record<string, unknown>> = [];
  for (const quotation of quotations) {
    const versionNo = Number(pickField(quotation, 'version_no', 'versionNo') || 1);
    const header = {
      quotation_id: quotation.id,
      quotation_code: pickField(quotation, 'quotation_code', 'quotationCode'),
      version_no: versionNo,
      customer_name: pickField(quotation, 'customer_name', 'customerName'),
      quotation_date: pickField(quotation, 'quotation_date', 'quotationDate'),
      salesman_name: pickField(quotation, 'salesman_name', 'salesmanName'),
      price_type: pickField(quotation, 'price_type', 'priceType'),
      currency_code: pickField(quotation, 'currency_code', 'currencyCode') || 'CNY',
      status: quotation.status,
      review_status: quotation.review_status,
      lifecycle: quotation.lifecycle,
      order_notes: pickField(quotation, 'notes'),
    };
    const items = quotation.items ?? [];
    if (items.length === 0) {
      flatRows.push({
        ...header,
        _rowKey: `qt-${quotation.id ?? 'x'}-empty`,
        material_code: '-',
        material_name: '-',
        material_spec: '',
        material_model: '',
        partner_material_code: '',
        partner_material_name: '',
        material_unit: '',
        quote_quantity: 0,
        unit_price: 0,
        tax_rate: '',
        total_amount: 0,
        is_gift: false,
        delivery_date: '',
        line_notes: '',
      });
      continue;
    }
    items.forEach((item, idx) => {
      flatRows.push({
        ...header,
        ...item,
        _rowKey: item.id
          ? `qt-${quotation.id}-item-${item.id}`
          : `qt-${quotation.id}-idx-${idx}`,
        line_notes: item.notes ?? '',
      });
    });
  }
  return flatRows;
}

export function filterQuotationItemExportRowsByKeys(
  flatRows: Array<Record<string, unknown>>,
  keys: Array<string | number> | undefined,
): Array<Record<string, unknown>> {
  if (!keys?.length) return flatRows;
  const keySet = new Set(keys.map(String));
  return flatRows.filter((row) => {
    const rowKey = String(row._rowKey ?? '');
    if (keySet.has(rowKey)) return true;
    const quotationId = row.quotation_id;
    return quotationId != null && keySet.has(String(quotationId));
  });
}

export function mapQuotationItemToExportRow(
  row: Record<string, unknown>,
  ctx: QuotationExportContext,
): Record<string, unknown> {
  const { t, dictionaryLabels } = ctx;
  const versionNo = Number(row.version_no || 1);
  return {
    quotation_code: String(row.quotation_code ?? ''),
    version_no: t('app.kuaizhizao.quotation.versionDisplay', { n: versionNo }),
    lifecycle: formatLifecycleLabel(row as Quotation, ctx),
    audit_phase: formatAuditPhaseLabel(row as Quotation, t),
    customer_name: String(row.customer_name ?? ''),
    quotation_date: formatDateOnly(row.quotation_date),
    salesman_name: String(row.salesman_name ?? ''),
    price_type: formatPriceType(row.price_type, t),
    currency_code: dictLabel(dictionaryLabels.CURRENCY, row.currency_code || 'CNY'),
    material_code: String(row.material_code ?? ''),
    material_name: String(row.material_name ?? ''),
    material_spec: String(row.material_spec ?? ''),
    material_model: String(row.material_model ?? ''),
    partner_material_code: String(row.partner_material_code ?? ''),
    partner_material_name: String(row.partner_material_name ?? ''),
    material_unit: String(row.material_unit ?? ''),
    quote_quantity: formatQuantity(row.quote_quantity),
    unit_price: formatAmount(row.unit_price),
    tax_rate: row.tax_rate != null && row.tax_rate !== '' ? String(row.tax_rate) : '',
    total_amount: formatAmount(row.total_amount),
    is_gift: formatBool(row.is_gift, t),
    delivery_date: formatDateOnly(row.delivery_date),
    line_notes: String(row.line_notes ?? row.notes ?? ''),
    order_notes: String(row.order_notes ?? ''),
  };
}

export async function exportQuotationItemsXlsx(
  flatRows: Array<Record<string, unknown>>,
  fileName: string,
  ctx: QuotationExportContext,
): Promise<void> {
  const columns = buildQuotationItemExportColumns(ctx);
  const rows = flatRows.map((row) => mapQuotationItemToExportRow(row, ctx));
  await downloadRecordsAsXlsx(rows, fileName, {
    columns,
    sheetName: ctx.t('app.kuaizhizao.menu.sales-management.quotations'),
  });
}
