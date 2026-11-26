import dayjs from 'dayjs';
import { message } from 'antd';
import { formatDateTime, todaySiteDateString } from '../../../utils/format';
import { getApiErrorMessage } from '../../../utils/errorHandler';
import type { Material } from '../types/material';
import { materialApi } from '../services/material';
import { materialMarketPriceApi } from '../services/material-market-price';
import { customerPriceBookApi, supplierPriceBookApi } from '../services/partner-price-book';
import type { PartnerPriceResolveResult } from '../types/partner-price-book';
import { parseVariantAttributesValue } from '../components/VariantAttributeFields';
import { normalizeFormListItems } from '../../../utils/formListItems';
import {
  clearDocumentLineUnitPriceLock,
  isDocumentLineUnitPriceLocked,
} from '../../kuaizhizao/utils/documentLinePriceLock';
import {
  readDocumentLineQuantityForStoredAmount,
  recalcDocumentStoredLineAmount,
} from '../../kuaizhizao/utils/documentLineAmounts';
import { getCachedNumericPrecisionPlaces } from '../../../hooks/useNumericPrecision';
import { quantizeNumericByPlaces } from '../../../services/businessConfig';

type FormWithLineItems = {
  getFieldValue: (name: string | (string | number)[]) => unknown;
  setFieldsValue: (values: Record<string, unknown>) => void;
  setFieldValue?: (name: string | (string | number)[], value: unknown) => void;
};

/** Form.List 行内快照字段：getFieldValue('items') 常缺嵌套 setFieldValue 写入项，禁止用 setFieldsValue({ items }) 冲掉 */
const DOCUMENT_LINE_SNAPSHOT_FIELDS = [
  'material_code',
  'material_name',
  'material_spec',
  'material_model',
  'partner_material_code',
  'partner_material_name',
] as const;

function mergeFormListLineFromFieldStore(
  form: FormWithLineItems,
  listName: string,
  index: number,
  row: Record<string, unknown>,
): Record<string, unknown> {
  const merged = { ...row };
  for (const field of DOCUMENT_LINE_SNAPSHOT_FIELDS) {
    const stored = form.getFieldValue([listName, index, field]);
    if (stored !== undefined) {
      merged[field] = stored;
    }
  }
  return merged;
}

function readMaterialTextField(obj: Record<string, unknown>, key: string): string {
  const camel = obj[key];
  if (camel != null && String(camel).trim()) return String(camel).trim();
  const snake = key.replace(/([A-Z])/g, '_$1').toLowerCase();
  const snakeVal = obj[snake];
  if (snakeVal != null && String(snakeVal).trim()) return String(snakeVal).trim();
  return '';
}

/** 引用展示/列表常缺型号，选料写行快照前按需拉物料详情 */
async function ensureMaterialMasterSnapshot(
  material: Material | Record<string, unknown>,
): Promise<Material | Record<string, unknown>> {
  const uuid = String((material as Record<string, unknown>).uuid ?? '').trim();
  if (!uuid) return material;
  const spec = readMaterialTextField(material as Record<string, unknown>, 'specification');
  const model = readMaterialTextField(material as Record<string, unknown>, 'model');
  if (spec && model) return material;
  try {
    return await materialApi.get(uuid);
  } catch {
    return material;
  }
}

function pickNumberField(
  obj: Record<string, unknown> | null | undefined,
  ...keys: string[]
): number | undefined {
  if (!obj) return undefined;
  for (const key of keys) {
    const val = obj[key];
    if (val != null && val !== '') {
      const n = Number(val);
      if (!Number.isNaN(n)) return n;
    }
  }
  return undefined;
}

export function getMaterialDefaultSalePrice(material: Material | Record<string, unknown>): number {
  const defaults = (material as any).defaults ?? {};
  const sales = defaults.sales ?? defaults.Sales;
  const fromSales =
    sales && typeof sales === 'object'
      ? Number(
          (sales as Record<string, unknown>).defaultSalePrice ??
            (sales as Record<string, unknown>).default_sale_price ??
            (sales as Record<string, unknown>).standard_price,
        ) || 0
      : 0;
  const raw =
    fromSales ||
    Number(
      defaults.defaultSalePrice ??
        defaults.default_sale_price ??
        (material as any).defaultSalePrice ??
        (material as any).default_sale_price,
    ) ||
    0;
  if (raw <= 0) return 0;

  const priceTypeRaw =
    (sales && typeof sales === 'object'
      ? (sales as Record<string, unknown>).defaultSalePriceType ??
        (sales as Record<string, unknown>).default_sale_price_type
      : undefined) ??
    defaults.defaultSalePriceType ??
    defaults.default_sale_price_type ??
    'tax_inclusive';
  const priceType = priceTypeRaw === 'tax_exclusive' ? 'tax_exclusive' : 'tax_inclusive';
  if (priceType === 'tax_inclusive') {
    const taxRate = getMaterialDefaultTaxRate(material);
    return convertUnitPriceByPriceType(raw, taxRate, 'tax_inclusive', 'tax_exclusive');
  }
  return raw;
}

export function getMaterialDefaultPurchasePrice(material: Material | Record<string, unknown>): number {
  const defaults = (material as any).defaults ?? {};
  const purchase = defaults.purchase ?? defaults.Purchase ?? {};
  const fromPurchase =
    purchase && typeof purchase === 'object'
      ? Number(
          (purchase as Record<string, unknown>).standard_price ??
            (purchase as Record<string, unknown>).purchase_price ??
            (purchase as Record<string, unknown>).defaultPurchasePrice ??
            (purchase as Record<string, unknown>).default_purchase_price,
        ) || 0
      : 0;
  const raw =
    fromPurchase ||
    Number(
      defaults.defaultPurchasePrice ??
        defaults.default_purchase_price ??
        (material as any).source_config?.purchase_price ??
        (material as any).sourceConfig?.purchase_price,
    ) ||
    0;
  if (raw <= 0) return 0;

  const priceTypeRaw =
    (purchase && typeof purchase === 'object'
      ? (purchase as Record<string, unknown>).defaultPurchasePriceType ??
        (purchase as Record<string, unknown>).default_purchase_price_type
      : undefined) ??
    defaults.defaultPurchasePriceType ??
    defaults.default_purchase_price_type ??
    'tax_inclusive';
  const priceType = priceTypeRaw === 'tax_exclusive' ? 'tax_exclusive' : 'tax_inclusive';
  if (priceType === 'tax_inclusive') {
    const taxRate = getMaterialDefaultTaxRate(material);
    return convertUnitPriceByPriceType(raw, taxRate, 'tax_inclusive', 'tax_exclusive');
  }
  return raw;
}

export function getMaterialSalePriceMethod(
  material: Material | Record<string, unknown>,
): 'fixed' | 'market' | 'tier' {
  const defaults = (material as any).defaults ?? {};
  const raw = defaults.salePriceMethod ?? defaults.sale_price_method;
  if (raw === 'market') return 'market';
  if (raw === 'tier') return 'tier';
  return 'fixed';
}

export function getMaterialPurchasePriceMethod(
  material: Material | Record<string, unknown>,
): 'fixed' | 'tier' {
  const defaults = (material as any).defaults ?? {};
  const raw = defaults.purchasePriceMethod ?? defaults.purchase_price_method;
  return raw === 'tier' ? 'tier' : 'fixed';
}

function readMaterialPurchaseTierPrices(material: Material | Record<string, unknown>): unknown[] {
  const defaults = (material as any).defaults ?? {};
  const purchase = defaults.purchase ?? defaults.Purchase ?? {};
  const tierRaw =
    purchase.tier_prices ??
    purchase.tierPrices ??
    defaults.purchaseTierPrices ??
    defaults.purchase_tier_prices;
  return Array.isArray(tierRaw) ? tierRaw : [];
}

function readMaterialSaleTierPrices(material: Material | Record<string, unknown>): unknown[] {
  const defaults = (material as any).defaults ?? {};
  const sales = defaults.sales ?? defaults.Sales ?? {};
  const tierRaw =
    sales.tier_prices ??
    sales.tierPrices ??
    defaults.saleTierPrices ??
    defaults.sale_tier_prices;
  return Array.isArray(tierRaw) ? tierRaw : [];
}

/** 物料主数据已启用「阶梯采购价」且维护了至少一档阶梯 */
export function materialHasPurchaseQuantityTierPricing(
  material: Material | Record<string, unknown>,
): boolean {
  if (getMaterialPurchasePriceMethod(material) !== 'tier') return false;
  return readMaterialPurchaseTierPrices(material).length > 0;
}

/** 物料主数据已启用「阶梯销售价」且维护了至少一档阶梯 */
export function materialHasSaleQuantityTierPricing(
  material: Material | Record<string, unknown>,
): boolean {
  if (getMaterialSalePriceMethod(material) !== 'tier') return false;
  return readMaterialSaleTierPrices(material).length > 0;
}

async function supplierPriceBookHasQuantityTierPricing(
  supplierId: number,
  materialId: number,
  asOf?: string,
): Promise<boolean> {
  try {
    const res = await supplierPriceBookApi.list({
      partnerId: supplierId,
      materialId,
      activeOnly: true,
      effectiveOn: asOf,
      limit: 50,
    });
    for (const row of res.data ?? []) {
      const tiers = row.tierPrices ?? (row as Record<string, unknown>).tier_prices;
      if (Array.isArray(tiers) && tiers.length > 0) return true;
    }
  } catch {
    return false;
  }
  return false;
}

async function customerPriceBookHasQuantityTierPricing(
  customerId: number,
  materialId: number,
  asOf?: string,
): Promise<boolean> {
  try {
    const res = await customerPriceBookApi.list({
      partnerId: customerId,
      materialId,
      activeOnly: true,
      effectiveOn: asOf,
      limit: 50,
    });
    for (const row of res.data ?? []) {
      const tiers = row.tierPrices ?? (row as Record<string, unknown>).tier_prices;
      if (Array.isArray(tiers) && tiers.length > 0) return true;
    }
  } catch {
    return false;
  }
  return false;
}

/** 改数量时是否应按数量重算采购单价（仅阶梯价场景） */
export async function purchaseLineQuantityChangeShouldReprice(
  material: Material | Record<string, unknown>,
  options?: { supplierId?: number; asOf?: string },
): Promise<boolean> {
  if (materialHasPurchaseQuantityTierPricing(material)) return true;
  const supplierId = options?.supplierId;
  const materialId = Number((material as any).id);
  if (supplierId != null && supplierId > 0 && Number.isFinite(materialId) && materialId > 0) {
    return supplierPriceBookHasQuantityTierPricing(supplierId, materialId, options?.asOf);
  }
  return false;
}

/** 改数量时是否应按数量重算销售单价（仅阶梯价场景；固定价/标准价禁止冲掉录入单价） */
export async function salesLineQuantityChangeShouldReprice(
  material: Material | Record<string, unknown>,
  options?: { customerId?: number; asOf?: string },
): Promise<boolean> {
  if (materialHasSaleQuantityTierPricing(material)) return true;
  const customerId = options?.customerId;
  const materialId = Number((material as any).id);
  if (customerId != null && customerId > 0 && Number.isFinite(materialId) && materialId > 0) {
    return customerPriceBookHasQuantityTierPricing(customerId, materialId, options?.asOf);
  }
  return false;
}

/** 表单展示精度下单价是否相同（禁止剥税乘回把 800 写成 799.99 / 800.000001） */
function unitPricesDisplayEqual(a: number, b: number): boolean {
  const places = Math.max(0, getCachedNumericPrecisionPlaces('price'));
  const factor = 10 ** places;
  return Math.round(a * factor) === Math.round(b * factor);
}

export async function resolveMaterialMarketSalePrice(
  material: Material | Record<string, unknown>,
  asOf?: string | dayjs.Dayjs,
): Promise<{ unitPrice: number; taxRate: number; snapshot?: Record<string, unknown> | null }> {
  const uuid = String((material as any).uuid ?? '').trim();
  if (!uuid) {
    throw new Error('未维护该日原料行情，请到原料行情录入');
  }
  const priceDate = formatAsOf(asOf) || todaySiteDateString();
  const resolved = await materialMarketPriceApi.resolveSale(uuid, priceDate);
  return {
    unitPrice: Number(resolved.unitPrice) || 0,
    taxRate: Number(resolved.taxRate) || getMaterialDefaultTaxRate(material),
    snapshot: resolved.snapshot ?? null,
  };
}

export function getMaterialDefaultTaxRate(material: Material | Record<string, unknown>): number {
  const defaults = (material as any).defaults ?? {};
  const finance = defaults.finance ?? defaults.Finance;
  const fromFinance =
    finance && typeof finance === 'object'
      ? Number(
          (finance as Record<string, unknown>).defaultTaxRate ??
            (finance as Record<string, unknown>).default_tax_rate,
        ) || 0
      : 0;
  return (
    fromFinance ||
    Number(defaults.defaultTaxRate ?? defaults.default_tax_rate) ||
    Number((material as any).defaultTaxRate ?? (material as any).default_tax_rate) ||
    0
  );
}

/** 补齐物料 defaults（列表/引用展示常不带默认价税，需拉详情） */
export async function resolveMaterialForPricing(
  material: Material | Record<string, unknown>,
  materialList?: Array<Material | Record<string, unknown>>,
): Promise<Material | Record<string, unknown>> {
  const id = Number((material as any).id);
  let full =
    materialList?.find((m) => Number((m as any).id) === id) ?? material;
  const uuid = String((full as any).uuid ?? (material as any).uuid ?? '').trim();
  // 列表常缺 defaults：销价与采购价都拿不到时才拉详情（避免仅缺采购价的销售料反复打详情）
  const needsDetail =
    (full as any).defaults == null ||
    getMaterialSalePriceMethod(full) === 'market' ||
    getMaterialPurchasePriceMethod(full) === 'tier' ||
    (getMaterialDefaultSalePrice(full) <= 0 && getMaterialDefaultPurchasePrice(full) <= 0) ||
    getMaterialDefaultTaxRate(full) <= 0;
  if (uuid && needsDetail) {
    try {
      full = await materialApi.get(uuid);
    } catch {
      /* 保留已有对象 */
    }
  }
  return full;
}

export function pickResolvedUnitPrice(resolved?: PartnerPriceResolveResult | null): number | undefined {
  return pickNumberField(resolved as Record<string, unknown> | null | undefined, 'unitPrice', 'unit_price');
}

export function pickResolvedTaxRate(resolved?: PartnerPriceResolveResult | null): number | undefined {
  return pickNumberField(resolved as Record<string, unknown> | null | undefined, 'taxRate', 'tax_rate');
}

function formatAsOf(asOf?: string | dayjs.Dayjs): string | undefined {
  if (!asOf) return undefined;
  return formatDateTime(asOf, 'YYYY-MM-DD');
}

export type ResolvePriceBatchLine = {
  materialId: number;
  variantAttributes?: Record<string, unknown>;
};

function normalizeBatchLines(
  materialIdsOrLines: number[] | ResolvePriceBatchLine[],
  materials?: Array<Material | Record<string, unknown>>,
): ResolvePriceBatchLine[] {
  if (!materialIdsOrLines.length) return [];
  if (typeof materialIdsOrLines[0] === 'number') {
    return (materialIdsOrLines as number[]).map((materialId) => {
      const material = materials?.find((m) => Number((m as any).id) === materialId);
      const variantAttributes = material
        ? parseVariantAttributesValue(
            (material as any).variantAttributes ?? (material as any).variant_attributes,
          )
        : undefined;
      return { materialId, variantAttributes };
    });
  }
  return materialIdsOrLines as ResolvePriceBatchLine[];
}

export async function resolveCustomerSalePrice(
  customerId: number,
  materialId: number,
  asOf?: string | dayjs.Dayjs,
  variantAttributes?: Record<string, unknown>,
): Promise<PartnerPriceResolveResult> {
  const { resolvePartnerMaterialLinePrice } = await import('../services/partner-price-book');
  const item = await resolvePartnerMaterialLinePrice({
    side: 'sales',
    partnerId: customerId,
    materialId,
    asOf: formatAsOf(asOf),
    variantAttributes,
  });
  return partnerLinePriceToResolveResult(item);
}

function partnerLinePriceToResolveResult(
  item: import('../services/partner-price-book').PartnerMaterialLinePriceResolveResult,
): PartnerPriceResolveResult {
  const raw = item as Record<string, unknown>;
  return {
    found: item.found,
    unitPrice: item.unitPrice ?? raw.unit_price,
    taxRate: item.taxRate ?? raw.tax_rate,
    partnerMaterialCode: item.partnerMaterialCode ?? raw.partner_material_code,
    partnerMaterialName: item.partnerMaterialName ?? raw.partner_material_name,
  } as PartnerPriceResolveResult;
}

export async function resolveCustomerSalePricesBatch(
  customerId: number,
  materialIdsOrLines: number[] | ResolvePriceBatchLine[],
  asOf?: string | dayjs.Dayjs,
  materials?: Array<Material | Record<string, unknown>>,
): Promise<PartnerPriceResolveResult[]> {
  const lines = normalizeBatchLines(materialIdsOrLines, materials);
  if (!customerId || !lines.length) return [];
  const { resolvePartnerMaterialLinePriceBatch } = await import('../services/partner-price-book');
  const res = await resolvePartnerMaterialLinePriceBatch({
    side: 'sales',
    partnerId: customerId,
    asOf: formatAsOf(asOf),
    items: lines.map((line) => ({
      materialId: line.materialId,
      variantAttributes: line.variantAttributes,
    })),
  });
  return (res.items ?? []).map(partnerLinePriceToResolveResult);
}

export async function resolveSupplierPurchasePrice(
  supplierId: number,
  materialId: number,
  asOf?: string | dayjs.Dayjs,
  variantAttributes?: Record<string, unknown>,
): Promise<PartnerPriceResolveResult> {
  const { resolvePartnerMaterialLinePrice } = await import('../services/partner-price-book');
  const item = await resolvePartnerMaterialLinePrice({
    side: 'purchase',
    partnerId: supplierId,
    materialId,
    asOf: formatAsOf(asOf),
    variantAttributes,
  });
  return partnerLinePriceToResolveResult(item);
}

export async function resolveSupplierPurchasePricesBatch(
  supplierId: number,
  materialIdsOrLines: number[] | ResolvePriceBatchLine[],
  asOf?: string | dayjs.Dayjs,
  materials?: Array<Material | Record<string, unknown>>,
): Promise<PartnerPriceResolveResult[]> {
  const lines = normalizeBatchLines(materialIdsOrLines, materials);
  if (!supplierId || !lines.length) return [];
  const { resolvePartnerMaterialLinePriceBatch } = await import('../services/partner-price-book');
  const res = await resolvePartnerMaterialLinePriceBatch({
    side: 'purchase',
    partnerId: supplierId,
    asOf: formatAsOf(asOf),
    items: lines.map((line) => ({
      materialId: line.materialId,
      variantAttributes: line.variantAttributes,
    })),
  });
  return (res.items ?? []).map(partnerLinePriceToResolveResult);
}

export function pickSaleUnitPrice(
  material: Material | Record<string, unknown>,
  resolved?: PartnerPriceResolveResult | null,
): number {
  if (resolved?.found) {
    const fromResolved = pickResolvedUnitPrice(resolved);
    if (fromResolved != null) return fromResolved;
  }
  return getMaterialDefaultSalePrice(material);
}

export function pickPurchaseUnitPrice(
  material: Material | Record<string, unknown>,
  resolved?: PartnerPriceResolveResult | null,
): number {
  if (resolved?.found) {
    const fromResolved = pickResolvedUnitPrice(resolved);
    if (fromResolved != null) return fromResolved;
  }
  return getMaterialDefaultPurchasePrice(material);
}

export type ResolvedSalesMaterialLinePricing = {
  material: Material | Record<string, unknown>;
  unitPrice: number;
  taxRate: number;
  pricingSnapshot?: Record<string, unknown> | null;
  material_spec?: string;
  material_model?: string;
  partner_material_code?: string;
  partner_material_name?: string;
};

/** 批量选料：客户价本 + 物料默认价税（与单行 applySalesDocumentLineMaterialPricing 一致） */
export async function resolveSalesDocumentMaterialLinesPricing(
  materials: Array<Material | Record<string, unknown>>,
  options?: {
    customerId?: number;
    asOf?: string | dayjs.Dayjs;
    priceType?: string;
    materialList?: Array<Material | Record<string, unknown>>;
  },
): Promise<ResolvedSalesMaterialLinePricing[]> {
  if (!materials.length) return [];

  const pt = options?.priceType ?? 'tax_exclusive';
  const asOf =
    options?.asOf != null
      ? dayjs.isDayjs(options.asOf)
        ? options.asOf
        : dayjs(options.asOf)
      : dayjs();

  const enriched = await Promise.all(
    materials.map(async (m) =>
      ensureMaterialMasterSnapshot(await resolveMaterialForPricing(m, options?.materialList)),
    ),
  );

  const resolveMap = new Map<number, PartnerPriceResolveResult>();
  const customerId = options?.customerId ? Number(options.customerId) : undefined;
  if (customerId && enriched.length) {
    try {
      const items = await resolveCustomerSalePricesBatch(
        customerId,
        enriched.map((m) => ({
          materialId: Number((m as Material).id),
          variantAttributes: parseVariantAttributesValue(
            (m as Material).variantAttributes ?? (m as any).variant_attributes,
          ),
        })),
        asOf,
        enriched,
      );
      enriched.forEach((m, i) => {
        const id = Number((m as Material).id);
        if (items[i]) resolveMap.set(id, items[i]);
      });
    } catch {
      /* 回退物料默认价 */
    }
  }

  return Promise.all(
    enriched.map(async (full, idx) => {
      const id = Number((full as Material).id ?? (materials[idx] as Material).id);
      const resolved = resolveMap.get(id);
      const materialTax = getMaterialDefaultTaxRate(full);
      let inflateTaxRate: number | null = null;
      let taxRate = materialTax;
      let unitPrice = pickSaleUnitPrice(full, resolved);
      let pricingSnapshot: Record<string, unknown> | null = null;
      if (resolved?.found) {
        const src = pickSourceTaxRate(pickResolvedTaxRate(resolved), materialTax);
        taxRate = src.taxRate;
        inflateTaxRate = resolveInflateTaxRateForExclusiveBookPrice(
          pt,
          src.inflateTaxRate,
          src.taxRate,
          true,
        );
      } else if (getMaterialSalePriceMethod(full) === 'market') {
        const market = await resolveMaterialMarketSalePrice(full, asOf);
        unitPrice = market.unitPrice;
        const src = pickSourceTaxRate(market.taxRate, materialTax);
        taxRate = src.taxRate;
        inflateTaxRate = src.inflateTaxRate;
        pricingSnapshot = market.snapshot ?? null;
      } else {
        // pickSaleUnitPrice → getMaterialDefaultSalePrice 已剥未税
        const src = pickSourceTaxRate(materialTax > 0 ? materialTax : null, materialTax);
        taxRate = src.taxRate;
        inflateTaxRate = src.inflateTaxRate;
      }
      unitPrice = toFormUnitPriceFromExclusive(unitPrice, pt, inflateTaxRate);
      const partner = pickPartnerMaterialSnapshotFields(resolved);
      return {
        material: full,
        unitPrice,
        taxRate,
        pricingSnapshot,
        material_spec: readMaterialTextField(full as Record<string, unknown>, 'specification'),
        material_model: readMaterialTextField(full as Record<string, unknown>, 'model'),
        partner_material_code: partner.partner_material_code,
        partner_material_name: partner.partner_material_name,
      };
    }),
  );
}

export async function resolveOrderLineSalePrice(
  customerId: number | undefined,
  materialId: number | undefined,
  variantAttributes: unknown,
  material: Material | Record<string, unknown> | undefined,
  asOf?: string | dayjs.Dayjs,
  quantity?: number,
): Promise<{
  unitPrice: number;
  taxRate: number;
  /** 取价源税率；仅 >0 时可用其将未税价乘回含税表单价 */
  inflateTaxRate: number | null;
  /** 单价来自客户价本剥离后的未税价 */
  fromPartnerPriceBook: boolean;
  resolved?: PartnerPriceResolveResult;
  snapshot?: Record<string, unknown> | null;
}> {
  const attrs = parseVariantAttributesValue(variantAttributes);
  const taxR = material != null ? getMaterialDefaultTaxRate(material) : 0;
  const fallbackMarket = async () => {
    if (material && getMaterialSalePriceMethod(material) === 'market') {
      const market = await resolveMaterialMarketSalePrice(material, asOf);
      const src = pickSourceTaxRate(market.taxRate, taxR);
      return {
        unitPrice: market.unitPrice,
        taxRate: src.taxRate,
        inflateTaxRate: src.inflateTaxRate,
        fromPartnerPriceBook: false,
        snapshot: market.snapshot ?? null,
      };
    }
    // getMaterialDefaultSalePrice 已按物料价类剥成未税
    const src = pickSourceTaxRate(taxR > 0 ? taxR : null, taxR);
    return {
      unitPrice: material ? getMaterialDefaultSalePrice(material) : 0,
      taxRate: src.taxRate,
      inflateTaxRate: src.inflateTaxRate,
      fromPartnerPriceBook: false,
      snapshot: null,
    };
  };
  if (!customerId || !materialId) {
    const fb = await fallbackMarket();
    return { ...fb, resolved: undefined };
  }
  try {
    const { resolvePartnerMaterialLinePrice } = await import('../services/partner-price-book');
    const unified = await resolvePartnerMaterialLinePrice({
      side: 'sales',
      partnerId: customerId,
      materialId,
      quantity: quantity != null && Number.isFinite(Number(quantity)) ? Number(quantity) : undefined,
      asOf: formatAsOf(asOf),
      variantAttributes: attrs,
    });
    const unifiedRaw = unified as Record<string, unknown>;
    const partnerMaterialCode = String(
      unified.partnerMaterialCode ?? unifiedRaw.partner_material_code ?? '',
    ).trim();
    const partnerMaterialName = String(
      unified.partnerMaterialName ?? unifiedRaw.partner_material_name ?? '',
    ).trim();
    const unitPriceRaw = unified.unitPrice ?? unifiedRaw.unit_price;
    const taxRateRaw = unified.taxRate ?? unifiedRaw.tax_rate;
    const resolvedFromUnified = {
      found: unified.found,
      unitPrice: unitPriceRaw,
      taxRate: taxRateRaw,
      partnerMaterialCode,
      partnerMaterialName,
    } as PartnerPriceResolveResult;
    const hasPartnerSnapshot = partnerMaterialCode !== '' || partnerMaterialName !== '';
    if (unified.found && unitPriceRaw != null && Number(unitPriceRaw) > 0) {
      const src = pickSourceTaxRate(taxRateRaw, taxR);
      return {
        unitPrice: Number(unitPriceRaw),
        taxRate: src.taxRate,
        inflateTaxRate: src.inflateTaxRate,
        fromPartnerPriceBook: true,
        resolved: resolvedFromUnified,
        snapshot: null,
      };
    }
    if (hasPartnerSnapshot) {
      const fb = await fallbackMarket();
      return { ...fb, resolved: resolvedFromUnified };
    }
  } catch {
    /* 统一解析失败则走物料/行情回落 */
  }
  const fb = await fallbackMarket();
  return { ...fb, resolved: undefined };
}

function pickPartnerMaterialSnapshotFields(
  resolved?: PartnerPriceResolveResult | null,
): { partner_material_code: string; partner_material_name: string } {
  if (!resolved) {
    return { partner_material_code: '', partner_material_name: '' };
  }
  const raw = resolved as Record<string, unknown>;
  const code = String(resolved.partnerMaterialCode ?? raw.partner_material_code ?? '').trim();
  const name = String(resolved.partnerMaterialName ?? raw.partner_material_name ?? '').trim();
  return { partner_material_code: code, partner_material_name: name };
}

/** 行上物料 uuid：选料写 `_masterMaterialUuid`，部分下推行写 `material_uuid` */
function readLineMaterialUuid(line: Record<string, unknown>): string | undefined {
  const raw =
    line.material_uuid ??
    line.materialUuid ??
    line._masterMaterialUuid ??
    line.masterMaterialUuid;
  const uuid = String(raw ?? '').trim();
  return uuid || undefined;
}

const toSafeNumber = (value: unknown): number => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

/**
 * 与后端 convert_unit_price / normalize_stored_unit_price_to_exclusive 对齐：
 * 中间过程保留最多 6 位小数，禁止先压成「分」再乘税率（含税 800@13% 会变成 799.99）。
 */
const UNIT_PRICE_CONVERT_PLACES = 6;

function roundUnitPriceConvert(value: number): number {
  if (!Number.isFinite(value)) return 0;
  const factor = 10 ** UNIT_PRICE_CONVERT_PLACES;
  return Math.round(value * factor) / factor;
}

/** 切换含税/不含税时换算行单价（询价出口未税；表单含税时再乘回） */
export function convertUnitPriceByPriceType(
  unitPriceInput: unknown,
  taxRateInput: unknown,
  fromPriceType: string,
  toPriceType: string,
): number {
  const unitPrice = toSafeNumber(unitPriceInput);
  if (fromPriceType === toPriceType) return roundUnitPriceConvert(unitPrice);

  const taxRate = toSafeNumber(taxRateInput);
  const factor = 1 + taxRate / 100;
  if (factor <= 0) return roundUnitPriceConvert(unitPrice);

  if (fromPriceType === 'tax_exclusive' && toPriceType === 'tax_inclusive') {
    return roundUnitPriceConvert(unitPrice * factor);
  }
  if (fromPriceType === 'tax_inclusive' && toPriceType === 'tax_exclusive') {
    return roundUnitPriceConvert(unitPrice / factor);
  }
  return roundUnitPriceConvert(unitPrice);
}

/**
 * 取价 API 约定返回未税单价；表单为含税时再乘回。
 * 仅当取价源自身税率 > 0（已按该税率剥离）时乘回；禁止用物料回落税率对「未剥离的含税价」再乘。
 */
export function toFormUnitPriceFromExclusive(
  unitPriceInput: unknown,
  formPriceType: string,
  inflateTaxRate: number | null | undefined,
): number {
  const unitPrice = toSafeNumber(unitPriceInput);
  if (
    formPriceType !== 'tax_inclusive' ||
    !(unitPrice > 0) ||
    inflateTaxRate == null ||
    !(inflateTaxRate > 0)
  ) {
    return unitPrice;
  }
  const converted = convertUnitPriceByPriceType(
    unitPrice,
    inflateTaxRate,
    'tax_exclusive',
    'tax_inclusive',
  );
  return quantizeNumericByPlaces(converted, getCachedNumericPrecisionPlaces('price'));
}

/**
 * 价本/API 出口为未税单价；表单为含税时乘回。
 * 行税率回落只用于已确认来自价本（已剥离）；物料默认价禁止用回落税率再乘。
 */
export function resolveInflateTaxRateForExclusiveBookPrice(
  formPriceType: string,
  inflateTaxRate: number | null | undefined,
  lineTaxRate: number,
  fromPartnerPriceBook: boolean,
): number | null {
  if (formPriceType !== 'tax_inclusive') return null;
  if (inflateTaxRate != null && Number(inflateTaxRate) > 0) return Number(inflateTaxRate);
  if (fromPartnerPriceBook && Number(lineTaxRate) > 0) return Number(lineTaxRate);
  return null;
}

export function formUnitPriceFromExclusiveBook(
  exclusiveUnitPrice: unknown,
  formPriceType: string,
  inflateTaxRate: number | null | undefined,
  lineTaxRate: number,
  fromPartnerPriceBook: boolean,
): number {
  const inflate = resolveInflateTaxRateForExclusiveBookPrice(
    formPriceType,
    inflateTaxRate,
    lineTaxRate,
    fromPartnerPriceBook,
  );
  return toFormUnitPriceFromExclusive(exclusiveUnitPrice, formPriceType, inflate);
}

function pickSourceTaxRate(raw: unknown, fallback: number): {
  taxRate: number;
  inflateTaxRate: number | null;
} {
  if (raw != null && raw !== '') {
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) {
      return { taxRate: n, inflateTaxRate: n };
    }
  }
  return { taxRate: fallback, inflateTaxRate: null };
}

/** 选物料后解析客户价本/物料默认价并回填行单价与税率（与报价单一致） */
export async function applySalesDocumentLineMaterialPricing(
  form: FormWithLineItems | null | undefined,
  index: number,
  material: Material | Record<string, unknown>,
  options?: {
    materialList?: Array<Material | Record<string, unknown>>;
    asOfField?: string;
    /**
     * 改数量重算：只更新价税与 pricing_snapshot。
     * 禁止覆盖行上已有规格/型号/伙伴料号快照（选料 stub 常缺 uuid，重读会写成空串）。
     */
    priceOnly?: boolean;
  },
): Promise<void> {
  if (!form) return;
  const full = await ensureMaterialMasterSnapshot(
    await resolveMaterialForPricing(material, options?.materialList),
  );
  const materialSpec = readMaterialTextField(full as Record<string, unknown>, 'specification');
  const materialModel = readMaterialTextField(full as Record<string, unknown>, 'model');
  const customerId = form.getFieldValue('customer_id');
  const asOfField = options?.asOfField ?? 'order_date';
  const asOfRaw = form.getFieldValue(asOfField);
  const asOf =
    asOfRaw != null
      ? dayjs.isDayjs(asOfRaw)
        ? asOfRaw
        : dayjs(asOfRaw as string)
      : dayjs();
  const pt = String(form.getFieldValue('price_type') ?? 'tax_exclusive');
  const materialId = Number((full as Material).id ?? (material as Record<string, unknown>).id);
  let unitPrice = 0;
  let taxRate = getMaterialDefaultTaxRate(full);
  let inflateTaxRate: number | null = null;
  let fromPartnerPriceBook = false;
  let snapshot: Record<string, unknown> | null = null;
  let partnerSnapshot = { partner_material_code: '', partner_material_name: '' };
  try {
    const itemsForQty = normalizeFormListItems<Record<string, unknown>>(form.getFieldValue('items'));
    const qtyRaw =
      itemsForQty[index]?.required_quantity ??
      itemsForQty[index]?.requiredQuantity ??
      itemsForQty[index]?.quote_quantity ??
      itemsForQty[index]?.contract_quantity ??
      itemsForQty[index]?.delivery_quantity ??
      itemsForQty[index]?.return_quantity ??
      itemsForQty[index]?.ordered_quantity ??
      itemsForQty[index]?.receipt_quantity;
    const lineQty = Number(qtyRaw);
    const resolved = await resolveOrderLineSalePrice(
      customerId ? Number(customerId) : undefined,
      Number.isFinite(materialId) ? materialId : undefined,
      undefined,
      full,
      asOf,
      Number.isFinite(lineQty) && lineQty > 0 ? lineQty : undefined,
    );
    unitPrice = resolved.unitPrice;
    taxRate = resolved.taxRate;
    inflateTaxRate = resolved.inflateTaxRate;
    fromPartnerPriceBook = resolved.fromPartnerPriceBook;
    snapshot = resolved.snapshot ?? null;
    partnerSnapshot = pickPartnerMaterialSnapshotFields(resolved.resolved);
  } catch (e: unknown) {
    message.error(getApiErrorMessage(e, '未维护该日原料行情，请到原料行情录入'));
  }
  let up = formUnitPriceFromExclusiveBook(unitPrice, pt, inflateTaxRate, taxRate, fromPartnerPriceBook);
  const priceOnly = options?.priceOnly === true;
  const items = [...normalizeFormListItems<Record<string, unknown>>(form.getFieldValue('items'))];
  if (!items[index]) return;
  items[index] = mergeFormListLineFromFieldStore(form, 'items', index, items[index] as Record<string, unknown>);
  const existingPrice = Number(items[index]?.unit_price);
  // 改数量重算：价本未命中时保留行上已有单价/税率，避免下推打开页把来源价冲成 0
  if (priceOnly && !(up > 0)) {
    if (Number.isFinite(existingPrice) && existingPrice > 0) {
      up = existingPrice;
      const existingTax = Number(items[index]?.tax_rate);
      if (Number.isFinite(existingTax) && existingTax >= 0) {
        taxRate = existingTax;
      }
    }
  }
  const correctedInclusiveUp = formUnitPriceFromExclusiveBook(
    unitPrice,
    pt,
    inflateTaxRate,
    taxRate,
    fromPartnerPriceBook,
  );
  if (
    pt === 'tax_inclusive' &&
    fromPartnerPriceBook &&
    unitPrice > 0 &&
    correctedInclusiveUp > 0 &&
    !unitPricesDisplayEqual(correctedInclusiveUp, unitPrice) &&
    Number.isFinite(existingPrice) &&
    existingPrice > 0 &&
    unitPricesDisplayEqual(existingPrice, unitPrice)
  ) {
    up = correctedInclusiveUp;
  }
  // 取价结果与行上单价在展示精度下相同则保留原值，禁止剥税乘回改写末位（800→799.99 / 799.999998）
  // 选料与改数量共用：价本含税标准价剥未税再乘回不得改写已录入/已回填的干净单价
  if (
    up > 0 &&
    Number.isFinite(existingPrice) &&
    existingPrice > 0 &&
    unitPricesDisplayEqual(existingPrice, up)
  ) {
    up = existingPrice;
  }
  const refreshPartnerSnapshot = !priceOnly;
  let nextRow: Record<string, unknown> = {
    ...items[index],
    unit_price: up,
    tax_rate: taxRate,
    pricing_snapshot: snapshot ?? null,
  };
  if (!priceOnly) {
    // 选料重新取价：清除手工改价锁
    nextRow = clearDocumentLineUnitPriceLock({
      ...nextRow,
      material_spec: materialSpec,
      material_model: materialModel,
    });
  }
  if (refreshPartnerSnapshot) {
    nextRow.partner_material_code = partnerSnapshot.partner_material_code;
    nextRow.partner_material_name = partnerSnapshot.partner_material_name;
  }
  // setFieldsValue 不走 onValuesChange；销售行金额以 item_amount 为展示真源，须同步 qty×单价
  const itemAmount = recalcDocumentStoredLineAmount(
    {
      qty: readDocumentLineQuantityForStoredAmount(nextRow),
      unit_price: up,
      tax_rate: taxRate,
      is_gift: nextRow.is_gift,
    },
    pt,
  );
  // 禁止 setFieldsValue({ items })：会冲掉仅经 setFieldValue 写入的规格/型号等快照列
  form.setFieldValue?.(['items', index, 'unit_price'], up);
  form.setFieldValue?.(['items', index, 'tax_rate'], taxRate);
  form.setFieldValue?.(['items', index, 'pricing_snapshot'], snapshot ?? null);
  form.setFieldValue?.(['items', index, 'item_amount'], itemAmount);
  if (!priceOnly) {
    form.setFieldValue?.(['items', index, 'material_spec'], materialSpec);
    form.setFieldValue?.(['items', index, 'material_model'], materialModel);
    form.setFieldValue?.(['items', index, 'unit_price_locked'], undefined);
  }
  if (refreshPartnerSnapshot) {
    form.setFieldValue?.(['items', index, 'partner_material_code'], partnerSnapshot.partner_material_code);
    form.setFieldValue?.(['items', index, 'partner_material_name'], partnerSnapshot.partner_material_name);
  }
}

export type ResolvedPurchaseMaterialLinePricing = {
  material: Material | Record<string, unknown>;
  unitPrice: number;
  taxRate: number;
};

export async function resolveOrderLinePurchasePrice(
  supplierId: number | undefined,
  materialId: number | undefined,
  variantAttributes: unknown,
  material: Material | Record<string, unknown> | undefined,
  asOf?: string | dayjs.Dayjs,
  quantity?: number,
): Promise<{
  unitPrice: number;
  taxRate: number;
  inflateTaxRate: number | null;
  resolved?: PartnerPriceResolveResult;
}> {
  const attrs = parseVariantAttributesValue(variantAttributes);
  const taxR = material != null ? getMaterialDefaultTaxRate(material) : 0;
  if (!supplierId || !materialId) {
    const src = pickSourceTaxRate(taxR > 0 ? taxR : null, taxR);
    return {
      unitPrice: material ? getMaterialDefaultPurchasePrice(material) : 0,
      taxRate: src.taxRate,
      inflateTaxRate: src.inflateTaxRate,
      resolved: undefined,
    };
  }
  try {
    const { resolvePartnerMaterialLinePrice } = await import('../services/partner-price-book');
    const unified = await resolvePartnerMaterialLinePrice({
      side: 'purchase',
      partnerId: supplierId,
      materialId,
      quantity: quantity != null && Number.isFinite(Number(quantity)) ? Number(quantity) : undefined,
      asOf: formatAsOf(asOf),
      variantAttributes: attrs,
    });
    const unifiedRaw = unified as Record<string, unknown>;
    const partnerMaterialCode = String(
      unified.partnerMaterialCode ?? unifiedRaw.partner_material_code ?? '',
    ).trim();
    const partnerMaterialName = String(
      unified.partnerMaterialName ?? unifiedRaw.partner_material_name ?? '',
    ).trim();
    const unitPriceRaw = unified.unitPrice ?? unifiedRaw.unit_price;
    const taxRateRaw = unified.taxRate ?? unifiedRaw.tax_rate;
    const resolvedFromUnified = {
      found: unified.found,
      unitPrice: unitPriceRaw,
      taxRate: taxRateRaw,
      partnerMaterialCode,
      partnerMaterialName,
    } as PartnerPriceResolveResult;
    const hasPartnerSnapshot = partnerMaterialCode !== '' || partnerMaterialName !== '';
    if (unified.found && unitPriceRaw != null && Number(unitPriceRaw) > 0) {
      const src = pickSourceTaxRate(taxRateRaw, taxR);
      return {
        unitPrice: Number(unitPriceRaw),
        taxRate: src.taxRate,
        inflateTaxRate: src.inflateTaxRate,
        resolved: resolvedFromUnified,
      };
    }
    if (hasPartnerSnapshot) {
      const src = pickSourceTaxRate(taxR > 0 ? taxR : null, taxR);
      return {
        unitPrice: material ? getMaterialDefaultPurchasePrice(material) : 0,
        taxRate: src.taxRate,
        inflateTaxRate: src.inflateTaxRate,
        resolved: resolvedFromUnified,
      };
    }
  } catch {
    /* 回落物料默认采购价 */
  }
  const src = pickSourceTaxRate(taxR > 0 ? taxR : null, taxR);
  return {
    unitPrice: material ? getMaterialDefaultPurchasePrice(material) : 0,
    taxRate: src.taxRate,
    inflateTaxRate: src.inflateTaxRate,
    resolved: undefined,
  };
}

/** 批量选料：供应商价本 + 物料默认采购价（与单行 applyPurchaseDocumentLineMaterialPricing 一致） */
export async function resolvePurchaseDocumentMaterialLinesPricing(
  materials: Array<Material | Record<string, unknown>>,
  options?: {
    supplierId?: number;
    asOf?: string | dayjs.Dayjs;
    priceType?: string;
    materialList?: Array<Material | Record<string, unknown>>;
    /** 价本与物料均无税率时的回落（采购订单默认 13） */
    fallbackTaxRate?: number;
  },
): Promise<ResolvedPurchaseMaterialLinePricing[]> {
  if (!materials.length) return [];

  const pt = options?.priceType ?? 'tax_inclusive';
  const fallbackTax =
    options?.fallbackTaxRate != null &&
    Number.isFinite(Number(options.fallbackTaxRate)) &&
    Number(options.fallbackTaxRate) > 0
      ? Number(options.fallbackTaxRate)
      : 13;
  const asOf =
    options?.asOf != null
      ? dayjs.isDayjs(options.asOf)
        ? options.asOf
        : dayjs(options.asOf)
      : dayjs();

  const enriched = await Promise.all(
    materials.map(async (m) =>
      ensureMaterialMasterSnapshot(await resolveMaterialForPricing(m, options?.materialList)),
    ),
  );

  const resolveMap = new Map<number, PartnerPriceResolveResult>();
  const supplierId = options?.supplierId ? Number(options.supplierId) : undefined;
  if (supplierId && enriched.length) {
    try {
      const items = await resolveSupplierPurchasePricesBatch(
        supplierId,
        enriched.map((m) => ({
          materialId: Number((m as Material).id),
          variantAttributes: parseVariantAttributesValue(
            (m as Material).variantAttributes ?? (m as any).variant_attributes,
          ),
        })),
        asOf,
        enriched,
      );
      enriched.forEach((m, i) => {
        const id = Number((m as Material).id);
        if (items[i]) resolveMap.set(id, items[i]);
      });
    } catch {
      /* 回退物料默认采购价 */
    }
  }

  return enriched.map((full, idx) => {
    const id = Number((full as Material).id ?? (materials[idx] as Material).id);
    const resolved = resolveMap.get(id);
    const fromBook = pickResolvedTaxRate(resolved);
    const fromMaterial = getMaterialDefaultTaxRate(full);
    const src = pickSourceTaxRate(
      fromBook != null && fromBook > 0 ? fromBook : null,
      (fromMaterial > 0 ? fromMaterial : 0) || fallbackTax,
    );
    const taxRate = src.taxRate;
    let unitPrice = pickPurchaseUnitPrice(full, resolved);
    const inflateTaxRate = resolved?.found
      ? resolveInflateTaxRateForExclusiveBookPrice(pt, src.inflateTaxRate, taxRate, true)
      : fromMaterial > 0 && pt === 'tax_inclusive'
        ? fromMaterial
        : src.inflateTaxRate;
    unitPrice = toFormUnitPriceFromExclusive(unitPrice, pt, inflateTaxRate);
    const partner = pickPartnerMaterialSnapshotFields(resolved);
    return {
      material: full,
      unitPrice,
      taxRate,
      material_spec: readMaterialTextField(full as Record<string, unknown>, 'specification'),
      material_model: readMaterialTextField(full as Record<string, unknown>, 'model'),
      partner_material_code: partner.partner_material_code,
      partner_material_name: partner.partner_material_name,
    };
  });
}

/**
 * 选物料后解析供应商价本/物料默认采购价并回填行单价。
 * unitPriceField：PO 用 unit_price；采购申请用 suggested_unit_price。
 */
export async function applyPurchaseDocumentLineMaterialPricing(
  form: FormWithLineItems | null | undefined,
  index: number,
  material: Material | Record<string, unknown>,
  options?: {
    materialList?: Array<Material | Record<string, unknown>>;
    asOfField?: string;
    unitPriceField?: 'unit_price' | 'suggested_unit_price';
    includeTaxRate?: boolean;
    /** 表头供应商；缺省时读行内 supplier_id */
    supplierId?: number;
    /** 价本与物料均无税率时的回落 */
    fallbackTaxRate?: number;
    /** 改数量重算时：价本未命中则保留行上已有单价，避免把手工价/回填价清成 0 */
    preserveUnitPriceWhenUnresolved?: boolean;
    /**
     * 只更新价税与伙伴料号，不覆盖行上规格/型号（下推、换供应商重价；物料 stub 常缺 uuid）。
     */
    preserveSpecSnapshot?: boolean;
  },
): Promise<void> {
  if (!form) return;
  const full = await ensureMaterialMasterSnapshot(
    await resolveMaterialForPricing(material, options?.materialList),
  );
  const materialSpec = readMaterialTextField(full as Record<string, unknown>, 'specification');
  const materialModel = readMaterialTextField(full as Record<string, unknown>, 'model');
  const unitPriceField = options?.unitPriceField ?? 'unit_price';
  const includeTaxRate = options?.includeTaxRate !== false && unitPriceField === 'unit_price';
  const asOfField = options?.asOfField ?? 'order_date';
  const asOfRaw = form.getFieldValue(asOfField) ?? form.getFieldValue('requisition_date');
  const asOf =
    asOfRaw != null
      ? dayjs.isDayjs(asOfRaw)
        ? asOfRaw
        : dayjs(asOfRaw as string)
      : dayjs();
  const pt = String(form.getFieldValue('price_type') ?? 'tax_inclusive');
  const items = [...normalizeFormListItems<Record<string, unknown>>(form.getFieldValue('items'))];
  if (!items[index]) return;
  items[index] = mergeFormListLineFromFieldStore(form, 'items', index, items[index] as Record<string, unknown>);
  const lineSupplier = Number(items[index]?.supplier_id);
  const headerSupplier = Number(form.getFieldValue('supplier_id'));
  const supplierId =
    options?.supplierId != null && Number.isFinite(options.supplierId)
      ? Number(options.supplierId)
      : Number.isFinite(lineSupplier) && lineSupplier > 0
        ? lineSupplier
        : Number.isFinite(headerSupplier) && headerSupplier > 0
          ? headerSupplier
          : undefined;
  const materialId = Number((full as Material).id ?? (material as Record<string, unknown>).id);
  const qtyRaw =
    items[index]?.ordered_quantity ??
    items[index]?.orderedQuantity ??
    items[index]?.quantity ??
    items[index]?.return_quantity ??
    items[index]?.receipt_quantity ??
    items[index]?.delivery_quantity ??
    items[index]?.required_quantity ??
    items[index]?.requiredQuantity;
  const lineQty = Number(qtyRaw);
  const {
    unitPrice,
    taxRate: resolvedTax,
    inflateTaxRate,
    resolved,
  } = await resolveOrderLinePurchasePrice(
    supplierId,
    Number.isFinite(materialId) ? materialId : undefined,
    undefined,
    full,
    asOf,
    Number.isFinite(lineQty) && lineQty > 0 ? lineQty : undefined,
  );
  const lineTaxFallback = Number(items[index]?.tax_rate);
  const taxRate =
    (resolvedTax > 0 ? resolvedTax : 0) ||
    (Number.isFinite(lineTaxFallback) && lineTaxFallback > 0 ? lineTaxFallback : 0) ||
    (options?.fallbackTaxRate != null && Number(options.fallbackTaxRate) > 0
      ? Number(options.fallbackTaxRate)
      : 13);
  const partnerSnapshot = pickPartnerMaterialSnapshotFields(resolved);
  let up = toFormUnitPriceFromExclusive(unitPrice, pt, inflateTaxRate);
  if (options?.preserveUnitPriceWhenUnresolved && !(up > 0)) {
    const existing = Number(items[index]?.[unitPriceField]);
    if (Number.isFinite(existing) && existing > 0) {
      up = existing;
    }
  }
  /** 改数量/换供应商重价：只动价税（数量未命中价本时保留单价）；规格型号仅选料写入 */
  const preserveSpecSnapshot =
    options?.preserveSpecSnapshot === true || options?.preserveUnitPriceWhenUnresolved === true;
  const refreshPartnerSnapshot = !options?.preserveUnitPriceWhenUnresolved;
  form.setFieldValue?.(['items', index, unitPriceField], up);
  if (!preserveSpecSnapshot) {
    form.setFieldValue?.(['items', index, 'material_spec'], materialSpec);
    form.setFieldValue?.(['items', index, 'material_model'], materialModel);
  }
  if (refreshPartnerSnapshot) {
    form.setFieldValue?.(['items', index, 'partner_material_code'], partnerSnapshot.partner_material_code);
    form.setFieldValue?.(['items', index, 'partner_material_name'], partnerSnapshot.partner_material_name);
  }
  if (includeTaxRate) {
    form.setFieldValue?.(['items', index, 'tax_rate'], taxRate);
  }
}

export type PurchaseLineRepriceTrigger = 'material' | 'quantity' | 'partner' | 'asOf';

/**
 * 按客商编号映射回填行上客户/供应商料号、品名（不改动单价）。
 */
export async function refreshPartnerMaterialLineSnapshot(
  form: FormWithLineItems | null | undefined,
  index: number,
  options: {
    side: 'purchase' | 'sales';
    partnerId?: number;
    asOfField?: string;
    materialList?: Array<Material | Record<string, unknown>>;
    material?: Material | Record<string, unknown>;
    /** true：换客商时强制按新客商重取映射 */
    overwrite?: boolean;
  },
): Promise<void> {
  if (!form) return;
  const items = normalizeFormListItems<Record<string, unknown>>(form.getFieldValue('items'));
  const line = items[index];
  if (!line) return;
  const materialId = Number(line.material_id ?? line.materialId);
  if (!Number.isFinite(materialId) || materialId <= 0) return;

  const existingCode = String(line.partner_material_code ?? line.partnerMaterialCode ?? '').trim();
  const existingName = String(line.partner_material_name ?? line.partnerMaterialName ?? '').trim();
  if (!options.overwrite && existingCode && existingName) return;

  const headerPartnerId =
    options.side === 'purchase'
      ? Number(form.getFieldValue('supplier_id'))
      : Number(form.getFieldValue('customer_id'));
  const linePartnerId = Number(
    options.side === 'purchase' ? line.supplier_id ?? line.supplierId : line.customer_id ?? line.customerId,
  );
  const partnerId =
    options.partnerId != null && Number.isFinite(options.partnerId) && options.partnerId > 0
      ? Number(options.partnerId)
      : Number.isFinite(linePartnerId) && linePartnerId > 0
        ? linePartnerId
        : Number.isFinite(headerPartnerId) && headerPartnerId > 0
          ? headerPartnerId
          : undefined;
  if (!partnerId) return;

  const asOfField = options.asOfField ?? 'order_date';
  const asOfRaw =
    form.getFieldValue(asOfField) ??
    form.getFieldValue('requisition_date') ??
    form.getFieldValue('order_date');
  const qtyRaw =
    line.ordered_quantity ??
    line.orderedQuantity ??
    line.quantity ??
    line.required_quantity ??
    line.requiredQuantity;
  const qty = Number(qtyRaw);

  const { resolvePartnerMaterialLinePrice } = await import('../services/partner-price-book');
  const unified = await resolvePartnerMaterialLinePrice({
    side: options.side,
    partnerId,
    materialId,
    quantity: Number.isFinite(qty) && qty > 0 ? qty : undefined,
    asOf: formatAsOf(asOfRaw as string | dayjs.Dayjs),
  });
  const partner = pickPartnerMaterialSnapshotFields(unified);
  if (!partner.partner_material_code && !partner.partner_material_name) return;

  if (options.overwrite || !existingCode) {
    form.setFieldValue?.(['items', index, 'partner_material_code'], partner.partner_material_code);
  }
  if (options.overwrite || !existingName) {
    form.setFieldValue?.(['items', index, 'partner_material_name'], partner.partner_material_name);
  }
}

/**
 * 未锁定来源行：按数量/供应商/日期重算采购单价。
 * trigger=partner|quantity 时不覆盖行规格/型号快照（与下推、选料带入一致）。
 */
export async function repriceUnlockedPurchaseDocumentLineIfNeeded(
  form: FormWithLineItems | null | undefined,
  index: number,
  options?: {
    materialList?: Array<Material | Record<string, unknown>>;
    asOfField?: string;
    unitPriceField?: 'unit_price' | 'suggested_unit_price';
    supplierId?: number;
    fallbackTaxRate?: number;
    /** material 触发时必传 */
    material?: Material | Record<string, unknown>;
    /** 仅 quantity：价本未命中时保留行上单价 */
    trigger?: PurchaseLineRepriceTrigger;
  },
): Promise<void> {
  if (!form) return;
  const items = normalizeFormListItems<Record<string, unknown>>(form.getFieldValue('items'));
  const line = items[index];
  if (!line) return;
  if (isDocumentLineUnitPriceLocked(line)) {
    const lockedPrice = Number(line.unit_price ?? line.suggested_unit_price);
    if (Number.isFinite(lockedPrice) && lockedPrice >= 0) {
      await refreshPartnerMaterialLineSnapshot(form, index, {
        side: 'purchase',
        partnerId: options?.supplierId,
        asOfField: options?.asOfField,
        materialList: options?.materialList,
        material: options?.material,
        overwrite: options?.trigger === 'partner',
      });
    }
    return;
  }

  const materialId = Number(line.material_id ?? line.materialId);
  if (!Number.isFinite(materialId) || materialId <= 0) return;

  const stub = options?.material ?? {
    id: materialId,
    uuid: readLineMaterialUuid(line),
  };
  const material = await resolveMaterialForPricing(stub, options?.materialList);

  if (options?.trigger === 'quantity') {
    const asOfField = options?.asOfField ?? 'order_date';
    const asOfRaw = form.getFieldValue(asOfField) ?? form.getFieldValue('requisition_date');
    const asOf = formatAsOf(asOfRaw as string | dayjs.Dayjs);
    const lineSupplier = Number(line.supplier_id);
    const headerSupplier = Number(form.getFieldValue('supplier_id'));
    const supplierId =
      options?.supplierId != null && Number.isFinite(options.supplierId)
        ? Number(options.supplierId)
        : Number.isFinite(lineSupplier) && lineSupplier > 0
          ? lineSupplier
          : Number.isFinite(headerSupplier) && headerSupplier > 0
            ? headerSupplier
            : undefined;
    const shouldReprice = await purchaseLineQuantityChangeShouldReprice(material, {
      supplierId,
      asOf,
    });
    if (!shouldReprice) return;
  }

  const preserveSpecOnReprice = options?.trigger !== 'material';
  await applyPurchaseDocumentLineMaterialPricing(form, index, material, {
    materialList: options?.materialList,
    asOfField: options?.asOfField,
    unitPriceField: options?.unitPriceField,
    supplierId: options?.supplierId,
    fallbackTaxRate: options?.fallbackTaxRate,
    preserveUnitPriceWhenUnresolved: options?.trigger === 'quantity',
    preserveSpecSnapshot: preserveSpecOnReprice,
  });
}

export type SalesLineRepriceTrigger = 'material' | 'quantity' | 'partner' | 'asOf';

/**
 * 未锁定来源行：按数量/客户/日期重算销售单价（只动价税，不覆盖行规格快照）。
 * trigger=quantity 时仅阶梯价才重取；固定价禁止冲掉已录入单价。
 */
export async function repriceUnlockedSalesDocumentLineIfNeeded(
  form: FormWithLineItems | null | undefined,
  index: number,
  options?: {
    materialList?: Array<Material | Record<string, unknown>>;
    asOfField?: string;
    customerId?: number;
    material?: Material | Record<string, unknown>;
    trigger?: SalesLineRepriceTrigger;
  },
): Promise<void> {
  if (!form) return;
  const items = normalizeFormListItems<Record<string, unknown>>(form.getFieldValue('items'));
  const line = items[index];
  if (!line) return;
  if (isDocumentLineUnitPriceLocked(line) || line.pricing_snapshot != null) {
    const lockedPrice = Number(line.unit_price);
    if (Number.isFinite(lockedPrice) && lockedPrice > 0) {
      await refreshPartnerMaterialLineSnapshot(form, index, {
        side: 'sales',
        partnerId: options?.customerId,
        asOfField: options?.asOfField,
        materialList: options?.materialList,
        material: options?.material,
        overwrite: options?.trigger === 'partner',
      });
    }
    return;
  }

  const materialId = Number(line.material_id ?? line.materialId);
  if (!Number.isFinite(materialId) || materialId <= 0) return;

  const stub = options?.material ?? {
    id: materialId,
    uuid: readLineMaterialUuid(line),
  };
  const material = await resolveMaterialForPricing(stub, options?.materialList);

  if (options?.trigger === 'quantity') {
    const asOfField = options?.asOfField ?? 'order_date';
    const asOfRaw = form.getFieldValue(asOfField);
    const headerCustomer = Number(form.getFieldValue('customer_id'));
    const customerId =
      options?.customerId != null && Number.isFinite(options.customerId)
        ? Number(options.customerId)
        : Number.isFinite(headerCustomer) && headerCustomer > 0
          ? headerCustomer
          : undefined;
    const shouldReprice = await salesLineQuantityChangeShouldReprice(material, {
      customerId,
      asOf: formatAsOf(asOfRaw as string | dayjs.Dayjs),
    });
    if (!shouldReprice) return;
  }

  await applySalesDocumentLineMaterialPricing(form, index, material, {
    materialList: options?.materialList,
    asOfField: options?.asOfField,
    priceOnly: true,
  });
}
