/**
 * 接入配置页接口封装。共享读写复用 services/kuaiiot；
 * services 的 ConnectionOut 缺 created_at/config/remark 展示字段，这里补齐行类型。
 * URL、method、响应外层与后端契约一致，仅放宽前端类型。
 */

import { apiRequest } from '../../../../services/api';
import type { ConnectionOut } from '../../services/kuaiiot';

export type ConnectionRow = ConnectionOut & {
  /** 后端响应含已脱敏 config（密钥字段服务端剔除），展示安全 */
  config?: Record<string, unknown> | null;
  remark?: string | null;
  created_at?: string | null;
};

export function listConnectionRows(): Promise<ConnectionRow[]> {
  return apiRequest<ConnectionRow[]>('/apps/kuaiiot/connections');
}

export function getConnectionRow(connectionId: number): Promise<ConnectionRow> {
  return apiRequest<ConnectionRow>(`/apps/kuaiiot/connections/${connectionId}`);
}

/** 与后端 ConnectionCreate 对齐：比 services.createConnection 多 is_enabled/remark。 */
export function createConnectionRow(payload: {
  code: string;
  name: string;
  connection_type: string;
  integration_uuid?: string;
  config?: Record<string, string>;
  is_enabled?: boolean;
  remark?: string;
}): Promise<ConnectionRow> {
  return apiRequest<ConnectionRow>('/apps/kuaiiot/connections', { method: 'POST', data: payload });
}

export function updateConnectionRow(
  connectionId: number,
  payload: {
    name?: string;
    config?: Record<string, string> | null;
    is_enabled?: boolean;
    remark?: string | null;
  },
): Promise<ConnectionRow> {
  return apiRequest<ConnectionRow>(`/apps/kuaiiot/connections/${connectionId}`, {
    method: 'PUT',
    data: payload,
  });
}

export function deleteConnectionRow(connectionId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/connections/${connectionId}`, { method: 'DELETE' });
}
