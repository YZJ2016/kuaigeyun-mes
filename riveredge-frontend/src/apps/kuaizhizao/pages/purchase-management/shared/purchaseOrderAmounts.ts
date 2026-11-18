/**
 * 采购订单：落库/回填专用（库内 unit_price、total_price 为未税）。
 * 行价税、头表汇总、列表/详情展示一律走 documentLineAmounts 公共契约，禁止本文件另起拆税算法。
 */
import { getCachedNumericPrecisionPlaces } from '../../../../../hooks/useNumericPrecision';
import {
  calcDocumentLineAmounts,
  computeDocumentGoodsTotals,
  mapDocumentGoodsTotalsToPurchaseHeader,
  resolveDocumentFormLineAmounts,
  resolveDocumentStoredNetGrossAmount,
  type DocumentGoodsTotals,
} from '../../../utils/documentLineAmounts';
import { purchaseFormPriceType } from './purchasePriceType';
import type { PriceTypeValue } from '../../../../../components/price-type-switch/PriceTypeSwitch';

const roundMoney = (value: number): number => {
  const places = getCachedNumericPrecisionPlaces('amount');
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
};

/**
 * 采购行库字段 total_price / total_amount 恒为未税金额。
 * resolveDocumentLineDisplayAmounts 的 item_amount 在含税价类下表示价税合计，禁止把未税库值直传（会 gross=excl、税额 0）。
 */
export function purchaseStoredExclAsFormItemAmount(
  storedExcl: unknown,
  priceType: string | PriceTypeValue,
): number | undefined {
  const pt = purchaseFormPriceType(priceType);
  if (pt !== 'tax_exclusive') return undefined;
  if (storedExcl == null || storedExcl === '') return undefined;
  const n = Number(storedExcl);
  return Number.isFinite(n) ? n : undefined;
}

/**
 * 头表 tax_rate 存小数（0.13）；行 / 入库 / 价本存百分比（13）。
 * (0,1)→小数×100；(>=1)→已是百分比。禁止 `<=1` 把百分数 1（1%）抬成 100%。
 */
export function purchaseOrderTaxRateToPercent(raw: unknown): number {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return n < 1 ? n * 100 : n;
}

export function purchaseOrderTaxRateToDecimal(percent: unknown): number {
  const n = Number(percent);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return n / 100;
}

/** 采购入库单列表/取单金额：与后端 settlement_gross / purchase_receipt_settlement_gross 同源 */
/** 入库行税率：行优先，否则头表（百分比） */
export function resolvePurchaseReceiptLineTaxPercent(
  lineTax: unknown,
  headerTax: unknown,
): number {
  const fromLine = purchaseOrderTaxRateToPercent(lineTax);
  if (fromLine > 0) return fromLine;
  return purchaseOrderTaxRateToPercent(headerTax);
}

/** 采购订单行税率：行优先，否则头表（百分比） */
export function resolvePurchaseOrderLineTaxPercent(
  item: { tax_rate?: number | null },
  headerTaxRate?: unknown,
): number {
  const lineRaw = Number(item.tax_rate);
  if (Number.isFinite(lineRaw) && lineRaw > 0) {
    return purchaseOrderTaxRateToPercent(lineRaw);
  }
  return purchaseOrderTaxRateToPercent(headerTaxRate);
}

export type PurchaseOrderLineAmountRow = {
  ordered_quantity?: number | null;
  unit_price?: number | null;
  tax_rate?: number | null;
  item_amount?: unknown;
  is_gift?: unknown;
};

/**
 * 采购订单行价税（表单 / 详情共用）：单价必须已是录入口径，再走 resolveDocumentLineDisplayAmounts。
 */
export function resolvePurchaseOrderLineAmounts(
  row: PurchaseOrderLineAmountRow,
  priceType: string,
  opts?: {
    headerTaxRate?: unknown;
  },
): { excl: number; tax: number; incl: number; taxPct: number } {
  const taxPct = resolvePurchaseOrderLineTaxPercent(row, opts?.headerTaxRate);
  return {
    ...resolveDocumentFormLineAmounts(
      {
        qty: row.ordered_quantity,
        unit_price: row.unit_price,
        tax_rate: taxPct,
        item_amount: row.item_amount,
        is_gift: row.is_gift,
      },
      purchaseFormPriceType(priceType),
    ),
    taxPct,
  };
}

export type PurchaseReceiptLineAmountRow = {
  receipt_quantity?: number | null;
  unit_price?: number | null;
  tax_rate?: number | null;
  total_amount?: unknown;
  is_gift?: unknown;
};

/**
 * 采购入库表单行价税（与采购订单 resolvePurchaseOrderLineAmounts 同源，仅数量字段为 receipt_quantity）。
 */
export function resolvePurchaseReceiptLineAmounts(
  row: PurchaseReceiptLineAmountRow,
  priceType: string,
  opts?: { headerTaxRate?: unknown },
): { excl: number; tax: number; incl: number; taxPct: number } {
  const taxPct = resolvePurchaseReceiptLineTaxPercent(row.tax_rate, opts?.headerTaxRate);
  const pt = purchaseFormPriceType(priceType);
  const itemAmount = purchaseStoredExclAsFormItemAmount(row.total_amount, pt);
  return {
    ...resolveDocumentFormLineAmounts(
      {
        qty: row.receipt_quantity,
        unit_price: row.unit_price,
        tax_rate: taxPct,
        ...(itemAmount != null ? { item_amount: itemAmount } : {}),
        is_gift: row.is_gift,
      },
      pt,
    ),
    taxPct,
  };
}

/** 详情行价税：只用录入单价正向拆分。没有录入单价时返回 null。 */
export function calcPurchaseOrderDetailLineAmounts(
  row: PurchaseOrderLineAmountRow & {
    total_price?: number | null;
    display_unit_price?: number | null;
    displayUnitPrice?: number | null;
  },
  headerTaxRate?: unknown,
  priceType: string = 'tax_inclusive',
): { excl: number; tax: number; incl: number; taxPct: number } | null {
  const pt = purchaseFormPriceType(priceType);
  const entered = readPurchaseOrderEnteredUnitPrice(row, pt);
  if (entered == null) return null;
  return resolvePurchaseOrderLineAmounts(
    { ...row, unit_price: entered },
    pt,
    { headerTaxRate },
  );
}

/** 表单提交头表货值（与 DocumentAmountSummary variant=purchase 同源） */
export function computePurchaseOrderHeaderGoodsTotals(
  items: unknown[] | undefined,
  priceType: string,
  quantityField = 'ordered_quantity',
): DocumentGoodsTotals {
  return computeDocumentGoodsTotals(items, priceType, (row) => ({
    qty: row[quantityField],
    price: row.unit_price,
    taxRate: row.tax_rate,
  }));
}

/** 保存头表字段映射 */
export function computePurchaseOrderHeaderAmountsForSave(
  items: unknown[] | undefined,
  priceType: string,
  quantityField = 'ordered_quantity',
): { total_amount: number; tax_amount: number; net_amount: number } {
  return mapDocumentGoodsTotalsToPurchaseHeader(
    computePurchaseOrderHeaderGoodsTotals(items, priceType, quantityField),
  );
}

/** 列表/详情订单金额 = net_amount（保存时与汇总区 goodsIncl 一致） */
export function resolvePurchaseOrderDisplayAmount(order: {
  net_amount?: number | null;
}): number {
  return resolveDocumentStoredNetGrossAmount(order);
}

/** 详情「含税单价」：只读 display_unit_price；缺字段显示「—」，禁止把未税 unit_price 冒充含税。 */
export function purchaseOrderDetailUnitPriceIncl(
  row: {
    unit_price?: number | null;
    display_unit_price?: number | null;
    displayUnitPrice?: number | null;
  },
  _headerTaxRate?: unknown,
  _priceType: 'tax_inclusive' | 'tax_exclusive' = 'tax_inclusive',
): number | null {
  const raw = row.display_unit_price ?? row.displayUnitPrice;
  if (raw == null || String(raw) === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/**
 * 采购入库详情「含税单价」：只读展示库内 display_unit_price（保存时写入的表单单价），禁止反算。
 */
export function purchaseReceiptDetailUnitPriceIncl(row: {
  display_unit_price?: number | null;
  displayUnitPrice?: number | null;
}): number | null {
  const raw = row.display_unit_price ?? row.displayUnitPrice;
  if (raw == null) return null;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export type PurchaseReceiptPoLineSnapshot = {
  ordered_quantity?: number | null;
  total_price?: number | null;
  unit_price?: number | null;
  tax_rate?: number | null;
  display_unit_price?: number | null;
  displayUnitPrice?: number | null;
};

export type PurchaseReceiptPoSettlementCtx = {
  priceType: 'tax_inclusive' | 'tax_exclusive';
  headerTaxRate?: unknown;
  poiById: Record<number, PurchaseReceiptPoLineSnapshot>;
};

export type PurchaseReceiptLineSettlementInput = {
  receipt_quantity?: number | null;
  unit_price?: number | null;
  display_unit_price?: number | null;
  displayUnitPrice?: number | null;
  tax_rate?: number | null;
  purchase_order_item_id?: number | null;
  total_amount?: number | null;
  settlement_excl?: number | null;
  settlement_tax?: number | null;
  settlement_gross?: number | null;
};

/**
 * 采购入库行未税/税额/价税合计。唯一公式是 calcDocumentLineAmounts。
 *
 * 含税：价税合计 = round(数量 × 录入单价)，税额 = 价税合计 − 未税。
 * 不含税：未税 = round(数量 × 单价)，税额 = round(未税 × 税率)。
 * 禁止读已落库金额、禁止按采购订单行比例改写、禁止用未税再乘税率。
 */
export function computePurchaseReceiptLineSettlementAmounts(
  row: PurchaseReceiptLineSettlementInput,
  headerTaxRate: unknown,
  priceType: string,
  poCtx?: PurchaseReceiptPoSettlementCtx | null,
): { excl: number; tax: number; incl: number; taxPct: number } {
  const taxPct = resolvePurchaseReceiptLineTaxPercent(row.tax_rate, headerTaxRate);
  const qty = Number(row.receipt_quantity) || 0;
  const displayRaw = row.display_unit_price ?? row.displayUnitPrice;
  const hasDisplay =
    displayRaw != null && String(displayRaw) !== '' && Number(displayRaw) > 0;
  if (hasDisplay) {
    const line = calcDocumentLineAmounts(
      qty,
      Number(displayRaw),
      taxPct,
      'tax_inclusive',
    );
    return { excl: line.excl, tax: line.tax, incl: line.incl, taxPct };
  }
  const unit = Number(row.unit_price) || 0;
  const line = calcDocumentLineAmounts(qty, unit, taxPct, 'tax_exclusive');
  return { excl: line.excl, tax: line.tax, incl: line.incl, taxPct };
}

/** @deprecated 用名保留；实现已并入 `computePurchaseReceiptLineSettlementAmounts` */
export function computePurchaseReceiptFormLineAmounts(
  row: PurchaseReceiptLineSettlementInput,
  headerTaxRate: unknown,
  priceType: string,
  poCtx?: PurchaseReceiptPoSettlementCtx | null,
): { excl: number; tax: number; incl: number; taxPct: number } {
  return computePurchaseReceiptLineSettlementAmounts(row, headerTaxRate, priceType, poCtx);
}

export function computePurchaseReceiptFormGoodsTotals(
  items: unknown[] | undefined,
  headerTaxRate: unknown,
  priceType: string,
  poCtx?: PurchaseReceiptPoSettlementCtx | null,
): DocumentGoodsTotals {
  const rows = Array.isArray(items) ? items : [];
  let totalQuantity = 0;
  let goodsExcl = 0;
  let taxAmount = 0;
  let goodsIncl = 0;
  for (const raw of rows) {
    const row = raw as Record<string, unknown>;
    const qty = Number(row.receipt_quantity) || 0;
    if (qty <= 0) continue;
    totalQuantity += qty;
    const line = computePurchaseReceiptLineSettlementAmounts(
      row as PurchaseReceiptLineSettlementInput,
      headerTaxRate,
      priceType,
      poCtx,
    );
    goodsExcl = roundMoney(goodsExcl + line.excl);
    taxAmount = roundMoney(taxAmount + line.tax);
    goodsIncl = roundMoney(goodsIncl + line.incl);
  }
  return { totalQuantity, goodsExcl, taxAmount, goodsIncl };
}

/** 详情/只读：行未税、税额、价税（与 computePurchaseReceiptLineSettlementAmounts 同源） */
export function calcPurchaseReceiptDetailLineAmounts(
  row: PurchaseReceiptLineSettlementInput,
  headerTaxRate?: number | null,
  priceType: string = 'tax_inclusive',
  poCtx?: PurchaseReceiptPoSettlementCtx | null,
): { excl: number; tax: number; incl: number; taxPct: number } {
  return computePurchaseReceiptLineSettlementAmounts(row, headerTaxRate, priceType, poCtx);
}

export function resolvePurchaseReceiptDisplayAmount(receipt: {
  settlement_gross?: number | null;
  settlementGross?: number | null;
  net_amount?: number | null;
  netAmount?: number | null;
}): number {
  const hasSettlement =
    receipt.settlement_gross != null || receipt.settlementGross != null;
  if (hasSettlement) {
    const settlement = Number(receipt.settlement_gross ?? receipt.settlementGross);
    if (Number.isFinite(settlement)) return settlement;
  }
  return resolveDocumentStoredNetGrossAmount({
    net_amount: receipt.net_amount ?? receipt.netAmount,
  });
}

const roundToPricePlaces = (value: number, priceDecimals?: number): number => {
  const places = priceDecimals ?? getCachedNumericPrecisionPlaces('price');
  if (!Number.isFinite(value) || !Number.isFinite(places) || places < 0) return value;
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
};

/**
 * 编辑/详情/下推读取录入单价。
 * 有 display_unit_price 则原样返回。不含税且尚未固化时，unit_price 就是录入价。
 * 含税且没有 display_unit_price 时返回 null，禁止用未税单价乘税率。
 */
export function readPurchaseOrderEnteredUnitPrice(
  line: {
    display_unit_price?: unknown;
    displayUnitPrice?: unknown;
    unit_price?: unknown;
  },
  priceType: 'tax_inclusive' | 'tax_exclusive',
): number | null {
  const display = line.display_unit_price ?? line.displayUnitPrice;
  if (display != null && display !== '') {
    const n = Number(display);
    if (Number.isFinite(n)) return n;
  }
  if (priceType === 'tax_inclusive') return null;
  if (line.unit_price == null || line.unit_price === '') return null;
  const stored = Number(line.unit_price);
  return Number.isFinite(stored) ? stored : null;
}

/** 保存落库：表单单价原样写入 display_unit_price；unit_price 仍为未税单价。 */
export function purchaseOrderFormLineToStored(
  formUnitPrice: number,
  orderedQty: number,
  taxRatePercent: number,
  priceType: 'tax_inclusive' | 'tax_exclusive',
  priceDecimals?: number,
): {
  unit_price: number;
  display_unit_price: number;
  total_price: number;
  excl: number;
  tax: number;
  incl: number;
} {
  const qty = orderedQty > 0 ? orderedQty : 0;
  const unit = Number(formUnitPrice) || 0;
  const taxRate = Number(taxRatePercent) || 0;
  const pt = priceType ?? 'tax_exclusive';
  const displayUnit = roundToPricePlaces(unit, priceDecimals);
  const line = resolvePurchaseOrderLineAmounts(
    { ordered_quantity: qty, unit_price: displayUnit, tax_rate: taxRate },
    pt,
  );
  const storedUnit =
    qty > 0
      ? roundToPricePlaces(line.excl / qty, priceDecimals)
      : pt === 'tax_inclusive' && taxRate >= 0 && displayUnit > 0
        ? roundToPricePlaces(displayUnit / (1 + taxRate / 100), priceDecimals)
        : displayUnit;
  return {
    unit_price: storedUnit,
    display_unit_price: displayUnit,
    total_price: line.excl,
    excl: line.excl,
    tax: line.tax,
    incl: line.incl,
  };
}
