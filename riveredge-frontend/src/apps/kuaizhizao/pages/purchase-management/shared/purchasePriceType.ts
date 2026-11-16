/**
 * 采购单据价类 / 默认税率（对齐销售 salesPriceType；采购默认含税）。
 */
import type { PriceTypeValue } from '../../../../../components/price-type-switch/PriceTypeSwitch';

/** 采购模块产品明细表价类默认：含税 */
export const DEFAULT_PURCHASE_PRICE_TYPE: PriceTypeValue = 'tax_inclusive';

/**
 * 采购行默认税率（百分比）。
 * 供应商主数据无独立税率字段时：优先价本/物料税率；否则用本默认（与常见增值税 13% 一致，特殊税率手改）。
 */
export const DEFAULT_PURCHASE_TAX_RATE_PERCENT = 13;

export type SupplierTaxRateSource = Record<string, unknown> | null | undefined;

/**
 * 从供应商解析默认税率（百分比）。
 * 真源：供应商价本行税率（选料时由 resolvePurchaseDocumentMaterialLinesPricing 写入）；
 * 显式税率字段若有则用；否则组织默认 13（特殊税率行内手改）。
 */
export function resolveSupplierDefaultTaxRatePercent(supplier: SupplierTaxRateSource): number {
  if (!supplier) return DEFAULT_PURCHASE_TAX_RATE_PERCENT;
  const explicit = Number(
    supplier.defaultTaxRate ??
      supplier.default_tax_rate ??
      supplier.taxRate ??
      supplier.tax_rate,
  );
  // 0 / 空视为未设置，回落组织默认 13%（与价本→物料→13% 链一致）
  if (Number.isFinite(explicit) && explicit > 0 && explicit <= 100) {
    return explicit;
  }
  return DEFAULT_PURCHASE_TAX_RATE_PERCENT;
}

/** 持久化/API 价类归一（未赋值时默认含税） */
export function normalizePurchasePriceType(value: unknown): PriceTypeValue {
  if (value === 'tax_inclusive' || value === 'tax_exclusive') return value;
  return DEFAULT_PURCHASE_PRICE_TYPE;
}

/** 表单读取价类时的 fallback（未赋值时默认含税） */
export function purchaseFormPriceType(value: unknown): PriceTypeValue {
  return normalizePurchasePriceType(value);
}
