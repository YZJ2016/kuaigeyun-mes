/**
 * 销售侧仓储/出库等明细行价税：与采购 purchaseOrderAmounts 对称，真源 documentLineAmounts。
 */
import {
  resolveDocumentLineDisplayAmounts,
} from '../../../utils/documentLineAmounts';
import { salesFormPriceType } from './salesPriceType';
import { purchaseOrderTaxRateToPercent } from '../../purchase-management/shared/purchaseOrderAmounts';

export type SalesWarehouseLineAmountRow = {
  delivery_quantity?: number | null;
  unit_price?: number | null;
  tax_rate?: number | null;
  item_amount?: unknown;
  is_gift?: unknown;
};

export function resolveSalesWarehouseLineAmounts(
  row: SalesWarehouseLineAmountRow,
  priceType: string,
  opts?: { headerTaxRate?: unknown },
): { excl: number; tax: number; incl: number; taxPct: number } {
  const lineTax = row.tax_rate;
  const headerTax = opts?.headerTaxRate;
  const fromLine = purchaseOrderTaxRateToPercent(lineTax);
  const taxPct =
    fromLine > 0 ? fromLine : purchaseOrderTaxRateToPercent(headerTax);
  const pt = salesFormPriceType(priceType);
  const line = resolveDocumentLineDisplayAmounts(
    {
      qty: row.delivery_quantity,
      unit_price: row.unit_price,
      tax_rate: taxPct,
      item_amount: row.item_amount,
      is_gift: row.is_gift,
    },
    pt,
  );
  return { ...line, taxPct };
}
