/**
 * 边缘配置保存。请求走现有 apiRequest。
 */

import { apiRequest } from '../../../../services/api';

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
  trial_result?: { request_uuid: string; tags: Record<string, unknown>; raw_values?: Record<string, unknown>; qualities?: Record<string, string>; config_version: number; received_at: string } | null;
};

export type EdgeConfigWrite = {
  code: string;
  name: string;
  device_id: number;
  protocol: string;
  config: Record<string, unknown>;
  is_enabled: boolean;
};

export function saveEdgeConfig(payload: EdgeConfigWrite): Promise<EdgeConfigOut> {
  return apiRequest<EdgeConfigOut>('/apps/kuaiiot/edge-configs', { method: 'POST', data: payload });
}

export function listEdgeConfigs(): Promise<EdgeConfigOut[]> {
  return apiRequest('/apps/kuaiiot/edge-configs');
}
export function requestTrial(id: number): Promise<EdgeConfigOut> {
  return apiRequest(`/apps/kuaiiot/edge-configs/${id}/trial`, { method: 'POST' });
}
