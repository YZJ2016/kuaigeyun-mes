import { apiRequest } from '../../../services/api';

export interface GlExchangeRate {
  id: number;
  tenant_id: number;
  currency_code: string;
  effective_date: string;
  rate: number;
  notes?: string | null;
  created_at?: string;
  updated_at?: string;
  created_by?: number | null;
  created_by_name?: string | null;
  updated_by?: number | null;
  updated_by_name?: string | null;
}

export interface GlExchangeRateListParams {
  skip?: number;
  limit?: number;
  currency_code?: string;
  effective_start?: string;
  effective_end?: string;
  keyword?: string;
  sort_field?: string;
  sort_order?: string;
}

export interface GlExchangeRateLookupResult {
  currency_code: string;
  as_of_date: string;
  found: boolean;
  rate?: number | null;
}

export interface GlExchangeRateBatchResult {
  effective_date: string;
  base_currency: string;
  source?: string;
  created: number;
  updated: number;
  skipped: number;
  unavailable: string[];
}

export interface GlExchangeRateSource {
  code: string;
  label: string;
  description: string;
  is_default?: boolean;
}

const API = '/apps/kuaicaiwu/exchange-rates';

export const exchangeRateService = {
  list: async (params?: GlExchangeRateListParams) => {
    const res = await apiRequest<{ items?: GlExchangeRate[]; total?: number }>(API, {
      method: 'GET',
      params,
    });
    const items = Array.isArray(res) ? res : res?.items ?? [];
    const total = Array.isArray(res) ? res.length : res?.total ?? items.length;
    return { items, total };
  },

  create: (data: {
    currency_code: string;
    effective_date: string;
    rate: number;
    notes?: string;
  }) => apiRequest<GlExchangeRate>(API, { method: 'POST', data }),

  update: (
    id: number,
    data: Partial<{
      currency_code: string;
      effective_date: string;
      rate: number;
      notes: string | null;
    }>,
  ) => apiRequest<GlExchangeRate>(`${API}/${id}`, { method: 'PUT', data }),

  delete: (id: number) => apiRequest<void>(`${API}/${id}`, { method: 'DELETE' }),

  lookup: (params: { currency_code: string; as_of_date: string }) =>
    apiRequest<GlExchangeRateLookupResult>(`${API}/lookup`, { method: 'GET', params }),

  listReferenceSources: async () => {
    const res = await apiRequest<{ items?: GlExchangeRateSource[]; default?: string }>(
      `${API}/reference-sources`,
      { method: 'GET' },
    );
    return {
      items: res?.items ?? [],
      default: res?.default || 'cfets',
    };
  },

  presetCommon: (data?: { source?: string }) =>
    apiRequest<GlExchangeRateBatchResult>(`${API}/preset-common`, {
      method: 'POST',
      data: data ?? {},
    }),

  fetchReference: (data?: {
    effective_date?: string;
    currency_codes?: string[];
    source?: string;
  }) =>
    apiRequest<GlExchangeRateBatchResult>(`${API}/fetch-reference`, {
      method: 'POST',
      data: data ?? {},
    }),
};
