/**
 * 点位映射页接口封装。共享读写复用 services/kuaiiot；
 * services 的 TagOut 缺 uuid/unit/fill_target 展示字段，这里补齐行类型。
 * URL、method、响应外层与后端契约一致，仅放宽前端类型。
 */

import { apiRequest } from '../../../../services/api';
import type { TagOut } from '../../services/kuaiiot';

export type TagRow = TagOut & {
  uuid?: string;
  unit?: string | null;
  fill_target?: string | null;
};

export function listTagRows(deviceId?: number): Promise<TagRow[]> {
  return apiRequest<TagRow[]>('/apps/kuaiiot/tags', {
    params: deviceId ? { device_id: deviceId } : undefined,
  });
}

export function getTagRow(tagId: number): Promise<TagRow> {
  return apiRequest<TagRow>(`/apps/kuaiiot/tags/${tagId}`);
}

export function createTagRow(
  deviceId: number,
  payload: {
    tag_key: string;
    name: string;
    value_type: string;
    unit?: string;
    map_target: string;
    fill_target?: string;
    is_enabled?: boolean;
  },
): Promise<TagRow> {
  return apiRequest<TagRow>(`/apps/kuaiiot/devices/${deviceId}/tags`, {
    method: 'POST',
    data: payload,
  });
}

export function updateTagRow(
  tagId: number,
  payload: {
    name?: string;
    value_type?: string;
    unit?: string | null;
    map_target?: string;
    fill_target?: string | null;
    is_enabled?: boolean;
  },
): Promise<TagRow> {
  return apiRequest<TagRow>(`/apps/kuaiiot/tags/${tagId}`, { method: 'PUT', data: payload });
}

export function deleteTagRow(tagId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/tags/${tagId}`, { method: 'DELETE' });
}
