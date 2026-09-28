/**
 * 用户消息管理服务
 * 
 * 提供用户消息的查询、标记已读等功能。
 * 注意：所有 API 自动获取当前用户的消息。
 */

import { API_BASE_URL, apiRequest, buildAuthTenantHeaders, formatApiErrorDetail } from './api';
import { downloadFile } from '../utils/fileDownload';

export interface UserMessage {
  uuid: string;
  tenant_id: number;
  template_uuid?: string;
  config_uuid?: string;
  type: string;
  recipient: string;
  subject?: string;
  content: string;
  /** 有附件时为文件名；没有附件则不返回或为空 */
  attachment_name?: string;
  variables?: Record<string, any>;
  status: string;
  inngest_run_id?: string;
  error_message?: string;
  sent_at?: string;
  created_at: string;
  updated_at: string;
}

export interface UserMessageListResponse {
  items: UserMessage[];
  total: number;
  page: number;
  page_size: number;
}

export interface UserMessageStats {
  total: number;
  unread: number;
  read: number;
  failed: number;
}

export interface MarkReadRequest {
  message_uuids: string[];
}

export interface MarkReadResponse {
  updated_count: number;
}

/**
 * 获取当前用户消息列表
 */
export async function getUserMessages(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  channel?: string;
  unread_only?: boolean;
}): Promise<UserMessageListResponse> {
  return apiRequest<UserMessageListResponse>('/personal/user-messages', {
    params,
  });
}

/**
 * 获取当前用户消息详情
 */
export async function getUserMessage(messageUuid: string): Promise<UserMessage> {
  return apiRequest<UserMessage>(`/personal/user-messages/${messageUuid}`);
}

/**
 * 获取当前用户消息统计
 */
export async function getUserMessageStats(): Promise<UserMessageStats> {
  return apiRequest<UserMessageStats>('/personal/user-messages/stats');
}

/**
 * 标记消息为已读
 */
export async function markMessagesRead(data: MarkReadRequest): Promise<MarkReadResponse> {
  return apiRequest<MarkReadResponse>('/personal/user-messages/mark-read', {
    method: 'POST',
    data,
  });
}

function filenameFromContentDisposition(header: string | null): string {
  if (!header) return '';
  const starred = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (starred?.[1]) {
    try {
      return decodeURIComponent(starred[1].trim());
    } catch {
      return '';
    }
  }
  const quoted = /filename\s*=\s*"([^"]+)"/i.exec(header);
  if (quoted?.[1]) return quoted[1].trim();
  const plain = /filename\s*=\s*([^;]+)/i.exec(header);
  return plain?.[1]?.trim() ?? '';
}

function safeDownloadName(name: string): string {
  const base = name.split(/[/\\]/).filter(Boolean).pop()?.trim() ?? '';
  return base.replace(/[\r\n"]/g, '');
}

/**
 * 下载当前用户某条消息的附件。
 * GET /api/v1/personal/user-messages/{uuid}/attachment
 * 文件名优先用 Content-Disposition，否则用详情里的 attachment_name。
 */
export async function downloadUserMessageAttachment(
  messageUuid: string,
  fallbackName: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/personal/user-messages/${encodeURIComponent(messageUuid)}/attachment`,
    {
      method: 'GET',
      headers: buildAuthTenantHeaders(),
    },
  );
  if (!response.ok) {
    let detail = '';
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('json')) {
      try {
        const data = await response.json();
        detail = formatApiErrorDetail(data?.detail ?? data?.message);
      } catch {
        detail = '';
      }
    }
    throw new Error(detail);
  }
  const filename = safeDownloadName(
    filenameFromContentDisposition(response.headers.get('Content-Disposition')) || fallbackName,
  );
  if (!filename) {
    throw new Error('');
  }
  const blob = await response.blob();
  downloadFile(blob, filename);
}

