import { apiRequest } from '../../../services/api';

export type RelayLineCapacity = {
  id: number;
  production_line_id: number;
  production_line_code?: string | null;
  production_line_name?: string | null;
  takt_seconds: number;
  daily_capacity_qty: number;
  changeover_minutes_default: number;
  is_active: boolean;
  remarks?: string | null;
};

export type RelayChangeover = {
  id: number;
  from_family: string;
  to_family: string;
  changeover_minutes: number;
  forbid_same_line: boolean;
  remarks?: string | null;
};

export type RelayLineOutput = {
  production_line_id: number;
  production_line_code?: string | null;
  production_line_name?: string | null;
  daily_capacity_qty: number;
  planned_quantity?: number;
  output_qualified: number;
  achievement_rate: number;
  plan_achievement_rate?: number;
};

export type RelayModuleStatus = {
  output_basis: string;
  resource_mode: string;
  line_exclusive: boolean;
  host_defaults_applied: boolean;
  tables_ready: boolean;
  line_capacity_count: number;
  changeover_count: number;
  hints?: string[];
};

export type RelayAutoReportConfig = {
  id: number;
  is_enabled: boolean;
  match_by_device: boolean;
  interval_minutes: number;
  report_mode: string;
  offline_threshold_seconds: number;
  reporter_user_id?: number | null;
  reporter_user_name?: string | null;
  remarks?: string | null;
};

export type RelayAutoReportBinding = {
  id: number;
  iot_device_id: number;
  iot_device_uuid?: string | null;
  iot_device_code?: string | null;
  iot_device_name?: string | null;
  external_device_id?: string | null;
  equipment_uuid: string;
  equipment_id?: number | null;
  equipment_code?: string | null;
  equipment_name?: string | null;
  is_enabled: boolean;
  last_zscl?: number | null;
  pending_quantity: number;
  baseline_aligned: boolean;
  bound_work_order_id?: number | null;
  bound_work_order_code?: string | null;
  bound_operation_id?: number | null;
  bound_operation_name?: string | null;
  last_settle_at?: string | null;
  last_seen_at?: string | null;
  offline_flushed: boolean;
  remarks?: string | null;
};

export type RelayAutoReportDeviceOption = {
  iot_device_id: number;
  iot_device_uuid?: string;
  iot_device_code?: string;
  iot_device_name?: string;
  external_device_id?: string;
  equipment_uuid: string;
  equipment_id: number;
  equipment_code?: string;
  equipment_name?: string;
  is_online?: boolean;
  label: string;
};

export type RelayAutoReportLog = {
  id: number;
  binding_id?: number | null;
  iot_device_id?: number | null;
  level: string;
  event: string;
  message?: string | null;
  zscl?: number | null;
  increment_qty?: number | null;
  work_order_id?: number | null;
  work_order_code?: string | null;
  operation_id?: number | null;
  reporting_record_id?: number | null;
  created_at?: string | null;
};

export const industryRelayApi = {
  getStatus: () => apiRequest<RelayModuleStatus>('/apps/ind-relay/status', { method: 'GET' }),
  reapplyDefaults: () =>
    apiRequest<RelayModuleStatus>('/apps/ind-relay/status/reapply-defaults', { method: 'POST' }),
  listLineCapacities: () =>
    apiRequest<RelayLineCapacity[]>('/apps/ind-relay/line-capacities', { method: 'GET' }),
  createLineCapacity: (data: {
    production_line_id: number;
    takt_seconds?: number;
    daily_capacity_qty?: number;
    changeover_minutes_default?: number;
    remarks?: string;
  }) =>
    apiRequest<RelayLineCapacity>('/apps/ind-relay/line-capacities', { method: 'POST', data }),
  updateLineCapacity: (
    id: number,
    data: {
      takt_seconds?: number;
      daily_capacity_qty?: number;
      changeover_minutes_default?: number;
      is_active?: boolean;
      remarks?: string;
    }
  ) =>
    apiRequest<RelayLineCapacity>(`/apps/ind-relay/line-capacities/${id}`, {
      method: 'PATCH',
      data,
    }),
  listChangeovers: () =>
    apiRequest<RelayChangeover[]>('/apps/ind-relay/changeovers', { method: 'GET' }),
  createChangeover: (data: {
    from_family: string;
    to_family: string;
    changeover_minutes?: number;
    forbid_same_line?: boolean;
    remarks?: string;
  }) => apiRequest<RelayChangeover>('/apps/ind-relay/changeovers', { method: 'POST', data }),
  updateChangeover: (
    id: number,
    data: {
      changeover_minutes?: number;
      forbid_same_line?: boolean;
      remarks?: string;
    }
  ) =>
    apiRequest<RelayChangeover>(`/apps/ind-relay/changeovers/${id}`, { method: 'PATCH', data }),
  deleteChangeover: (id: number) =>
    apiRequest<{ ok: boolean }>(`/apps/ind-relay/changeovers/${id}`, { method: 'DELETE' }),
  listLineOutput: (params?: { date_start?: string; date_end?: string }) =>
    apiRequest<RelayLineOutput[]>('/apps/ind-relay/line-output', { method: 'GET', params }),
  getAutoReportConfig: () =>
    apiRequest<RelayAutoReportConfig>('/apps/ind-relay/auto-report/config', { method: 'GET' }),
  updateAutoReportConfig: (data: Partial<RelayAutoReportConfig> & { reporter_user_id?: number | null }) =>
    apiRequest<RelayAutoReportConfig>('/apps/ind-relay/auto-report/config', { method: 'PUT', data }),
  listAutoReportDeviceOptions: async () => {
    const res = await apiRequest<{ items: RelayAutoReportDeviceOption[] }>(
      '/apps/ind-relay/auto-report/device-options',
      { method: 'GET' },
    );
    return res.items || [];
  },
  listAutoReportBindings: () =>
    apiRequest<RelayAutoReportBinding[]>('/apps/ind-relay/auto-report/bindings', { method: 'GET' }),
  createAutoReportBinding: (data: { iot_device_id: number; is_enabled?: boolean; remarks?: string }) =>
    apiRequest<RelayAutoReportBinding>('/apps/ind-relay/auto-report/bindings', {
      method: 'POST',
      data,
    }),
  updateAutoReportBinding: (id: number, data: { is_enabled?: boolean; remarks?: string }) =>
    apiRequest<RelayAutoReportBinding>(`/apps/ind-relay/auto-report/bindings/${id}`, {
      method: 'PATCH',
      data,
    }),
  deleteAutoReportBinding: (id: number) =>
    apiRequest<{ ok: boolean }>(`/apps/ind-relay/auto-report/bindings/${id}`, { method: 'DELETE' }),
  listAutoReportLogs: (params?: { binding_id?: number; skip?: number; limit?: number }) =>
    apiRequest<{ total: number; items: RelayAutoReportLog[] }>('/apps/ind-relay/auto-report/logs', {
      method: 'GET',
      params,
    }),
  settleAutoReportNow: () =>
    apiRequest<Record<string, unknown>>('/apps/ind-relay/auto-report/settle-now', { method: 'POST' }),
};
