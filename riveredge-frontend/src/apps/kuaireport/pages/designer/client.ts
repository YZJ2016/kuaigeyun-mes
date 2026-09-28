import type { ReportConfigSchema } from '../../../../components/uni-report/types';
import { apiRequest } from '../../../../services/api';

export interface DesignerFieldInput {
  field: string;
  label: string;
  format?: string;
  width?: number;
  visible?: boolean;
}

export interface DesignerFilterInput {
  field: string;
  label: string;
  operator?: string;
  default_value?: unknown;
  required?: boolean;
}

export interface DesignerSaveBody {
  code: string;
  name: string;
  page_size: number;
  data_source_uuid: string;
  fields: DesignerFieldInput[];
  filters: DesignerFilterInput[];
  summary_fields: string[];
  note?: string;
  report_id?: number;
}

export interface DesignerReport {
  report_id: number;
  category: string;
  code: string;
  name: string;
  current_version: number;
  version_no?: number | null;
  report_config: ReportConfigSchema;
  data_source_uuid?: string | null;
}

export function saveDesignerReport(body: DesignerSaveBody): Promise<DesignerReport> {
  return apiRequest<DesignerReport>('/apps/kuaireport/designer/reports', {
    method: 'POST',
    data: body,
  });
}

export function loadDesignerReport(reportId: number): Promise<DesignerReport> {
  return apiRequest<DesignerReport>(`/apps/kuaireport/designer/reports/${reportId}`);
}
