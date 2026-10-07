/**
 * 星数采控制面。请求走现有 apiRequest，响应不含设备凭据。
 */

import { apiRequest } from '../../../services/api';

export type ConnectionOut = {
  id: number;
  uuid: string;
  code: string;
  name: string;
  connection_type: string;
  integration_id?: number | null;
  is_enabled: boolean;
  health_status: string;
};

export type DeviceOut = {
  id: number;
  uuid: string;
  connection_id?: number | null;
  external_device_id: string;
  code: string;
  name: string;
  equipment_uuid?: string | null;
  group_id?: number | null;
  is_online: boolean;
  last_seen_at?: string | null;
};

export type TagOut = {
  id: number;
  device_id: number;
  tag_key: string;
  name: string;
  value_type: string;
  map_target: string;
  is_enabled: boolean;
};

export type SnapshotOut = {
  id: number;
  device_id: number;
  tag_key: string;
  value_text?: string | null;
  value_number?: string | number | null;
  value_bool?: boolean | null;
  quality: string;
  sampled_at: string;
};

export function createConnection(payload: {
  code: string;
  name: string;
  connection_type: string;
  integration_uuid?: string;
  config?: Record<string, string>;
}): Promise<ConnectionOut> {
  return apiRequest<ConnectionOut>('/apps/kuaiiot/connections', { method: 'POST', data: payload });
}

export function listConnections(): Promise<ConnectionOut[]> {
  return apiRequest<ConnectionOut[]>('/apps/kuaiiot/connections');
}

export function createDevice(payload: {
  connection_id?: number;
  external_device_id: string;
  code: string;
  name: string;
  equipment_uuid?: string;
}): Promise<DeviceOut> {
  return apiRequest<DeviceOut>('/apps/kuaiiot/devices', { method: 'POST', data: payload });
}

export function listDevices(): Promise<DeviceOut[]> {
  return apiRequest<DeviceOut[]>('/apps/kuaiiot/devices');
}

export function createTag(
  deviceId: number,
  payload: { tag_key: string; name: string; value_type: string; map_target: string },
): Promise<TagOut> {
  return apiRequest<TagOut>(`/apps/kuaiiot/devices/${deviceId}/tags`, { method: 'POST', data: payload });
}

export function listSnapshots(deviceId: number): Promise<SnapshotOut[]> {
  return apiRequest<SnapshotOut[]>(`/apps/kuaiiot/devices/${deviceId}/snapshots`);
}

export type TemplateOut = {
  code: string;
  name: string;
  tags: Array<{ tag_key: string; name: string; value_type: string; map_target: string; unit?: string | null }>;
};

export type AlertOut = {
  id: number;
  rule_id: number | null;
  device_id: number;
  tag_key: string;
  severity: string;
  message: string;
  actual_value?: string | null;
  status: string;
  triggered_at: string;
  acknowledged_at?: string | null;
  recovered_at?: string | null;
  closed_at?: string | null;
};

export function listTemplates(): Promise<TemplateOut[]> {
  return apiRequest<TemplateOut[]>('/apps/kuaiiot/tag-templates');
}

export function applyTemplate(deviceId: number, code: string): Promise<{ code: string; tag_keys: string[] }> {
  return apiRequest(`/apps/kuaiiot/devices/${deviceId}/template`, { method: 'POST', data: { code } });
}

export function listAlerts(): Promise<AlertOut[]> {
  return apiRequest<AlertOut[]>('/apps/kuaiiot/alerts');
}

export function transitionAlert(id: number, action: 'acknowledge' | 'close'): Promise<AlertOut> {
  return apiRequest(`/apps/kuaiiot/alerts/${id}/${action}`, { method: 'POST' });
}

export function createAlertRule(payload: {
  code: string;
  name: string;
  tag_key: string;
  operator: string;
  threshold_number?: number;
  device_id?: number;
  cooldown_seconds?: number;
  notify_enabled?: boolean;
}): Promise<unknown> {
  return apiRequest('/apps/kuaiiot/alert-rules', { method: 'POST', data: payload });
}

export type ProductTag = {
  tag_key: string;
  name: string;
  value_type: string;
  map_target: string;
  unit?: string;
};

export type ProductEvent = {
  event_key: string;
  name: string;
  severity: string;
  message?: string;
};

export type ProductFunction = {
  function_key: string;
  name: string;
  timeout_seconds?: number;
  params?: Array<{ key: string; name?: string; value_type?: string; required?: boolean }>;
  edge_action?: {
    type?: string;
    param_key?: string;
    address?: number;
    data_type?: string;
    scale?: number;
  };
};

export type ProductOut = {
  id: number;
  uuid: string;
  code: string;
  name: string;
  description?: string | null;
  tags: ProductTag[];
  events?: ProductEvent[];
  functions?: ProductFunction[];
};

export type BatchDeviceOut = {
  id: number;
  code: string;
  name: string;
  product_id: number;
  device_token: string;
};

export type TrendPoint = {
  time: string;
  value: number;
};

export function createProduct(payload: {
  code: string;
  name: string;
  description?: string;
  tags: ProductTag[];
}): Promise<ProductOut> {
  return apiRequest<ProductOut>('/apps/kuaiiot/products', { method: 'POST', data: payload });
}

export function listProducts(): Promise<ProductOut[]> {
  return apiRequest<ProductOut[]>('/apps/kuaiiot/products');
}

export function updateProduct(
  productId: number,
  payload: { events?: ProductEvent[]; functions?: ProductFunction[]; name?: string },
): Promise<ProductOut> {
  return apiRequest<ProductOut>(`/apps/kuaiiot/products/${productId}`, { method: 'PUT', data: payload });
}

export type DeviceGroup = {
  id: number;
  uuid: string;
  code: string;
  name: string;
  parent_id?: number | null;
  sort_order: number;
  remark?: string | null;
};

export function listDeviceGroups(): Promise<DeviceGroup[]> {
  return apiRequest<DeviceGroup[]>('/apps/kuaiiot/device-groups');
}

export function createDeviceGroup(payload: {
  code: string;
  name: string;
  parent_id?: number;
  sort_order?: number;
}): Promise<DeviceGroup> {
  return apiRequest<DeviceGroup>('/apps/kuaiiot/device-groups', { method: 'POST', data: payload });
}

export function assignDeviceGroup(deviceId: number, groupId: number | null): Promise<{ device_id: number; group_id: number | null }> {
  return apiRequest(`/apps/kuaiiot/devices/${deviceId}/group`, { method: 'PUT', data: { group_id: groupId } });
}

export type DeviceCommand = {
  id: number;
  uuid: string;
  device_id: number;
  function_key: string;
  params: Record<string, unknown>;
  dispatch_channel: string;
  status: string;
  result?: Record<string, unknown> | null;
  error_message?: string | null;
  sent_at?: string | null;
  completed_at?: string | null;
  expires_at?: string | null;
};

export function listDeviceCommands(deviceId: number): Promise<DeviceCommand[]> {
  return apiRequest<DeviceCommand[]>(`/apps/kuaiiot/devices/${deviceId}/commands`);
}

export function createDeviceCommand(
  deviceId: number,
  payload: { function_key: string; params?: Record<string, unknown> },
): Promise<DeviceCommand> {
  return apiRequest<DeviceCommand>(`/apps/kuaiiot/devices/${deviceId}/commands`, { method: 'POST', data: payload });
}

export type MessageLog = {
  id: number;
  uuid: string;
  device_id: number;
  direction: string;
  msg_type: string;
  payload?: Record<string, unknown> | null;
  result: string;
  error_message?: string | null;
  created_at: string;
};

export function listMessageLogs(deviceId?: number): Promise<MessageLog[]> {
  return apiRequest<MessageLog[]>('/apps/kuaiiot/message-logs', {
    params: deviceId ? { device_id: deviceId } : undefined,
  });
}

export function batchCreateDevices(payload: {
  product_id: number;
  name_prefix: string;
  code_prefix: string;
  count: number;
}): Promise<BatchDeviceOut[]> {
  return apiRequest<BatchDeviceOut[]>('/apps/kuaiiot/device-batches', { method: 'POST', data: payload });
}

export function queryTrend(params: {
  device_id: number;
  tag_key: string;
  start: string;
  stop: string;
}): Promise<TrendPoint[]> {
  return apiRequest<TrendPoint[]>('/apps/kuaiiot/trends', { params });
}
