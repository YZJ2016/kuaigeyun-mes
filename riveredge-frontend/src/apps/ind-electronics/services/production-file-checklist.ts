import { apiRequest } from '../../../services/api';

const BASE = '/apps/ind-electronics/production-file-checklist';

export type ProductionFileChecklistItem = {
  item_code: string;
  priority?: string;
  item_name: string;
  purpose?: string;
  host_module?: string;
  catalog_kind?: string;
  file_types?: string[];
  notes?: string;
};

export type ProductionFileChecklistSummary = {
  enabled: boolean;
  item_count?: number;
  production_file_item_count?: number;
  items: ProductionFileChecklistItem[];
  production_file_items?: ProductionFileChecklistItem[];
  source_note?: string;
};

export const productionFileChecklistApi = {
  getSummary: async () =>
    (await apiRequest(`${BASE}`, { method: 'GET' })) as ProductionFileChecklistSummary,
};
