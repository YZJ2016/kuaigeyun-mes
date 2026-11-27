import type { Dispatch, SetStateAction } from 'react';
import type { TableColumnsType } from 'antd';
import { Input, InputNumber } from 'antd';
import type { TFunction } from 'i18next';
import type { PullReceiptFinanceDetailLine } from '../../../../kuaizhizao/utils/pullReceiptFinanceLines';
import {
  deriveInvoiceQtyFromLineAmount,
  deriveLineInclFromInvoiceQty,
  sumPullReceiptLineAmounts,
} from '../../../../kuaizhizao/utils/pullReceiptFinanceLines';

const P = 'app.kuaicaiwu.salesInvoice';
const PAGE = 'app.kuaicaiwu.salesDetailInvoice';

export type BuildSalesDetailPullLineColumnsArgs = {
  t: TFunction;
  pullReceiptSelectedIds: number[];
  pullReceiptLineAmounts: Record<number, number>;
  setPullReceiptLineAmounts: Dispatch<SetStateAction<Record<number, number>>>;
  pullReceiptLineQuantities: Record<number, number>;
  setPullReceiptLineQuantities: Dispatch<SetStateAction<Record<number, number>>>;
  pullReceiptLineInvoiceNumbers: Record<number, string>;
  setPullReceiptLineInvoiceNumbers: Dispatch<SetStateAction<Record<number, string>>>;
  headerInvoiceNumber: string;
  syncPullReceiptSumToInvoiceForm: (sumIncl: number) => void;
  formatMoney: (value: number) => string;
  formatPercent: (rate?: number) => string;
  formatQty: (qty?: number) => string;
};

function resolveRowInvoiceQty(
  row: PullReceiptFinanceDetailLine,
  id: number,
  incl: number,
  pullReceiptLineQuantities: Record<number, number>,
): number {
  const explicit = pullReceiptLineQuantities[id];
  if (explicit != null && Number(explicit) >= 0) {
    return Number(explicit);
  }
  return deriveInvoiceQtyFromLineAmount(row, incl);
}

export function buildSalesDetailInvoicePullLineColumns(
  args: BuildSalesDetailPullLineColumnsArgs,
): TableColumnsType<PullReceiptFinanceDetailLine> {
  const {
    t,
    pullReceiptSelectedIds,
    pullReceiptLineAmounts,
    setPullReceiptLineAmounts,
    pullReceiptLineQuantities,
    setPullReceiptLineQuantities,
    pullReceiptLineInvoiceNumbers,
    setPullReceiptLineInvoiceNumbers,
    headerInvoiceNumber,
    syncPullReceiptSumToInvoiceForm,
    formatMoney,
    formatPercent,
    formatQty,
  } = args;

  return [
    {
      title: t(`${PAGE}.pull.col.sourceDocCode`),
      dataIndex: 'source_doc_code',
      width: 148,
      ellipsis: true,
      fixed: 'left',
    },
    {
      title: t(`${PAGE}.pull.col.lineInvoiceNumber`),
      width: 120,
      ellipsis: true,
      render: (_: unknown, row: PullReceiptFinanceDetailLine) => {
        const id = row.purchase_receipt_item_id;
        if (!pullReceiptSelectedIds.includes(id)) {
          return '—';
        }
        const value = pullReceiptLineInvoiceNumbers[id] ?? headerInvoiceNumber ?? '';
        return (
          <Input
            size="small"
            value={value}
            maxLength={100}
            onChange={(e) => {
              setPullReceiptLineInvoiceNumbers((prev) => ({ ...prev, [id]: e.target.value }));
            }}
          />
        );
      },
    },
    {
      title: t(`${P}.pull.col.materialCode`),
      dataIndex: 'material_code',
      width: 112,
      ellipsis: true,
    },
    {
      title: t(`${P}.pull.col.materialName`),
      dataIndex: 'material_name',
      width: 128,
      ellipsis: true,
    },
    {
      title: t(`${P}.pull.col.materialSpec`),
      dataIndex: 'material_spec',
      width: 96,
      ellipsis: true,
      render: (v: string | null | undefined) => (v ? String(v) : '—'),
    },
    {
      title: t(`${PAGE}.pull.col.sourceQuantity`),
      dataIndex: 'quantity',
      width: 88,
      align: 'right',
      render: (v: number) => formatQty(v),
    },
    {
      title: t(`${PAGE}.pull.col.receivableQuantity`),
      dataIndex: 'max_push_quantity',
      width: 88,
      align: 'right',
      render: (v: number) => formatQty(v),
    },
    {
      title: t(`${PAGE}.pull.col.invoiceQuantity`),
      width: 104,
      align: 'right',
      render: (_, row) => {
        const id = row.purchase_receipt_item_id;
        const selected = pullReceiptSelectedIds.includes(id);
        const cap = Number(row.max_push_amount ?? 0);
        const maxQty = Number(row.max_push_quantity ?? row.quantity ?? 0);
        const incl = Number(pullReceiptLineAmounts[id] ?? 0);
        const qty = resolveRowInvoiceQty(row, id, incl, pullReceiptLineQuantities);
        return (
          <InputNumber
            size="small"
            min={0}
            max={maxQty > 0 ? maxQty : undefined}
            precision={4}
            disabled={!selected || cap <= 0}
            value={selected && incl > 0 ? qty : undefined}
            onChange={(val) => {
              const nextQty = Number(val ?? 0);
              const nextIncl = deriveLineInclFromInvoiceQty(row, nextQty);
              setPullReceiptLineQuantities((prev) => ({ ...prev, [id]: nextQty }));
              setPullReceiptLineAmounts((prev) => {
                const merged = { ...prev, [id]: nextIncl };
                const sum = sumPullReceiptLineAmounts(pullReceiptSelectedIds, merged);
                syncPullReceiptSumToInvoiceForm(sum);
                return merged;
              });
            }}
            style={{ width: '100%' }}
          />
        );
      },
    },
    {
      title: t(`${PAGE}.pull.col.sourceUnitPrice`),
      dataIndex: 'unit_price',
      width: 96,
      align: 'right',
      render: (v: number) => formatMoney(v),
    },
    {
      title: t(`${PAGE}.pull.col.invoiceUnitPrice`),
      width: 96,
      align: 'right',
      render: (_, row) => {
        const id = row.purchase_receipt_item_id;
        const incl = Number(pullReceiptLineAmounts[id] ?? 0);
        const qty = resolveRowInvoiceQty(row, id, incl, pullReceiptLineQuantities);
        if (!(qty > 0) || !(incl > 0)) return '—';
        return formatMoney(incl / qty);
      },
    },
    {
      title: t(`${PAGE}.pull.col.thisInvoiceAmount`),
      width: 120,
      align: 'right',
      render: (_, row) => {
        const id = row.purchase_receipt_item_id;
        const selected = pullReceiptSelectedIds.includes(id);
        const cap = Number(row.max_push_amount ?? 0);
        return (
          <InputNumber
            size="small"
            min={0}
            max={cap}
            precision={2}
            disabled={!selected || cap <= 0}
            value={pullReceiptLineAmounts[id]}
            onChange={(val) => {
              const next = Number(val ?? 0);
              const nextQty = deriveInvoiceQtyFromLineAmount(row, next);
              setPullReceiptLineAmounts((prev) => {
                const merged = { ...prev, [id]: next };
                const sum = sumPullReceiptLineAmounts(pullReceiptSelectedIds, merged);
                syncPullReceiptSumToInvoiceForm(sum);
                return merged;
              });
              setPullReceiptLineQuantities((prev) => ({ ...prev, [id]: nextQty }));
            }}
            style={{ width: '100%' }}
          />
        );
      },
    },
    {
      title: t(`${PAGE}.pull.col.sourceGrossAmount`),
      dataIndex: 'gross_amount',
      width: 104,
      align: 'right',
      render: (v: number | undefined) => formatMoney(Number(v ?? 0)),
    },
    {
      title: t(`${PAGE}.pull.col.receivableAmount`),
      dataIndex: 'max_push_amount',
      width: 104,
      align: 'right',
      render: (v: number) => formatMoney(v),
    },
    {
      title: t(`${P}.pull.col.occupiedAmount`),
      dataIndex: 'occupied_amount',
      width: 96,
      align: 'right',
      render: (v: number) => formatMoney(v),
    },
    {
      title: t(`${P}.col.taxRate`),
      dataIndex: 'tax_rate',
      width: 72,
      align: 'right',
      render: (v: number | undefined) => formatPercent(v),
    },
    {
      title: t(`${PAGE}.pull.col.warehouse`),
      dataIndex: 'warehouse_name',
      width: 96,
      ellipsis: true,
    },
    {
      title: t(`${PAGE}.pull.col.location`),
      dataIndex: 'location_code',
      width: 88,
      ellipsis: true,
    },
    {
      title: t(`${PAGE}.pull.col.batchNumber`),
      dataIndex: 'batch_number',
      width: 96,
      ellipsis: true,
    },
  ];
}