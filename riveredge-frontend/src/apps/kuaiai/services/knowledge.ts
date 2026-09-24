/**
 * KU-AI 知识库 / 文档 / 切块 API（spec 138，对齐 spec 136 契约）。
 *
 * 产品前缀 `/api/v1/apps/kuaiai/`；请求体禁止夹带 tenantId（后端 extra=forbid）。
 */

import { apiRequest } from '../../../services/api';

const BASE = '/apps/kuaiai';

export interface PagedResult<T> {
  items: T[];
  total: number;
}

export interface PageParams {
  page?: number;
  page_size?: number;
}

/** 知识库行（status 取值 启用|停用） */
export interface KnowledgeBaseOut {
  id: number;
  uuid: string;
  name: string;
  description?: string | null;
  embedding_model_id?: number | null;
  chunk_size?: number | null;
  chunk_overlap?: number | null;
  expand_enabled?: boolean | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBaseCreatePayload {
  name: string;
  description?: string | null;
  embedding_model_id?: number | null;
  chunk_size?: number | null;
  chunk_overlap?: number | null;
  expand_enabled?: boolean | null;
  status?: string;
}

export type KnowledgeBaseUpdatePayload = Partial<KnowledgeBaseCreatePayload>;

export interface KnowledgeBaseOption {
  id: number;
  name: string;
  description?: string | null;
}

export type DocumentStatus = 'pending' | 'parsing' | 'ready' | 'failed';

export interface DocumentListOut {
  id: number;
  uuid: string;
  knowledge_id?: number | null;
  title: string;
  source_type: string;
  file_uuid?: string | null;
  status: DocumentStatus | string;
  chunk_count: number;
  error_message?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentOut extends DocumentListOut {
  raw_content?: string | null;
}

export interface DocumentCreatePayload {
  title: string;
  source_type: string;
  file_uuid?: string;
  raw_content?: string;
}

export interface ChunkOut {
  id: number;
  chunk_index: number;
  content: string;
  char_count: number;
  created_at: string;
}

/** 文件来源文档允许的 source_type（按扩展名映射） */
export const DOCUMENT_FILE_SOURCE_TYPES = [
  'pdf',
  'doc',
  'docx',
  'ppt',
  'pptx',
  'xls',
  'xlsx',
  'md',
  'txt',
] as const;

/** 文本直存（raw_content）允许的 source_type */
export const DOCUMENT_RAW_SOURCE_TYPES = ['txt', 'md'] as const;

/** 按文件名扩展名解析 source_type；不在白名单返回 null */
export function sourceTypeFromFileName(fileName: string): string | null {
  const ext = (fileName.split('.').pop() || '').trim().toLowerCase();
  return (DOCUMENT_FILE_SOURCE_TYPES as readonly string[]).includes(ext) ? ext : null;
}

// ==================== 知识库 ====================

export function listKnowledgeBases(params?: PageParams & { keyword?: string }) {
  return apiRequest<PagedResult<KnowledgeBaseOut>>(`${BASE}/knowledge-bases`, { params });
}

export function createKnowledgeBase(data: KnowledgeBaseCreatePayload) {
  return apiRequest<KnowledgeBaseOut>(`${BASE}/knowledge-bases`, { method: 'POST', data });
}

export function getKnowledgeBase(id: number) {
  return apiRequest<KnowledgeBaseOut>(`${BASE}/knowledge-bases/${id}`);
}

export function updateKnowledgeBase(id: number, data: KnowledgeBaseUpdatePayload) {
  return apiRequest<KnowledgeBaseOut>(`${BASE}/knowledge-bases/${id}`, { method: 'PUT', data });
}

export function deleteKnowledgeBase(id: number) {
  return apiRequest<void>(`${BASE}/knowledge-bases/${id}`, { method: 'DELETE' });
}

export function listKnowledgeBaseOptions() {
  return apiRequest<KnowledgeBaseOption[]>(`${BASE}/knowledge-bases/options`);
}

// ==================== 文档 ====================

export function listDocuments(kbId: number, params?: PageParams) {
  return apiRequest<PagedResult<DocumentListOut>>(`${BASE}/knowledge-bases/${kbId}/documents`, {
    params,
  });
}

export function createDocument(kbId: number, data: DocumentCreatePayload) {
  return apiRequest<DocumentOut>(`${BASE}/knowledge-bases/${kbId}/documents`, {
    method: 'POST',
    data,
  });
}

export function getDocument(id: number) {
  return apiRequest<DocumentOut>(`${BASE}/documents/${id}`);
}

export function deleteDocument(id: number) {
  return apiRequest<void>(`${BASE}/documents/${id}`, { method: 'DELETE' });
}

/** 投递异步解析任务；返回 job 状态对象（解析是异步的，调用方直接提示已提交） */
export function parseDocument(id: number) {
  return apiRequest<Record<string, unknown>>(`${BASE}/documents/${id}/parse`, { method: 'POST' });
}

export function listChunks(docId: number, params?: PageParams) {
  return apiRequest<PagedResult<ChunkOut>>(`${BASE}/documents/${docId}/chunks`, { params });
}
