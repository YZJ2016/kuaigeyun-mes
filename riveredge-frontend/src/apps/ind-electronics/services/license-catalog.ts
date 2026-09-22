import { apiRequest } from '../../../services/api';

const BASE = '/apps/ind-electronics/license-catalog';

export type LicenseCatalogItem = {
  item_code?: string;
  item_name: string;
  license_type: string;
  renewal_frequency?: string;
  default_reminder_days?: number;
};

export type LicenseCatalogSummary = {
  enabled: boolean;
  default_reminder_days?: number;
  item_count?: number;
  items: LicenseCatalogItem[];
  source_note?: string;
};

export type ApplyLicenseCatalogStubsResult = {
  success: boolean;
  created: number;
  skipped: number;
};

export const licenseCatalogApi = {
  getSummary: async () =>
    (await apiRequest(`${BASE}`, { method: 'GET' })) as LicenseCatalogSummary,
  applyStubs: async () =>
    (await apiRequest(`${BASE}/apply-stubs`, { method: 'POST' })) as ApplyLicenseCatalogStubsResult,
};
