/** 客户/供应商价格本类型 */

export type PartnerPriceBookType = 'customer' | 'supplier';

export interface PartnerPriceVariantLine {
  variantAttributes: Record<string, unknown>;
  unitPrice: number;
}

export interface PartnerPriceTierLine {
  minQuantity: number;
  maxQuantity?: number | null;
  unitPrice: number;
}

export interface PartnerPriceBook {
  id: number;
  uuid: string;
  tenantId: number;
  partnerType: PartnerPriceBookType;
  partnerId: number;
  partnerCode?: string;
  partnerName?: string;
  materialId: number;
  materialCode?: string;
  materialName?: string;
  partnerMaterialCode?: string;
  partnerMaterialName?: string;
  unitPrice?: number;
  priceType?: 'tax_inclusive' | 'tax_exclusive';
  variantPrices?: PartnerPriceVariantLine[];
  tierPrices?: PartnerPriceTierLine[];
  currencyCode?: string;
  taxRate?: number;
  unit?: string;
  effectiveFrom?: string;
  effectiveTo?: string;
  remark?: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface PartnerPriceBookCreate {
  partnerId: number;
  materialId: number;
  unitPrice?: number;
  priceType?: 'tax_inclusive' | 'tax_exclusive';
  variantPrices?: PartnerPriceVariantLine[];
  tierPrices?: PartnerPriceTierLine[];
  currencyCode?: string;
  taxRate?: number;
  unit?: string;
  /** null/省略 = 不限，一直生效 */
  effectiveFrom?: string | null;
  /** null/省略 = 不限，一直生效 */
  effectiveTo?: string | null;
  remark?: string;
  isActive?: boolean;
  /** 无编号映射时可提交，保存后回写 MaterialCodeAlias */
  partnerMaterialCode?: string;
  partnerMaterialName?: string;
  /** 默认 true；已有映射时不写入 */
  syncPartnerAlias?: boolean;
}

export interface PartnerPriceBookUpdate extends Partial<PartnerPriceBookCreate> {}

export interface PartnerPriceBookListParams {
  skip?: number;
  limit?: number;
  partnerId?: number;
  materialId?: number;
  keyword?: string;
  activeOnly?: boolean;
  effectiveOn?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
  created_start_date?: string;
  created_end_date?: string;
  updated_start_date?: string;
  updated_end_date?: string;
}

export interface PartnerPriceBookListResponse {
  data: PartnerPriceBook[];
  total: number;
}

export interface PartnerPriceResolveResult {
  found: boolean;
  unitPrice?: number;
  isVariantPrice?: boolean;
  isTierPrice?: boolean;
  priceSource?: string;
  currencyCode?: string;
  taxRate?: number;
  unit?: string;
  materialId?: number;
  partnerMaterialCode?: string;
  partnerMaterialName?: string;
  priceBookUuid?: string;
}

export interface PartnerPriceResolveBatchLineRequest {
  materialId: number;
  variantAttributes?: Record<string, unknown>;
  quantity?: number;
}

export interface PartnerPriceResolveBatchRequest {
  partnerId: number;
  materialIds?: number[];
  items?: PartnerPriceResolveBatchLineRequest[];
  asOf?: string;
}

export interface PartnerPriceResolveBatchResponse {
  items: PartnerPriceResolveResult[];
}

export interface PartnerPriceBookBulkLine {
  materialId: number;
  unitPrice?: number;
  tierPrices?: PartnerPriceTierLine[];
  unit?: string;
  partnerMaterialCode?: string;
  partnerMaterialName?: string;
}

export type PartnerPriceBookBulkConflictPolicy = 'skip' | 'overwrite';

export interface PartnerPriceBookBulkCreate {
  partnerIds: number[];
  lines: PartnerPriceBookBulkLine[];
  priceType?: 'tax_inclusive' | 'tax_exclusive';
  taxRate?: number;
  effectiveFrom?: string;
  effectiveTo?: string;
  remark?: string;
  isActive?: boolean;
  /** 有伙伴料号时回写物料编号映射（仅尚无映射时） */
  syncPartnerAlias?: boolean;
  conflictPolicy?: PartnerPriceBookBulkConflictPolicy | null;
}

export interface PartnerPriceBookBulkConflictItem {
  partnerId: number;
  partnerCode?: string;
  partnerName?: string;
  materialId: number;
  materialCode?: string;
  materialName?: string;
  existingUuid: string;
}

export interface PartnerPriceBookBulkResponse {
  createdCount: number;
  skippedCount: number;
  overwrittenCount: number;
}
