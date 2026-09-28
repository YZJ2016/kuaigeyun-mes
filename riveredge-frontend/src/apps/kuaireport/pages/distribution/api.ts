import { apiRequest } from '../../../../services/api';

const base = '/apps/kuaireport/distribution';

export type ResourceType = 'report' | 'dashboard';

export function grantShare(data: {
  resource_type: ResourceType;
  resource_id: number;
  role_id: number;
  permission?: string;
}) {
  return apiRequest(`${base}/grants`, { method: 'POST', data });
}

export function canView(resourceType: ResourceType, resourceId: number) {
  return apiRequest(`${base}/grants/can-view`, {
    method: 'GET',
    params: { resource_type: resourceType, resource_id: resourceId },
  });
}

export function createSubscription(data: {
  report_id: number;
  name: string;
  recipient_user_ids: number[];
  cron?: string;
  channel?: 'inbox';
  attach_excel?: boolean;
  is_active?: boolean;
}) {
  return apiRequest(`${base}/subscriptions`, { method: 'POST', data });
}

export function listReportVersions(reportId: number) {
  return apiRequest(`${base}/reports/${reportId}/versions`, { method: 'GET' });
}

export function restoreReportVersion(reportId: number, versionNo: number) {
  return apiRequest(`${base}/reports/${reportId}/versions/${versionNo}/restore`, {
    method: 'POST',
  });
}

export function backfillDashboards() {
  return apiRequest(`${base}/dashboards/backfill-versions`, { method: 'POST' });
}

export function listDashboardVersions(dashboardId: number) {
  return apiRequest(`${base}/dashboards/${dashboardId}/versions`, { method: 'GET' });
}

export function restoreDashboardVersion(dashboardId: number, versionNo: number) {
  return apiRequest(`${base}/dashboards/${dashboardId}/versions/${versionNo}/restore`, {
    method: 'POST',
  });
}
