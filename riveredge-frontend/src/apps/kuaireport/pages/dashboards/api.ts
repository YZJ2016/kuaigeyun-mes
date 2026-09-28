/**
 * 大屏接口。挂载后路径为 /api/v1/apps/kuaireport + 本文件相对路径。
 * data_source_id 用数据源的数字 id（后端 validate_widgets 要求 int），不用 uuid。
 */

import { apiRequest } from '../../../../services/api';
import type { DashboardWidget } from './DashboardWidgets';
import type { ShareResult } from '../reports/api';

const DASHBOARDS_BASE = '/apps/kuaireport/dashboards';

export interface DataSourceOption {
  id: number;
  uuid: string;
  name: string;
  type: string;
}

/** 已登记数据源。报表设计器用 uuid；大屏组件 data_source_id 用数字 id */
export function listDataSources(): Promise<DataSourceOption[]> {
  return apiRequest<DataSourceOption[]>('/apps/kuaireport/data-sources', { method: 'GET' });
}

export interface DashboardRow {
  id: number;
  code: string;
  name: string;
  status: string;
  is_shared: boolean;
  updated_at?: string;
}

export function listDashboards(): Promise<DashboardRow[]> {
  return apiRequest<DashboardRow[]>(DASHBOARDS_BASE, { method: 'GET' });
}

export interface DashboardDetail {
  id: number;
  code: string;
  name: string;
  status?: string;
  is_shared?: boolean;
  layout_config?: Record<string, unknown> | null;
  widgets_config?: DashboardWidget[];
  theme_config?: Record<string, unknown> | null;
  tv_config?: { rotate_seconds?: number } | null;
}

/** 后端无 GET /dashboards/{id} 详情端点，回显走 preview（返回同形态配置） */
export function getDashboardPreview(dashboardId: number): Promise<DashboardDetail> {
  return apiRequest<DashboardDetail>(`${DASHBOARDS_BASE}/${dashboardId}/preview`, {
    method: 'GET',
  });
}

export function createDashboard(data: {
  code: string;
  name: string;
  layout_config?: Record<string, unknown> | null;
  widgets_config?: DashboardWidget[];
  theme_config?: Record<string, unknown> | null;
  tv_config?: Record<string, unknown> | null;
}): Promise<DashboardRow> {
  return apiRequest<DashboardRow>(DASHBOARDS_BASE, { method: 'POST', data });
}

export function updateDashboard(
  dashboardId: number,
  data: {
    name: string;
    layout_config?: Record<string, unknown> | null;
    widgets_config?: DashboardWidget[];
    theme_config?: Record<string, unknown> | null;
    tv_config?: Record<string, unknown> | null;
  },
): Promise<DashboardRow> {
  return apiRequest<DashboardRow>(`${DASHBOARDS_BASE}/${dashboardId}`, {
    method: 'PUT',
    data,
  });
}

export function shareDashboard(
  dashboardId: number,
  body: { password: string; expires_at: string; allow_ip_cidrs?: string[] },
): Promise<ShareResult> {
  return apiRequest<ShareResult>(`${DASHBOARDS_BASE}/${dashboardId}/share`, {
    method: 'POST',
    data: body,
  });
}

export function closeDashboardShare(dashboardId: number): Promise<unknown> {
  return apiRequest(`${DASHBOARDS_BASE}/${dashboardId}/share`, { method: 'DELETE' });
}
