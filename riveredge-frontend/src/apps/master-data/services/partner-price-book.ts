import { api } from '../../../services/api';
import type {
  PartnerPriceBook,
  PartnerPriceBookBulkCreate,
  PartnerPriceBookBulkResponse,
  PartnerPriceBookCreate,
  PartnerPriceBookListParams,
  PartnerPriceBookListResponse,
  PartnerPriceBookType,
  PartnerPriceBookUpdate,
  PartnerPriceResolveBatchRequest,
  PartnerPriceResolveBatchResponse,
  PartnerPriceResolveResult,
} from '../types/partner-price-book';

function resourcePath(partnerType: PartnerPriceBookType): string {
  return partnerType === 'customer' ? 'customer-price-books' : 'supplier-price-books';
}

export function createPartnerPriceBookApi(partnerType: PartnerPriceBookType) {
  const base = `/apps/master-data/supply-chain/${resourcePath(partnerType)}`;

  return {
    create: (data: PartnerPriceBookCreate): Promise<PartnerPriceBook> => api.post(base, data),
    list: (params?: PartnerPriceBookListParams): Promise<PartnerPriceBookListResponse> =>
      api.get(base, { params }),
    get: (uuid: string): Promise<PartnerPriceBook> => api.get(`${base}/${uuid}`),
    update: (uuid: string, data: PartnerPriceBookUpdate): Promise<PartnerPriceBook> =>
      api.put(`${base}/${uuid}`, data),
    delete: (uuid: string): Promise<void> => api.delete(`${base}/${uuid}`),
    resolve: (params: {
      partnerId: number;
      materialId?: number;
      partnerMaterialCode?: string;
      variantAttributes?: Record<string, unknown>;
      asOf?: string;
      quantity?: number;
      resolveMode?: 'auto' | 'standard_only' | 'tier_only';
    }): Promise<PartnerPriceResolveResult> => {
      const needsPost =
        (params.variantAttributes && Object.keys(params.variantAttributes).length > 0) ||
        params.quantity != null ||
        params.resolveMode != null;
      if (needsPost) {
        return api.post(`${base}/resolve`, {
          partnerId: params.partnerId,
          materialId: params.materialId,
          partnerMaterialCode: params.partnerMaterialCode,
          variantAttributes: params.variantAttributes,
          asOf: params.asOf,
          quantity: params.quantity,
          resolveMode: params.resolveMode,
        });
      }
      return api.get(`${base}/resolve`, { params });
    },
    resolveBatch: (data: PartnerPriceResolveBatchRequest): Promise<PartnerPriceResolveBatchResponse> =>
      api.post(`${base}/resolve-batch`, data),
    bulkCreate: (data: PartnerPriceBookBulkCreate): Promise<PartnerPriceBookBulkResponse> =>
      api.post(`${base}/bulk`, data),
    /** 列表筛选：仅返回价格本中已有数据的客户/供应商 */
    listPartnersWithData: (): Promise<{ data: { id: number; code?: string; name?: string }[] }> =>
      api.get(`${base}/partners-with-data`),
  };
}

export const customerPriceBookApi = createPartnerPriceBookApi('customer');
export const supplierPriceBookApi = createPartnerPriceBookApi('supplier');

export type PartnerMaterialLinePriceResolveParams = {
  side: 'purchase' | 'sales';
  partnerId: number;
  materialId: number;
  quantity?: number;
  asOf?: string;
  variantAttributes?: Record<string, unknown>;
};

export type PartnerMaterialLinePriceResolveResult = {
  found: boolean;
  unitPrice?: number;
  taxRate?: number;
  priceSource?: string;
  currencyCode?: string;
  partnerMaterialCode?: string;
  partnerMaterialName?: string;
};

export function resolvePartnerMaterialLinePrice(
  params: PartnerMaterialLinePriceResolveParams,
): Promise<PartnerMaterialLinePriceResolveResult> {
  return api.post('/apps/master-data/supply-chain/resolve-partner-material-line-price', params);
}

export type PartnerMaterialLinePriceBatchItem = {
  materialId: number;
  quantity?: number;
  variantAttributes?: Record<string, unknown>;
};

export type PartnerMaterialLinePriceBatchParams = {
  side: 'purchase' | 'sales';
  partnerId: number;
  asOf?: string;
  items: PartnerMaterialLinePriceBatchItem[];
};

export function resolvePartnerMaterialLinePriceBatch(
  params: PartnerMaterialLinePriceBatchParams,
): Promise<{ items: PartnerMaterialLinePriceResolveResult[] }> {
  return api.post('/apps/master-data/supply-chain/resolve-partner-material-line-price-batch', params);
}
