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
  category: 'system' | 'custom' | string;
  classify: string;
  is_system: boolean;
  status: string;
  is_shared: boolean;
  report_config: ReportConfigSchema;
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
