/**
 * 报表中心接口。全量 Excel 走星报表后端，不走浏览器 CSV。
 * 挂载后路径为 /api/v1/apps/kuaireport + 本文件相对路径。
 */

import { getTenantId, getToken } from '../../../../utils/auth';
import { decrementPendingRequests, incrementPendingRequests, updateLastActivity } from '../../../../utils/activityUtils';
import { apiRequest } from '../../../../services/api';
import type { ReportConfigSchema } from '../../../../components/uni-report';

const REPORTS_BASE = '/apps/kuaireport/reports';

export interface ReportCenterRow {
  id: number;
  uuid: string;
  code: string;
  name: string;
  description?: string | null;
  category: 'system' | 'custom' | string;
  classify: string;
  is_system: boolean;
  status: string;
  is_shared: boolean;
  updated_at?: string | null;
  report_config: ReportConfigSchema;
}

export interface ReportMountState {
  mounted: boolean;
  menu_uuid?: string | null;
  menu_name?: string | null;
  parent_uuid?: string | null;
}

export function listReports(params: {
  status?: string;
  category?: string;
  classify?: string;
}): Promise<ReportCenterRow[]> {
  return apiRequest<ReportCenterRow[]>(REPORTS_BASE, { params });
}

export function getReport(reportId: number): Promise<ReportCenterRow> {
  return apiRequest<ReportCenterRow>(`${REPORTS_BASE}/${reportId}`);
}

export interface WizardSaveBody {
  code: string;
  name: string;
  description?: string | null;
  category: 'custom' | 'system';
  classify?: string;
  report_config: ReportCenterRow['report_config'];
  status: 'DRAFT' | 'PUBLISHED';
}

export function createWizardReport(body: WizardSaveBody): Promise<ReportCenterRow> {
  return apiRequest<ReportCenterRow>(REPORTS_BASE, { method: 'POST', data: body });
}

export function updateWizardReport(reportId: number, body: WizardSaveBody): Promise<ReportCenterRow> {
  return apiRequest<ReportCenterRow>(`${REPORTS_BASE}/${reportId}`, { method: 'PUT', data: body });
}

export function detectDatasetFields(datasetUuid: string): Promise<{
  fields: Array<{ field: string; label: string; visible?: boolean }>;
  success: boolean;
}> {
  return apiRequest(`${REPORTS_BASE}/datasets/fields`, { params: { dataset_uuid: datasetUuid } });
}

export function previewDataset(body: {
  dataset_uuid: string;
  dataset_code?: string;
  chart_type: string;
  page_size?: number;
}): Promise<{ data: Record<string, unknown>[]; total?: number; success: boolean }> {
  return apiRequest(`${REPORTS_BASE}/preview`, { method: 'POST', data: body });
}

export function publishReport(reportId: number): Promise<ReportCenterRow> {
  return apiRequest<ReportCenterRow>(`${REPORTS_BASE}/${reportId}/publish`, {
    method: 'POST',
  });
}

/** 分享响应只回路径与过期时间，不回口令或哈希 */
export interface ShareResult {
  is_shared: boolean;
  share_path: string;
  expires_at?: string;
}

export function shareReport(
  reportId: number,
  body: { password: string; expires_at: string; allow_ip_cidrs?: string[] },
): Promise<ShareResult> {
  return apiRequest<ShareResult>(`${REPORTS_BASE}/${reportId}/share`, {
    method: 'POST',
    data: body,
  });
}

export function closeReportShare(reportId: number): Promise<unknown> {
  return apiRequest(`${REPORTS_BASE}/${reportId}/share`, { method: 'DELETE' });
}

/** 报表中心「分享」：免登录链接，不传口令。 */
export function createPublicLink(reportId: number): Promise<ShareResult> {
  return apiRequest<ShareResult>(`${REPORTS_BASE}/${reportId}/public-link`, { method: 'POST' });
}

export function withdrawReport(reportId: number): Promise<ReportCenterRow> {
  return apiRequest<ReportCenterRow>(`${REPORTS_BASE}/${reportId}/withdraw`, { method: 'POST' });
}

export function deleteReport(reportId: number): Promise<{ success: boolean }> {
  return apiRequest<{ success: boolean }>(`${REPORTS_BASE}/${reportId}`, { method: 'DELETE' });
}

export function getReportMount(reportId: number): Promise<ReportMountState> {
  return apiRequest<ReportMountState>(`${REPORTS_BASE}/${reportId}/mount`);
}

export function mountReport(
  reportId: number,
  body: { parent_uuid: string; menu_name: string },
): Promise<ReportMountState> {
  return apiRequest<ReportMountState>(`${REPORTS_BASE}/${reportId}/mount`, {
    method: 'POST',
    data: body,
  });
}

export function clearReportMount(reportId: number): Promise<ReportMountState> {
  return apiRequest<ReportMountState>(`${REPORTS_BASE}/${reportId}/mount`, { method: 'DELETE' });
}

export async function downloadFullExcel(
  reportId: number,
  filters: Record<string, unknown>,
): Promise<Blob> {
  updateLastActivity(true);
  incrementPendingRequests();
  try {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    };
    const tenantId = getTenantId();
    if (tenantId != null) {
      headers['X-Tenant-ID'] = String(tenantId);
    }
    const response = await fetch(`/api/v1${REPORTS_BASE}/${reportId}/excel`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ filters }),
    });
    if (!response.ok) {
      throw new Error('全量 Excel 导出失败');
    }
    return response.blob();
  } finally {
    updateLastActivity(true);
    decrementPendingRequests();
  }
}
