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
  product_id?: number | null;
  remark?: string | null;
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
  return apiRequest<ConnectionOut>('/apps/kuaiiot/registry/connections', { method: 'POST', data: payload });
}

export function listConnections(): Promise<ConnectionOut[]> {
  return apiRequest<ConnectionOut[]>('/apps/kuaiiot/registry/connections');
}

export function getConnection(connectionId: number): Promise<ConnectionOut> {
  return apiRequest<ConnectionOut>(`/apps/kuaiiot/registry/connections/${connectionId}`);
}

export function updateConnection(
  connectionId: number,
  payload: {
    name?: string;
    config?: Record<string, string> | null;
    is_enabled?: boolean;
    remark?: string | null;
  },
): Promise<ConnectionOut> {
  return apiRequest<ConnectionOut>(`/apps/kuaiiot/registry/connections/${connectionId}`, {
    method: 'PUT',
    data: payload,
  });
}

export function deleteConnection(connectionId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/registry/connections/${connectionId}`, { method: 'DELETE' });
}

export function createDevice(payload: {
  connection_id?: number;
  external_device_id: string;
  code: string;
  name: string;
  equipment_uuid?: string;
}): Promise<DeviceOut> {
  return apiRequest<DeviceOut>('/apps/kuaiiot/registry/devices', { method: 'POST', data: payload });
}

export function listDevices(): Promise<DeviceOut[]> {
  return apiRequest<DeviceOut[]>('/apps/kuaiiot/registry/devices');
}

export function getDevice(deviceId: number): Promise<DeviceOut> {
  return apiRequest<DeviceOut>(`/apps/kuaiiot/registry/devices/${deviceId}`);
}

export function updateDevice(
  deviceId: number,
  payload: {
    name?: string;
    connection_id?: number | null;
    equipment_uuid?: string;
    clear_equipment?: boolean;
    group_id?: number | null;
    product_id?: number | null;
    remark?: string | null;
  },
): Promise<DeviceOut> {
  return apiRequest<DeviceOut>(`/apps/kuaiiot/registry/devices/${deviceId}`, {
    method: 'PUT',
    data: payload,
  });
}

export function deleteDevice(deviceId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/registry/devices/${deviceId}`, { method: 'DELETE' });
}

export function createTag(
  deviceId: number,
  payload: { tag_key: string; name: string; value_type: string; map_target: string },
): Promise<TagOut> {
  return apiRequest<TagOut>(`/apps/kuaiiot/registry/devices/${deviceId}/tags`, { method: 'POST', data: payload });
}

export function listSnapshots(deviceId: number): Promise<SnapshotOut[]> {
  return apiRequest<SnapshotOut[]>(`/apps/kuaiiot/registry/devices/${deviceId}/snapshots`);
}

export function listTags(params?: { device_id?: number }): Promise<TagOut[]> {
  return apiRequest<TagOut[]>('/apps/kuaiiot/registry/tags', {
    params: params?.device_id ? { device_id: params.device_id } : undefined,
  });
}

export function getTag(tagId: number): Promise<TagOut> {
  return apiRequest<TagOut>(`/apps/kuaiiot/registry/tags/${tagId}`);
}

export function updateTag(
  tagId: number,
  payload: {
    name?: string;
    value_type?: string;
    unit?: string | null;
    map_target?: string;
    fill_target?: string | null;
    is_enabled?: boolean;
  },
): Promise<TagOut> {
  return apiRequest<TagOut>(`/apps/kuaiiot/registry/tags/${tagId}`, { method: 'PUT', data: payload });
}

export function deleteTag(tagId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/registry/tags/${tagId}`, { method: 'DELETE' });
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
  return apiRequest<TemplateOut[]>('/apps/kuaiiot/registry/tag-templates');
}

export function applyTemplate(deviceId: number, code: string): Promise<{ code: string; tag_keys: string[] }> {
  return apiRequest(`/apps/kuaiiot/registry/devices/${deviceId}/template`, { method: 'POST', data: { code } });
}

export function listAlerts(): Promise<AlertOut[]> {
  return apiRequest<AlertOut[]>('/apps/kuaiiot/registry/alerts');
}

export function transitionAlert(id: number, action: 'acknowledge' | 'close'): Promise<AlertOut> {
  return apiRequest(`/apps/kuaiiot/registry/alerts/${id}/${action}`, { method: 'POST' });
}

export function createAlertRule(payload: {
  code: string;
  name: string;
  tag_key: string;
  operator: string;
  threshold_number?: number;
  threshold_text?: string;
  device_id?: number;
  equipment_uuid?: string;
  severity?: string;
  cooldown_seconds?: number;
  notify_enabled?: boolean;
  is_enabled?: boolean;
  remark?: string;
}): Promise<AlertRuleOut> {
  return apiRequest('/apps/kuaiiot/registry/alert-rules', { method: 'POST', data: payload });
}

export type AlertRuleOut = {
  id: number;
  uuid: string;
  code: string;
  name: string;
  tag_key: string;
  operator: string;
  threshold_number?: string | number | null;
  threshold_text?: string | null;
  device_id?: number | null;
  equipment_uuid?: string | null;
  severity: string;
  cooldown_seconds: number;
  notify_enabled: boolean;
  is_enabled: boolean;
  rule_type: string;
};

export function listAlertRules(): Promise<AlertRuleOut[]> {
  return apiRequest<AlertRuleOut[]>('/apps/kuaiiot/registry/alert-rules');
}

export function updateAlertRule(
  ruleId: number,
  payload: {
    name?: string;
    tag_key?: string;
    operator?: string;
    threshold_number?: number | null;
    threshold_text?: string | null;
    device_id?: number | null;
    equipment_uuid?: string | null;
    severity?: string;
    cooldown_seconds?: number;
    notify_enabled?: boolean;
    is_enabled?: boolean;
    remark?: string | null;
  },
): Promise<AlertRuleOut> {
  return apiRequest<AlertRuleOut>(`/apps/kuaiiot/registry/alert-rules/${ruleId}`, {
    method: 'PUT',
    data: payload,
  });
}

export function deleteAlertRule(ruleId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/registry/alert-rules/${ruleId}`, { method: 'DELETE' });
}

export function createOfflineRule(payload: {
  code: string;
  name: string;
  device_id?: number;
  severity?: string;
}): Promise<AlertRuleOut> {
  return apiRequest<AlertRuleOut>('/apps/kuaiiot/registry/offline-rules', { method: 'POST', data: payload });
}

export function deleteAlert(alertId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/registry/alerts/${alertId}`, { method: 'DELETE' });
}

export type ProductTag = {
  tag_key: string;
  name: string;
  value_type: string;
  map_target: string;
  unit?: string;
  fill_target?: string | null;
  is_enabled?: boolean;
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
  return apiRequest<ProductOut>('/apps/kuaiiot/registry/products', { method: 'POST', data: payload });
}

export function listProducts(): Promise<ProductOut[]> {
  return apiRequest<ProductOut[]>('/apps/kuaiiot/registry/products');
}

export function getProduct(productId: number): Promise<ProductOut> {
  return apiRequest<ProductOut>(`/apps/kuaiiot/registry/products/${productId}`);
}

export function updateProduct(
  productId: number,
  payload: {
    events?: ProductEvent[];
    functions?: ProductFunction[];
    name?: string;
    description?: string;
    tags?: ProductTag[];
    remark?: string;
  },
): Promise<ProductOut> {
  return apiRequest<ProductOut>(`/apps/kuaiiot/registry/products/${productId}`, { method: 'PUT', data: payload });
}

export function deleteProduct(productId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/registry/products/${productId}`, { method: 'DELETE' });
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
  return apiRequest<DeviceGroup[]>('/apps/kuaiiot/registry/device-groups');
}

export function createDeviceGroup(payload: {
  code: string;
  name: string;
  parent_id?: number;
  sort_order?: number;
}): Promise<DeviceGroup> {
  return apiRequest<DeviceGroup>('/apps/kuaiiot/registry/device-groups', { method: 'POST', data: payload });
}

export function assignDeviceGroup(deviceId: number, groupId: number | null): Promise<{ device_id: number; group_id: number | null }> {
  return apiRequest(`/apps/kuaiiot/registry/devices/${deviceId}/group`, { method: 'PUT', data: { group_id: groupId } });
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
  return apiRequest<DeviceCommand[]>(`/apps/kuaiiot/registry/devices/${deviceId}/commands`);
}

export function createDeviceCommand(
  deviceId: number,
  payload: { function_key: string; params?: Record<string, unknown> },
): Promise<DeviceCommand> {
  return apiRequest<DeviceCommand>(`/apps/kuaiiot/registry/devices/${deviceId}/commands`, { method: 'POST', data: payload });
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
  return apiRequest<MessageLog[]>('/apps/kuaiiot/registry/message-logs', {
    params: deviceId ? { device_id: deviceId } : undefined,
  });
}

export function batchCreateDevices(payload: {
  product_id: number;
  name_prefix: string;
  code_prefix: string;
  count: number;
}): Promise<BatchDeviceOut[]> {
  return apiRequest<BatchDeviceOut[]>('/apps/kuaiiot/registry/device-batches', { method: 'POST', data: payload });
}

export function queryTrend(params: {
  device_id: number;
  tag_key: string;
  start: string;
  stop: string;
}): Promise<TrendPoint[]> {
  return apiRequest<TrendPoint[]>('/apps/kuaiiot/registry/trends', { params });
}

export type EdgeConfigOut = {
  id: number;
  code: string;
  name: string;
  device_id: number;
  protocol: string;
  config: Record<string, unknown>;
  is_enabled: boolean;
  config_version: number;
  agent_status: string;
  agent_config_version?: number | null;
  agent_version?: string | null;
  buffer_pending_count: number;
  last_agent_heartbeat_at?: string | null;
  trial_request_uuid?: string | null;
  trial_result?: {
    request_uuid: string;
    tags: Record<string, unknown>;
    raw_values?: Record<string, unknown>;
    qualities?: Record<string, string>;
    config_version: number;
    received_at: string;
  } | null;
};

export type EdgeConfigWrite = {
  code: string;
  name: string;
  device_id: number;
  protocol: string;
  config: Record<string, unknown>;
  is_enabled: boolean;
};

export function listEdgeConfigs(): Promise<EdgeConfigOut[]> {
  return apiRequest<EdgeConfigOut[]>('/apps/kuaiiot/registry/edge-configs');
}

export function getEdgeConfig(configId: number): Promise<EdgeConfigOut> {
  return apiRequest<EdgeConfigOut>(`/apps/kuaiiot/registry/edge-configs/${configId}`);
}

export function saveEdgeConfig(payload: EdgeConfigWrite): Promise<EdgeConfigOut> {
  return apiRequest<EdgeConfigOut>('/apps/kuaiiot/registry/edge-configs', { method: 'POST', data: payload });
}

export function updateEdgeConfig(configId: number, payload: EdgeConfigWrite): Promise<EdgeConfigOut> {
  return apiRequest<EdgeConfigOut>(`/apps/kuaiiot/registry/edge-configs/${configId}`, {
    method: 'PUT',
    data: payload,
  });
}

export function deleteEdgeConfig(configId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/registry/edge-configs/${configId}`, { method: 'DELETE' });
}

export function requestTrial(configId: number): Promise<EdgeConfigOut> {
  return apiRequest<EdgeConfigOut>(`/apps/kuaiiot/registry/edge-configs/${configId}/trial`, { method: 'POST' });
}

export type DiagnosticsOut = {
  connections: Array<{
    id: number;
    name: string;
    type: string;
    health_status: string;
    last_health_at?: string | null;
  }>;
  devices: Array<{
    id: number;
    name: string;
    is_online: boolean;
    last_seen_at?: string | null;
  }>;
  agents: Array<Omit<EdgeConfigOut, 'config'>>;
  deliveries: Array<{
    id: number;
    kind: string;
    status: string;
    attempts: number;
    last_error?: string | null;
  }>;
};

export function getDiagnostics(): Promise<DiagnosticsOut> {
  return apiRequest<DiagnosticsOut>('/apps/kuaiiot/registry/diagnostics');
}

export type OpsFeedEquipment = {
  equipment_uuid: string;
  equipment_id: number;
  code: string;
  name: string;
  workshop_id?: number | null;
  workshop_name?: string | null;
  status?: string | null;
  is_online?: boolean | null;
};

export type OpsMetric = {
  equipment_uuid: string;
  equipment_id: number;
  code: string;
  name: string;
  availability_rate: number | null;
  quality_rate: number | null;
  performance_rate: number | null;
  coverage_rate: number | null;
  unavailable_reasons: string[];
  oee_live: number | null;
};

export type OpsFeedSpotCheck = {
  equipment_uuid: string;
  equipment_code: string;
  equipment_name: string;
  document_no: string;
  check_date?: string | null;
  status: string;
  has_abnormality: boolean;
};

export type EquipmentOpsFeed = {
  equipment_list: OpsFeedEquipment[];
  ops_metrics: OpsMetric[];
  status_dist: Array<{ status: string; count: number }>;
  workshop_stats: Array<{
    workshop_id: number | null;
    workshop_name: string | null;
    equipment_count: number;
  }>;
  spot_check_recent: OpsFeedSpotCheck[];
};

export function getEquipmentOpsFeed(hours?: number): Promise<EquipmentOpsFeed> {
  return apiRequest<EquipmentOpsFeed>('/apps/kuaiiot/analytics/equipment-ops-feed', {
    params: hours ? { hours } : undefined,
  });
}
