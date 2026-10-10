import { apiRequest } from '../../../services/api';

export type DashboardSummary = {
  total_devices: number;
  online_devices: number;
  total_connections: number;
  enabled_connections: number;
  total_tags: number;
  points_today: number;
  recent_devices: Device[];
};

export type Connection = {
  uuid: string;
  id: number;
  code: string;
  name: string;
  connection_type: string;
  config?: Record<string, unknown>;
  is_enabled: boolean;
  health_status: string;
  last_health_at?: string;
  remark?: string;
};

export type Device = {
  uuid: string;
  id: number;
  code: string;
  name: string;
  external_device_id: string;
  connection_id?: number;
  product_id?: number;
  group_id?: number;
  equipment_uuid?: string;
  device_token: string;
  is_online: boolean;
  last_seen_at?: string;
  remark?: string;
};

export type TagSnapshot = {
  tag_key: string;
  value_text?: string;
  value_number?: number;
  value_bool?: boolean;
  quality: string;
  sampled_at: string;
};

export type TagHistory = TagSnapshot;

export type TagHistoryList = {
  items: TagHistory[];
  tsdb_configured: boolean;
};

export type TagDefinition = {
  uuid: string;
  id: number;
  device_id: number;
  tag_key: string;
  name: string;
  value_type: string;
  unit?: string;
  map_target: string;
  fill_target?: string;
  is_enabled: boolean;
};

export type AlertRule = {
  uuid: string;
  id: number;
  code: string;
  name: string;
  rule_type?: string;
  device_id?: number;
  equipment_uuid?: string;
  tag_key: string;
  operator: string;
  threshold_number?: number;
  threshold_text?: string;
  severity: string;
  cooldown_seconds: number;
  notify_enabled: boolean;
  is_enabled: boolean;
  remark?: string;
};

export type AlertRecord = {
  uuid: string;
  id: number;
  rule_id: number;
  device_id: number;
  equipment_uuid?: string;
  tag_key: string;
  severity: string;
  message: string;
  actual_value?: string;
  status: string;
  triggered_at: string;
};

export type EdgeConfig = {
  uuid: string;
  id: number;
  code: string;
  name: string;
  device_id: number;
  protocol: string;
  config: Record<string, unknown>;
  config_version?: number;
  last_agent_heartbeat_at?: string;
  agent_version?: string;
  agent_status?: string;
  buffer_pending_count?: number;
  is_enabled: boolean;
  remark?: string;
};

export type OpsSummary = {
  connections: Record<string, number>;
  devices: Record<string, number>;
  edge_agents: Record<string, number>;
  alerts: Record<string, number>;
  ingest: Record<string, number>;
  tsdb_configured: boolean;
};

export async function getDashboardSummary() {
  return apiRequest<DashboardSummary>('/apps/kuaiiot/dashboard/summary', { method: 'GET' });
}

export async function getOpsSummary() {
  return apiRequest<OpsSummary>('/apps/kuaiiot/ops/summary', { method: 'GET' });
}

export async function listConnections(params?: { page?: number; page_size?: number; q?: string }) {
  return apiRequest<{ items: Connection[]; total: number }>('/apps/kuaiiot/connections', {
    method: 'GET',
    params,
  });
}

export async function createConnection(data: Partial<Connection>) {
  return apiRequest<Connection>('/apps/kuaiiot/connections', { method: 'POST', data });
}

export async function updateConnection(uuid: string, data: Partial<Connection>) {
  return apiRequest<Connection>(`/apps/kuaiiot/connections/${uuid}`, { method: 'PUT', data });
}

export async function deleteConnection(uuid: string) {
  return apiRequest<void>(`/apps/kuaiiot/connections/${uuid}`, { method: 'DELETE' });
}

export type ConnectionRecentMessage = {
  uuid: string;
  topic: string;
  qos: number;
  retained: boolean;
  received_at: string;
  payload?: unknown;
  payload_format: string;
  ingest_summary?: Record<string, unknown>;
  error?: string;
};

export async function listConnectionRecentMessages(uuid: string, limit = 20) {
  return apiRequest<{ items: ConnectionRecentMessage[]; total: number }>(
    `/apps/kuaiiot/connections/${uuid}/recent-messages`,
    { method: 'GET', params: { limit } },
  );
}

export type DiscoveredMqttDevice = {
  external_device_id: string;
  device_name: string;
  device_key?: string;
  line_name?: string;
  line_code?: string;
  workshop_name?: string;
  workshop_code?: string;
  status?: string;
  last_seen_at?: string;
  topic?: string;
  already_bound: boolean;
  label: string;
  connection_id?: number;
};

export async function listConnectionDiscoveredDevices(uuid: string, limit = 50) {
  return apiRequest<{ items: DiscoveredMqttDevice[]; total: number }>(
    `/apps/kuaiiot/connections/${uuid}/discovered-devices`,
    { method: 'GET', params: { limit } },
  );
}

export async function listAllDiscoveredMqttDevices(limit = 200) {
  return apiRequest<{ items: DiscoveredMqttDevice[]; total: number }>(
    '/apps/kuaiiot/connections/discovered-devices',
    { method: 'GET', params: { limit } },
  );
}

export async function syncConnectionDevices(connectionUuid: string) {
  return apiRequest<{ synced_devices: number; message: string }>('/apps/kuaiiot/connectors/sync', {
    method: 'POST',
    data: { connection_uuid: connectionUuid },
  });
}

export async function healthCheckConnection(connectionUuid: string) {
  return apiRequest<{ health_status: string; last_health_at?: string }>(
    `/apps/kuaiiot/connectors/health-check/${connectionUuid}`,
    { method: 'POST' },
  );
}


export async function pullConnectionTelemetry(connectionUuid: string) {
  return apiRequest<{ pulled_points: number; message: string }>(
    `/apps/kuaiiot/connectors/pull-telemetry/${connectionUuid}`,
    { method: 'POST' },
  );
}


export async function listDevices(params?: { page?: number; page_size?: number; q?: string; group_id?: number }) {
  return apiRequest<{ items: Device[]; total: number }>('/apps/kuaiiot/devices', {
    method: 'GET',
    params,
  });
}

export async function createDevice(data: Partial<Device> & { tag_template_code?: string; product_id?: number }) {
  return apiRequest<Device>('/apps/kuaiiot/devices', { method: 'POST', data });
}

export async function batchCreateDevices(data: {
  product_id: number;
  name_prefix: string;
  count: number;
  code_prefix?: string;
  connection_id?: number;
  equipment_uuid?: string;
  remark?: string;
}) {
  return apiRequest<{ items: DeviceBatchItem[]; total: number }>('/apps/kuaiiot/devices/batch', {
    method: 'POST',
    data,
  });
}

export async function ingestDeviceData(deviceToken: string, payload: { tags: Record<string, unknown>; timestamp?: string }) {
  return apiRequest<IngestResponse>(`/apps/kuaiiot/ingest/${deviceToken}`, { method: 'POST', data: payload });
}

export async function updateDevice(uuid: string, data: Partial<Device>) {
  return apiRequest<Device>(`/apps/kuaiiot/devices/${uuid}`, { method: 'PUT', data });
}

export async function deleteDevice(uuid: string) {
  return apiRequest<void>(`/apps/kuaiiot/devices/${uuid}`, { method: 'DELETE' });
}

export async function rotateDeviceToken(uuid: string) {
  return apiRequest<Device>(`/apps/kuaiiot/devices/${uuid}/rotate-token`, { method: 'POST' });
}

export async function listDeviceSnapshots(uuid: string) {
  return apiRequest<TagSnapshot[]>(`/apps/kuaiiot/devices/${uuid}/snapshots`, { method: 'GET' });
}

export async function listDeviceHistory(uuid: string, params?: { tag_key?: string; limit?: number }) {
  return apiRequest<TagHistoryList>(`/apps/kuaiiot/devices/${uuid}/history`, {
    method: 'GET',
    params,
  });
}

export async function listTags(params?: { page?: number; page_size?: number; device_id?: number; q?: string }) {
  return apiRequest<{ items: TagDefinition[]; total: number }>('/apps/kuaiiot/tags', {
    method: 'GET',
    params,
  });
}

export async function createTag(data: Partial<TagDefinition>) {
  return apiRequest<TagDefinition>('/apps/kuaiiot/tags', { method: 'POST', data });
}

export async function updateTag(uuid: string, data: Partial<TagDefinition>) {
  return apiRequest<TagDefinition>(`/apps/kuaiiot/tags/${uuid}`, { method: 'PUT', data });
}

export async function deleteTag(uuid: string) {
  return apiRequest<void>(`/apps/kuaiiot/tags/${uuid}`, { method: 'DELETE' });
}

export async function listEquipmentOptions() {
  const res = await apiRequest<{ items?: Array<{ uuid: string; code: string; name: string }>; total?: number }>(
    '/apps/kuaizhizao/equipment',
    {
      method: 'GET',
      params: {
        skip: 0,
        limit: 500,
        order_by: '-created_at',
        exclude_equipment_nature: '测量设备',
      },
    },
  );
  const items = res.items ?? (Array.isArray(res) ? res : []);
  // 与设备台账展示一致：名称/编码
  return items.map((item) => ({
    label: `${item.name} / ${item.code}`,
    value: item.uuid,
    name: item.name,
    code: item.code,
  }));
}

export async function listAlertRules(params?: { page?: number; page_size?: number; device_id?: number; q?: string }) {
  return apiRequest<{ items: AlertRule[]; total: number }>('/apps/kuaiiot/alerts/rules', { method: 'GET', params });
}

export async function createAlertRule(data: Partial<AlertRule>) {
  return apiRequest<AlertRule>('/apps/kuaiiot/alerts/rules', { method: 'POST', data });
}

export async function updateAlertRule(uuid: string, data: Partial<AlertRule>) {
  return apiRequest<AlertRule>(`/apps/kuaiiot/alerts/rules/${uuid}`, { method: 'PUT', data });
}

export async function deleteAlertRule(uuid: string) {
  return apiRequest<void>(`/apps/kuaiiot/alerts/rules/${uuid}`, { method: 'DELETE' });
}

export async function listAlerts(params?: { page?: number; page_size?: number; status?: string; device_id?: number }) {
  return apiRequest<{ items: AlertRecord[]; total: number }>('/apps/kuaiiot/alerts', { method: 'GET', params });
}

export async function acknowledgeAlert(uuid: string) {
  return apiRequest<AlertRecord>(`/apps/kuaiiot/alerts/${uuid}/acknowledge`, { method: 'POST' });
}

export async function listEdgeConfigs(params?: { page?: number; page_size?: number; device_id?: number; q?: string }) {
  return apiRequest<{ items: EdgeConfig[]; total: number }>('/apps/kuaiiot/edge-configs', { method: 'GET', params });
}

export async function createEdgeConfig(data: Partial<EdgeConfig>) {
  return apiRequest<EdgeConfig>('/apps/kuaiiot/edge-configs', { method: 'POST', data });
}

export async function updateEdgeConfig(uuid: string, data: Partial<EdgeConfig>) {
  return apiRequest<EdgeConfig>(`/apps/kuaiiot/edge-configs/${uuid}`, { method: 'PUT', data });
}

export async function deleteEdgeConfig(uuid: string) {
  return apiRequest<void>(`/apps/kuaiiot/edge-configs/${uuid}`, { method: 'DELETE' });
}

export async function exportEdgeAgentSpec(uuid: string) {
  return apiRequest<{ version: number; protocol: string; device_token: string; config: Record<string, unknown> }>(
    `/apps/kuaiiot/edge-configs/${uuid}/agent-spec`,
    { method: 'GET' },
  );
}


export type Product = {
  uuid: string;
  id: number;
  code: string;
  name: string;
  description?: string;
  tags: Array<Record<string, unknown>>;
  remark?: string;
};

export type DeviceBatchItem = {
  uuid: string;
  code: string;
  name: string;
  device_token: string;
};

export type IngestResponse = {
  accepted: number;
  mes_updated?: boolean;
};

export type TagTemplate = {
  code: string;
  name: string;
  description?: string;
  tag_count: number;
};

export type DeviceGroup = {
  uuid: string;
  id: number;
  parent_id?: number;
  code: string;
  name: string;
  sort_order: number;
  children?: DeviceGroup[];
};

export type DeviceCommand = {
  uuid: string;
  id: number;
  function_key: string;
  status: string;
  dispatch_channel?: string;
  created_at: string;
};

export type MessageLog = {
  uuid: string;
  id: number;
  direction: string;
  msg_type: string;
  payload?: Record<string, unknown>;
  created_at: string;
};

export type OeeLiveItem = {
  equipment_uuid: string;
  equipment_code: string;
  equipment_name: string;
  sensor: Record<string, number>;
  mes_quality_rate?: number;
  oee_live?: number;
  oee_note: string;
  latest_status?: string;
  is_online: boolean;
  monitor_points: number;
};

export type PipelineGraph = {
  nodes: Array<{ id: string; node_type: string; label: string; status: string; meta?: Record<string, unknown> }>;
  edges: Array<{ source: string; target: string; edge_type: string }>;
  summary: Record<string, number>;
};

export async function listOeeLive(params?: { hours?: number; limit?: number }) {
  return apiRequest<{ items: OeeLiveItem[]; total: number }>('/apps/kuaiiot/analytics/oee-live', {
    method: 'GET',
    params,
  });
}

export async function getPipelineGraph() {
  return apiRequest<PipelineGraph>('/apps/kuaiiot/analytics/pipeline', { method: 'GET' });
}

export async function getEquipmentOpsFeed(params?: { hours?: number }) {
  return apiRequest<Record<string, unknown>>('/apps/kuaiiot/analytics/equipment-ops-feed', {
    method: 'GET',
    params,
  });
}

export async function listProducts(params?: { page?: number; page_size?: number; q?: string }) {
  return apiRequest<{ items: Product[]; total: number }>('/apps/kuaiiot/products', { method: 'GET', params });
}

export async function createProduct(data: Partial<Product>) {
  return apiRequest<Product>('/apps/kuaiiot/products', { method: 'POST', data });
}

export async function updateProduct(uuid: string, data: Partial<Product>) {
  return apiRequest<Product>(`/apps/kuaiiot/products/${uuid}`, { method: 'PUT', data });
}

export async function deleteProduct(uuid: string) {
  return apiRequest<void>(`/apps/kuaiiot/products/${uuid}`, { method: 'DELETE' });
}

export async function loadBuiltinProductPresets() {
  return apiRequest<{ created: number; skipped: number; total: number }>('/apps/kuaiiot/products/load-builtin-presets', {
    method: 'POST',
  });
}

export async function listDeviceGroupsTree() {
  return apiRequest<{ items: DeviceGroup[] }>('/apps/kuaiiot/device-groups/tree', { method: 'GET' });
}

export async function createDeviceGroup(data: Partial<DeviceGroup>) {
  return apiRequest<DeviceGroup>('/apps/kuaiiot/device-groups', { method: 'POST', data });
}

export async function updateDeviceGroup(uuid: string, data: Partial<DeviceGroup>) {
  return apiRequest<DeviceGroup>(`/apps/kuaiiot/device-groups/${uuid}`, { method: 'PUT', data });
}

export async function deleteDeviceGroup(uuid: string) {
  return apiRequest<void>(`/apps/kuaiiot/device-groups/${uuid}`, { method: 'DELETE' });
}

export async function listDeviceCommands(deviceUuid: string, params?: { page?: number; page_size?: number }) {
  return apiRequest<{ items: DeviceCommand[]; total: number }>(`/apps/kuaiiot/devices/${deviceUuid}/commands`, {
    method: 'GET',
    params,
  });
}

export async function createDeviceCommand(
  deviceUuid: string,
  data: { function_key: string; params?: Record<string, unknown>; dispatch_channel?: string },
) {
  return apiRequest<DeviceCommand>(`/apps/kuaiiot/devices/${deviceUuid}/commands`, { method: 'POST', data });
}

export async function listDeviceMessageLogs(
  deviceUuid: string,
  params?: { page?: number; page_size?: number; direction?: string; msg_type?: string },
) {
  return apiRequest<{ items: MessageLog[]; total: number }>(`/apps/kuaiiot/devices/${deviceUuid}/message-logs`, {
    method: 'GET',
    params,
  });
}
