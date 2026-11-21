/**
 * 出入库 Hub / 详情抽屉 — 明细行只读列（仓/位/批/序 + tracking 过滤）
 */

import type { ReactNode } from 'react';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import { formatCurrencyAmount, formatCurrencyPrice, formatQuantity } from '../../../../../utils/format';
import { purchaseReceiptDetailUnitPriceIncl } from '../../purchase-management/shared/purchaseOrderAmounts';
import { readPurchaseReceiptDetailLineAmounts } from './purchaseReceiptWarehouseAmounts';
import {
  buildDocumentLineAttachmentsDrawerColumn,
  DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY,
} from '../../../components/documentLineAttachmentsColumns';
import {
  appendWarehouseLineAmountColumns,
  KUAIZHIZAO_INBOUND_FIELD_RESOURCE,
  KUAIZHIZAO_OUTBOUND_FIELD_RESOURCE,
} from './warehouseAmountDisplay';
import { filterWarehouseTrackingColumns, type WarehouseTrackingFlags } from './warehouseTrackingFlags';
import type { InboundReceiptType } from '../inbound/inboundHubTypes';
import { resolveInboundHubLineQuantity } from '../inbound/inboundHubNormalize';
import type { OutboundIssueType } from '../outbound/outboundHubTypes';

const dash = (v: unknown) => (v != null && String(v).trim() ? String(v) : '—');

export function renderInboundDetailSerialCell(
  t: TFunction,
  val: unknown,
): string {
  if (!Array.isArray(val) || val.length === 0) return '—';
  return t('app.kuaizhizao.warehouseInbound.detail.serialCount', { count: val.length });
}

export function parseOutboundLineSerialNumbers(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((x) => String(x).trim()).filter(Boolean);
  if (typeof raw === 'string' && raw.trim()) {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) {
        return parsed.map((x) => String(x).trim()).filter(Boolean);
      }
    } catch {
      /* ignore */
    }
  }
  return [];
}

export function buildInboundDetailMaterialCols(t: TFunction) {
  return [
    {
      title: t('app.kuaizhizao.warehouseInbound.col.materialCode'),
      dataIndex: 'material_code',
      width: 120,
      ellipsis: true,
    },
    {
      title: t('app.kuaizhizao.warehouseInbound.col.materialName'),
      dataIndex: 'material_name',
      width: 150,
      ellipsis: true,
    },
    {
      title: t('app.kuaizhizao.warehouseInbound.col.spec'),
      dataIndex: 'material_spec',
      width: 120,
      ellipsis: true,
      render: (v: unknown) => dash(v),
    },
    {
      title: t('app.kuaizhizao.warehouseInbound.col.model'),
      dataIndex: 'material_model',
      width: 100,
      ellipsis: true,
      render: (v: unknown) => dash(v),
    },
  ];
}

export type InboundHubDetailLineRow = Record<string, unknown> & {
  material_unit?: string;
  unit?: string;
  receipt_quantity?: number;
  return_quantity?: number;
};

export type BuildInboundHubDetailLineColumnsOptions = {
  t: TFunction;
  receiptType: InboundReceiptType | undefined;
  trackingFlags: WarehouseTrackingFlags;
  showAmount: boolean;
  /** 字段权限资源键；默认 kuaizhizao:inbound */
  fieldResource?: string;
  /** 采购入库详情：行价税拆分与头表税率回退 */
  purchaseHeaderTaxRate?: number | null;
  renderUnitCell: (row: InboundHubDetailLineRow) => ReactNode;
  renderLineQuantity?: (qty: unknown, unit?: string) => React.ReactNode;
};

export function buildPurchaseReceiptDetailFinanceColumns(
  t: TFunction,
  headerTaxRate?: number | null,
): ColumnsType<InboundHubDetailLineRow> {
  return [
    {
      title: t('app.kuaizhizao.purchaseOrder.col.taxUnitPrice'),
      key: 'purchase_line_unit_incl',
      width: 104,
      align: 'right' as const,
      render: (_: unknown, row) => {
        const listUnit = purchaseReceiptDetailUnitPriceIncl(row);
        return listUnit != null ? formatCurrencyPrice(listUnit) : '—';
      },
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.taxRate'),
      key: 'purchase_line_tax_rate',
      width: 72,
      align: 'right' as const,
      render: (_: unknown, row) => {
        const amounts = readPurchaseReceiptDetailLineAmounts(row, headerTaxRate);
        const taxPct =
          amounts?.taxPct ??
          (row.tax_rate != null && Number(row.tax_rate) > 0 ? Number(row.tax_rate) : 0);
        return taxPct > 0 ? `${taxPct}%` : '—';
      },
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.exclAmount'),
      key: 'purchase_line_excl',
      width: 112,
      align: 'right' as const,
      render: (_: unknown, row) => {
        const amounts = readPurchaseReceiptDetailLineAmounts(row, headerTaxRate);
        return amounts != null && amounts.excl > 0 ? formatCurrencyAmount(amounts.excl) : '—';
      },
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.taxAmount'),
      key: 'purchase_line_tax',
      width: 104,
      align: 'right' as const,
      render: (_: unknown, row) => {
        const amounts = readPurchaseReceiptDetailLineAmounts(row, headerTaxRate);
        return amounts != null && (amounts.excl > 0 || amounts.tax > 0)
          ? formatCurrencyAmount(amounts.tax)
          : '—';
      },
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.inclTotal'),
      key: 'purchase_line_incl',
      width: 112,
      align: 'right' as const,
      render: (_: unknown, row) => {
        const amounts = readPurchaseReceiptDetailLineAmounts(row, headerTaxRate);
        return amounts != null && (amounts.excl > 0 || amounts.incl > 0)
          ? formatCurrencyAmount(amounts.incl)
          : '—';
      },
    },
  ];
}

function inboundTrackingTailCols(t: TFunction): ColumnsType<InboundHubDetailLineRow> {
  return [
    {
      title: t('app.kuaizhizao.warehouseInbound.col.warehouseName'),
      dataIndex: 'warehouse_name',
      width: 120,
      ellipsis: true,
      render: (v: unknown) => dash(v),
    },
    {
      title: t('app.kuaizhizao.warehouseInbound.col.locationCode'),
      dataIndex: 'location_code',
      width: 100,
      ellipsis: true,
      render: (v: unknown) => dash(v),
    },
    {
      title: t('app.kuaizhizao.warehouseInbound.col.batchNumber'),
      dataIndex: 'batch_number',
      width: 100,
      ellipsis: true,
      render: (v: unknown) => dash(v),
    },
    {
      title: t('app.kuaizhizao.warehouseInbound.col.serialNo'),
      dataIndex: 'serial_numbers',
      width: 88,
      render: (v: unknown) => renderInboundDetailSerialCell(t, v),
    },
  ];
}

export function buildInboundHubDetailLineColumns(
  options: BuildInboundHubDetailLineColumnsOptions,
): ColumnsType<InboundHubDetailLineRow> {
  const {
    t,
    receiptType,
    trackingFlags,
    showAmount,
    purchaseHeaderTaxRate,
    renderUnitCell,
    renderLineQuantity,
    fieldResource = KUAIZHIZAO_INBOUND_FIELD_RESOURCE,
  } = options;
  const materialCols = buildInboundDetailMaterialCols(t);
  const qtyRender =
    renderLineQuantity ??
    ((qty: unknown, unit?: string) => formatQuantity(qty as number | undefined) + (unit ? '' : ''));

  const withTracking = (cols: ColumnsType<InboundHubDetailLineRow>, amountOffset = 0) =>
    appendWarehouseLineAmountColumns(
      filterWarehouseTrackingColumns([...cols, ...inboundTrackingTailCols(t)], trackingFlags),
      t,
      showAmount,
      fieldResource,
      amountOffset,
    );

  if (receiptType === 'production_return') {
    return withTracking([
      ...materialCols,
      {
        title: t('common.unit'),
        dataIndex: 'material_unit',
        width: 72,
        render: (_: unknown, row) => renderUnitCell(row),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.returnQty'),
        dataIndex: 'return_quantity',
        width: 120,
        align: 'right' as const,
        render: (_: unknown, row) =>
          qtyRender(row.return_quantity, String(row.material_unit ?? row.unit ?? '')),
      },
    ]);
  }

  if (receiptType === 'purchase') {
    return withTracking(
      [
        ...materialCols,
        {
          title: t('app.kuaizhizao.warehouseInbound.col.actualQty'),
          dataIndex: 'receipt_quantity',
          width: 112,
          align: 'right' as const,
          render: (_: unknown, row) => formatQuantity(row.receipt_quantity),
        },
        {
          title: t('common.unit'),
          dataIndex: 'material_unit',
          width: 72,
          render: (_: unknown, row) => renderUnitCell(row),
        },
        ...buildPurchaseReceiptDetailFinanceColumns(t, purchaseHeaderTaxRate),
        buildDocumentLineAttachmentsDrawerColumn(
          t,
          DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.purchaseReceipt,
        ),
      ],
      -3,
    );
  }

  if (receiptType === 'outsource_receipt') {
    return appendWarehouseLineAmountColumns(
      filterWarehouseTrackingColumns(
        [
          ...materialCols,
          {
            title: t('app.kuaizhizao.warehouseInbound.col.thisReceiptOutsource'),
            dataIndex: 'receipt_quantity',
            width: 100,
            align: 'right' as const,
            render: (_: unknown, row) => formatQuantity(row.receipt_quantity),
          },
          {
            title: t('app.kuaizhizao.warehouseInbound.col.qualified'),
            dataIndex: 'qualified_quantity',
            width: 88,
            align: 'right' as const,
            render: (v: unknown) => formatQuantity(v),
          },
          {
            title: t('app.kuaizhizao.warehouseInbound.col.unqualified'),
            dataIndex: 'unqualified_quantity',
            width: 88,
            align: 'right' as const,
            render: (v: unknown) => formatQuantity(v),
          },
          {
            title: t('app.kuaizhizao.warehouseInbound.col.processWaste'),
            dataIndex: 'process_waste_qty',
            width: 72,
            align: 'right' as const,
            render: (v: unknown) => formatQuantity(v),
          },
          {
            title: t('app.kuaizhizao.warehouseInbound.col.materialWaste'),
            dataIndex: 'material_waste_qty',
            width: 72,
            align: 'right' as const,
            render: (v: unknown) => formatQuantity(v),
          },
          {
            title: t('common.unit'),
            dataIndex: 'material_unit',
            width: 72,
            render: (_: unknown, row) => renderUnitCell(row),
          },
          ...inboundTrackingTailCols(t),
        ],
        trackingFlags,
      ),
      t,
      showAmount,
      fieldResource,
    );
  }

  return withTracking([
    ...materialCols,
    {
      title: t('common.quantity'),
      dataIndex: 'receipt_quantity',
      width: 100,
      align: 'right' as const,
      render: (_: unknown, row) =>
        formatQuantity(resolveInboundHubLineQuantity(row as Record<string, unknown>)),
    },
    {
      title: t('common.unit'),
      dataIndex: 'material_unit',
      width: 72,
      render: (_: unknown, row) => renderUnitCell(row),
    },
  ]);
}

export type BuildOutboundHubDetailLineColumnsOptions = {
  t: TFunction;
  outboundType: OutboundIssueType | undefined;
  trackingFlags: WarehouseTrackingFlags;
  showAmount: boolean;
  /** 字段权限资源键；默认 kuaizhizao:outbound */
  fieldResource?: string;
};

function outboundTrackingTailCols(t: TFunction): ColumnsType<Record<string, unknown>> {
  return [
    {
      title: t('app.kuaizhizao.warehouseOutbound.col.warehouseName'),
      dataIndex: 'warehouse_name',
      width: 120,
      ellipsis: true,
      render: (v: unknown) => dash(v),
    },
    {
      title: t('app.kuaizhizao.warehouseOutbound.col.locationCode'),
      dataIndex: 'location_code',
      width: 100,
      ellipsis: true,
      render: (v: unknown, row) => dash(v ?? row.location_id),
    },
    {
      title: t('app.kuaizhizao.warehouseOutbound.col.batchNo'),
      dataIndex: 'batch_number',
      width: 100,
      render: (v: unknown) => dash(v),
    },
    {
      title: t('app.kuaizhizao.warehouseOutbound.col.serialNo'),
      dataIndex: 'serial_numbers',
      width: 120,
      render: (_: unknown, row) => {
        const serials = parseOutboundLineSerialNumbers(row.serial_numbers);
        return serials.length ? serials.join(', ') : '—';
      },
    },
  ];
}

export function buildOutboundHubDetailLineColumns(
  options: BuildOutboundHubDetailLineColumnsOptions,
): ColumnsType<Record<string, unknown>> {
  const {
    t,
    outboundType,
    trackingFlags,
    showAmount,
    fieldResource = KUAIZHIZAO_OUTBOUND_FIELD_RESOURCE,
  } = options;
  const tail = filterWarehouseTrackingColumns(outboundTrackingTailCols(t), trackingFlags);

  if (outboundType === 'production_picking') {
    return [
      { title: t('app.kuaizhizao.warehouseOutbound.col.materialCode'), dataIndex: 'material_code', width: 120 },
      { title: t('app.kuaizhizao.warehouseOutbound.col.materialName'), dataIndex: 'material_name', width: 150 },
      {
        title: t('app.kuaizhizao.warehouseCommon.colSpec'),
        dataIndex: 'material_spec',
        width: 120,
        ellipsis: true,
        render: (v: unknown) => dash(v),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.model'),
        dataIndex: 'material_model',
        width: 100,
        ellipsis: true,
        render: (v: unknown) => dash(v),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.requiredQty'),
        dataIndex: 'required_quantity',
        width: 100,
        align: 'right' as const,
        render: (_: unknown, row) => formatQuantity(row.required_quantity as number | undefined),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.pickedQty'),
        dataIndex: 'picked_quantity',
        width: 100,
        align: 'right' as const,
        render: (_: unknown, row) => formatQuantity(row.picked_quantity as number | undefined),
      },
      { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
      ...tail,
    ];
  }

  if (outboundType === 'sales_delivery') {
    const withAmount = appendWarehouseLineAmountColumns(
      filterWarehouseTrackingColumns(
        [
          { title: t('app.kuaizhizao.warehouseOutbound.col.materialCode'), dataIndex: 'material_code', width: 120 },
          { title: t('app.kuaizhizao.warehouseOutbound.col.materialName'), dataIndex: 'material_name', width: 150 },
          {
            title: t('app.kuaizhizao.warehouseOutbound.col.deliveryQty'),
            dataIndex: 'delivery_quantity',
            width: 100,
            align: 'right' as const,
            render: (_: unknown, row) => formatQuantity(row.delivery_quantity as number | undefined),
          },
          { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
          ...tail,
          { title: t('common.remark'), dataIndex: 'notes' },
          buildDocumentLineAttachmentsDrawerColumn(
            t,
            DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.salesDelivery,
          ),
        ],
        trackingFlags,
      ),
      t,
      showAmount,
      fieldResource,
      -2,
    );
    if (showAmount) {
      const priceIdx = withAmount.findIndex((col) => col.dataIndex === 'unit_price');
      const taxCol = {
        title: t('app.kuaizhizao.salesOrder.taxRate'),
        dataIndex: 'tax_rate',
        width: 80,
        align: 'right' as const,
      };
      if (priceIdx >= 0) {
        withAmount.splice(priceIdx, 0, taxCol);
      } else {
        withAmount.push(taxCol);
      }
    }
    return withAmount;
  }

  return filterWarehouseTrackingColumns(
    [
      { title: t('app.kuaizhizao.warehouseOutbound.col.materialCode'), dataIndex: 'material_code', width: 120 },
      { title: t('app.kuaizhizao.warehouseOutbound.col.materialName'), dataIndex: 'material_name', width: 150 },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.deliveryQty'),
        key: 'qty',
        width: 100,
        align: 'right' as const,
        render: (_: unknown, row) =>
          formatQuantity(
            (row.delivery_quantity ??
              row.picked_quantity ??
              row.outbound_quantity ??
              row.borrow_quantity ??
              row.quantity) as number | undefined,
          ),
      },
      { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
      ...tail,
    ],
    trackingFlags,
  );
}

export const INBOUND_DETAIL_ITEMS_MIN_WIDTH = 2080;
