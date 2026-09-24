/**
 * KU-AI MCP 白名单 API（spec 138，对齐 spec 137 契约）。
 *
 * 产品前缀 `/api/v1/apps/kuaiai/`；请求体禁止夹带 tenantId（后端 extra=forbid）。
 * token 只写不回明文：响应恒为打码占位（"****"）或 null + token_configured。
 */

import { apiRequest } from '../../../services/api';
import type { PagedResult, PageParams } from './knowledge';

const BASE = '/apps/kuaiai';

export interface McpServerOut {
  id: number;
  uuid: string;
  code: string;
  name: string;
  transport: string;
  endpoint: string;
  /** 打码占位（"****"）或 null，绝不回明文 */
  token?: string | null;
  token_configured: boolean;
  /** 允许工具名 CSV */
  allowed_tools: string;
  /** 启用|停用 */
  status: string;
  created_at: string;
  updated_at: string;
}

export interface McpServerCreatePayload {
  code: string;
  name: string;
  /** 仅 http，缺省 http */
  transport?: string;
  endpoint: string;
  /** 只写不回明文 */
  token?: string;
  /** 允许工具名 CSV（非空；SQL 类工具名后端拒绝） */
  allowed_tools: string;
  status?: string;
}

export type McpServerUpdatePayload = Partial<McpServerCreatePayload>;

export interface McpServerOption {
  id: number;
  name: string;
  code: string;
}

export function listMcpServers(params?: PageParams) {
  return apiRequest<PagedResult<McpServerOut>>(`${BASE}/mcp-servers`, { params });
}

export function createMcpServer(data: McpServerCreatePayload) {
  return apiRequest<McpServerOut>(`${BASE}/mcp-servers`, { method: 'POST', data });
}

export function getMcpServer(id: number) {
  return apiRequest<McpServerOut>(`${BASE}/mcp-servers/${id}`);
}

export function updateMcpServer(id: number, data: McpServerUpdatePayload) {
  return apiRequest<McpServerOut>(`${BASE}/mcp-servers/${id}`, { method: 'PUT', data });
}

export function deleteMcpServer(id: number) {
  return apiRequest<void>(`${BASE}/mcp-servers/${id}`, { method: 'DELETE' });
}

export function listMcpServerOptions() {
  return apiRequest<McpServerOption[]>(`${BASE}/mcp-servers/options`);
}
