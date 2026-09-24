/**
 * KU-AI 模型目录 API（spec 138，契约 C 逐字一致）。
 *
 * - 厂商（llm-providers）：OpenAI 兼容端点目录，非闭集；内置项仅是可选模板。
 * - 模型（llm-models）：model_name 自由填写；model_type ∈ chat|embed|vision。
 * - api_key 只写不回明文：详情/列表回打码占位（LlmProviderOut.api_key），
 *   前端原样展示掩码即可；更新时传空/省略视为保留原值。
 * - 请求体禁止携带 tenantId。
 */

import { apiRequest } from '../../../services/api';

const PROVIDERS_BASE = '/apps/kuaiai/llm-providers';
const MODELS_BASE = '/apps/kuaiai/llm-models';

export type LlmModelType = 'chat' | 'embed' | 'vision';

// ============================================================ 厂商

export interface LlmProviderOut {
  id: number;
  uuid: string;
  code: string;
  name: string;
  base_url: string;
  /** 打码占位或 null，绝不回明文 */
  api_key?: string | null;
  api_key_configured: boolean;
  provider_type?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface LlmProviderCreatePayload {
  code: string;
  name: string;
  base_url: string;
  api_key?: string;
  provider_type?: string;
  status?: string;
}

export interface LlmProviderUpdatePayload {
  name?: string;
  base_url?: string;
  api_key?: string;
  provider_type?: string;
  status?: string;
}

export function listProviders(page = 1, pageSize = 50): Promise<LlmProviderOut[]> {
  return apiRequest<LlmProviderOut[]>(PROVIDERS_BASE, {
    params: { page, page_size: pageSize },
  });
}

export function getProvider(id: number): Promise<LlmProviderOut> {
  return apiRequest<LlmProviderOut>(`${PROVIDERS_BASE}/${id}`);
}

export function createProvider(payload: LlmProviderCreatePayload): Promise<LlmProviderOut> {
  return apiRequest<LlmProviderOut>(PROVIDERS_BASE, { method: 'POST', data: payload });
}

export function updateProvider(
  id: number,
  payload: LlmProviderUpdatePayload,
): Promise<LlmProviderOut> {
  return apiRequest<LlmProviderOut>(`${PROVIDERS_BASE}/${id}`, {
    method: 'PUT',
    data: payload,
  });
}

export function deleteProvider(id: number): Promise<void> {
  return apiRequest<void>(`${PROVIDERS_BASE}/${id}`, { method: 'DELETE' });
}

// ============================================================ 模型

export interface LlmModelOut {
  id: number;
  uuid: string;
  provider_id: number;
  model_name: string;
  model_type: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface LlmModelCreatePayload {
  provider_id: number;
  model_name: string;
  model_type: LlmModelType;
  status?: string;
}

export type LlmModelUpdatePayload = Partial<LlmModelCreatePayload>;

export interface LlmModelListParams {
  page?: number;
  page_size?: number;
  model_type?: string;
  provider_id?: number;
}

export function listModels(params?: LlmModelListParams): Promise<LlmModelOut[]> {
  return apiRequest<LlmModelOut[]>(MODELS_BASE, {
    params: { page: 1, page_size: 50, ...(params || {}) },
  });
}

export function getModel(id: number): Promise<LlmModelOut> {
  return apiRequest<LlmModelOut>(`${MODELS_BASE}/${id}`);
}

export function createModel(payload: LlmModelCreatePayload): Promise<LlmModelOut> {
  return apiRequest<LlmModelOut>(MODELS_BASE, { method: 'POST', data: payload });
}

export function updateModel(
  id: number,
  payload: LlmModelUpdatePayload,
): Promise<LlmModelOut> {
  return apiRequest<LlmModelOut>(`${MODELS_BASE}/${id}`, { method: 'PUT', data: payload });
}

export function deleteModel(id: number): Promise<void> {
  return apiRequest<void>(`${MODELS_BASE}/${id}`, { method: 'DELETE' });
}

/** 模型下拉项（启用行，可带 model_type 过滤；不含连接信息） */
export interface LlmModelOption {
  id: number;
  provider_id: number;
  provider_name?: string | null;
  model_name: string;
  model_type: string;
}

export function listModelOptions(modelType?: string): Promise<LlmModelOption[]> {
  return apiRequest<LlmModelOption[]>(`${MODELS_BASE}/options`, {
    params: modelType ? { model_type: modelType } : undefined,
  });
}

// ============================================================ 常用厂商模板（仅填值，不锁字段）

export interface LlmProviderTemplate {
  key: string;
  label: string;
  name: string;
  base_url: string;
  provider_type: string;
}

/** 公开 OpenAI 兼容端点模板；厂商并非下拉死名单，选择后仍可自由修改 */
export const LLM_PROVIDER_TEMPLATES: LlmProviderTemplate[] = [
  { key: 'deepseek', label: 'DeepSeek', name: 'DeepSeek', base_url: 'https://api.deepseek.com', provider_type: 'deepseek' },
  { key: 'openai', label: 'OpenAI', name: 'OpenAI', base_url: 'https://api.openai.com/v1', provider_type: 'openai' },
  { key: 'qwen', label: '通义千问（阿里云百炼）', name: '通义千问', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', provider_type: 'qwen' },
  { key: 'zhipu', label: '智谱 AI', name: '智谱 AI', base_url: 'https://open.bigmodel.cn/api/paas/v4', provider_type: 'zhipu' },
  { key: 'moonshot', label: 'Moonshot（Kimi）', name: 'Moonshot', base_url: 'https://api.moonshot.cn/v1', provider_type: 'moonshot' },
  { key: 'siliconflow', label: 'SiliconFlow', name: 'SiliconFlow', base_url: 'https://api.siliconflow.cn/v1', provider_type: 'siliconflow' },
];
