import { apiRequest } from '../../../services/api';

const BASE = '/apps/kuaielectronics/annual-training-plan-schema';

export type AnnualTrainingPlanField = {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
};

export type AnnualTrainingPlanSchemaSummary = {
  enabled: boolean;
  document_code?: string;
  document_title?: string;
  retention_years?: number;
  approval_slots?: string[];
  line_field_schema: AnnualTrainingPlanField[];
  source_note?: string;
};

export const annualTrainingPlanApi = {
  getSchema: async () =>
    (await apiRequest(`${BASE}`, { method: 'GET' })) as AnnualTrainingPlanSchemaSummary,
};
