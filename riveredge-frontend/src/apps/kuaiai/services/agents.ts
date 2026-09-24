/**
 * KU-AI Agent 档案 / 授权 API（spec 138，契约 C 逐字一致）。
 *
 * - 请求体禁止携带 tenantId；组织隔离由服务端按上下文处理。
 * - grants 的 target_ids 语义随档案 grant_mode：ROLE=角色 int id，USER=用户 int id。
 * - 角色 int id 的解析依赖 `GET /core/roles/{id|by-code/{code}}/scenarios`
 *   （响应 {role:{id,uuid,name,code}}，apiRequest 已解包 success/data 信封）。
 *   注意：不直接复用 services/roleScenario.ts 的 getRoleScenarios——其内部路径
 *   带了 `/api/v1` 前缀，经 apiRequest 再拼前缀会形成 `/api/v1/api/v1/...` 而 404。
 */

import { apiRequest } from '../../../services/api';

const AGENTS_BASE = '/apps/kuaiai/agents';

export type AgentGrantMode = 'ROLE' | 'USER';
export type AgentStatus = '启用' | '停用';

/** 档案行（管理 list / 详情） */
export interface AgentProfileOut {
  id: number;
  uuid: string;
  name: string;
  description?: string | null;
  system_prompt?: string | null;
  default_model_id?: number | null;
  knowledge_ids: number[];
  enabled_tools: string[];
  mcp_server_ids: number[];
  status: string;
  grant_mode: string;
  created_at: string;
  updated_at: string;
}

export interface AgentProfileCreatePayload {
  name: string;
  description?: string;
  system_prompt?: string;
  default_model_id?: number | null;
  knowledge_ids?: number[];
  enabled_tools?: string[];
  mcp_server_ids?: number[];
  status?: string;
  grant_mode: AgentGrantMode;
}

export type AgentProfileUpdatePayload = Partial<AgentProfileCreatePayload>;

/** 档案下拉项（仅当前用户有使用权的启用档案） */
export interface AgentProfileOption {
  id: number;
  name: string;
  description?: string | null;
}

export interface AgentGrantsOut {
  agent_id: number;
  grant_mode: string;
  target_ids: number[];
}

export function listAgents(page = 1, pageSize = 50): Promise<AgentProfileOut[]> {
  return apiRequest<AgentProfileOut[]>(AGENTS_BASE, {
    params: { page, page_size: pageSize },
  });
}

export function getAgent(id: number): Promise<AgentProfileOut> {
  return apiRequest<AgentProfileOut>(`${AGENTS_BASE}/${id}`);
}

export function createAgent(payload: AgentProfileCreatePayload): Promise<AgentProfileOut> {
  return apiRequest<AgentProfileOut>(AGENTS_BASE, { method: 'POST', data: payload });
}

export function updateAgent(
  id: number,
  payload: AgentProfileUpdatePayload,
): Promise<AgentProfileOut> {
  return apiRequest<AgentProfileOut>(`${AGENTS_BASE}/${id}`, { method: 'PUT', data: payload });
}

export function deleteAgent(id: number): Promise<void> {
  return apiRequest<void>(`${AGENTS_BASE}/${id}`, { method: 'DELETE' });
}

export function listAgentOptions(): Promise<AgentProfileOption[]> {
  return apiRequest<AgentProfileOption[]>(`${AGENTS_BASE}/options`);
}

export function getAgentGrants(agentId: number): Promise<AgentGrantsOut> {
  return apiRequest<AgentGrantsOut>(`${AGENTS_BASE}/${agentId}/grants`);
}

export function putAgentGrants(agentId: number, targetIds: number[]): Promise<AgentGrantsOut> {
  return apiRequest<AgentGrantsOut>(`${AGENTS_BASE}/${agentId}/grants`, {
    method: 'PUT',
    data: { target_ids: targetIds },
  });
}

// ============================================================ 角色引用解析（ROLE 授权）

/** 角色轻量引用（int id + 展示名） */
export interface RoleRef {
  id: number;
  uuid: string;
  name: string;
  code: string;
}

function pickRoleRef(res: any): RoleRef | null {
  const role = res?.role ?? res?.data?.role;
  if (!role || typeof role.id !== 'number') return null;
  return { id: role.id, uuid: role.uuid, name: role.name, code: role.code };
}

/** 按角色 code 解析 int id（GET /core/roles/by-code/{code}/scenarios） */
export async function getRoleRefByCode(code: string): Promise<RoleRef | null> {
  const res = await apiRequest<any>(
    `/core/roles/by-code/${encodeURIComponent(code)}/scenarios`,
  );
  return pickRoleRef(res);
}

/** 按角色 int id 解析展示名（GET /core/roles/{id}/scenarios），失败返回 null */
export async function getRoleRefById(id: number): Promise<RoleRef | null> {
  const res = await apiRequest<any>(`/core/roles/${id}/scenarios`);
  return pickRoleRef(res);
}
