/**
 * KU-AI 运营层 API（spec 181；/apps/kuaiai/operations 命名空间）。
 *
 * 全部走 apiRequest（base 已含 /api/v1，成功信封已解包）；
 * days 为用户可分享筛选，可进 query；内部 ID/key 只进 path/body。
 */

import { apiRequest, API_BASE_URL, buildAuthTenantHeaders } from '../../../services/api';
import { downloadFile } from '../../../utils/fileDownload';
import type {
  AiAuditLogListOut,
  AiStatsOverviewOut,
  CorpusBatchOut,
  CorpusFaqCreatePayload,
  CorpusItemOut,
  CorpusKnowledgeOption,
  CorpusListOut,
  CorpusQuery,
  CorpusSeedFaqsOut,
  HubOut,
  LibraryItemOut,
  LibraryOut,
  PulseOut,
  PulseQuery,
  SceneInstanceClonePayload,
  SceneInstanceUpdatePayload,
  SettingsOut,
  SettingsUpdatePayload,
  TrustOut,
} from '../types/operations';

const OPS_BASE = '/apps/kuaiai/operations';

export function getHub(days = 7): Promise<HubOut> {
  return apiRequest<HubOut>(`${OPS_BASE}/hub`, {
    params: { days },
  });
}

export function getAgentLibrary(): Promise<LibraryOut> {
  return apiRequest<LibraryOut>(`${OPS_BASE}/agent-library`);
}

export function updateSceneInstance(
  instanceKey: string,
  payload: SceneInstanceUpdatePayload,
): Promise<LibraryItemOut> {
  return apiRequest<LibraryItemOut>(
    `${OPS_BASE}/agent-library/instances/${encodeURIComponent(instanceKey)}`,
    { method: 'PUT', data: payload },
  );
}

export function cloneSceneInstance(
  payload: SceneInstanceClonePayload,
): Promise<LibraryItemOut> {
  return apiRequest<LibraryItemOut>(`${OPS_BASE}/agent-library/instances`, {
    method: 'POST',
    data: payload,
  });
}

// ============================================================ Pulse（spec 182）

export function getPulse(
  query: PulseQuery = {},
  signal?: AbortSignal,
): Promise<PulseOut> {
  return apiRequest<PulseOut>(`${OPS_BASE}/pulse`, {
    params: query,
    signal,
  });
}

// ============================================================ 信任中心（spec 184）

export function getTrust(signal?: AbortSignal): Promise<TrustOut> {
  return apiRequest<TrustOut>(`${OPS_BASE}/trust`, { signal });
}

// ============================================================ Core AI 统计/审计复用（spec 184）
// 直接消费既有 /core/ai/*（kuaiai:entry:read）；页面须先过 display 门控再发请求。

const CORE_AI_BASE = '/core/ai';

export function getAiStatsOverview(
  days: number,
  signal?: AbortSignal,
): Promise<AiStatsOverviewOut> {
  return apiRequest<AiStatsOverviewOut>(`${CORE_AI_BASE}/stats/overview`, {
    params: { days },
    signal,
  });
}

export function listAiAuditLogs(
  query: { page?: number; page_size?: number; capability?: string } = {},
  signal?: AbortSignal,
): Promise<AiAuditLogListOut> {
  return apiRequest<AiAuditLogListOut>(`${CORE_AI_BASE}/audit/logs`, {
    params: query,
    signal,
  });
}

// ============================================================ 设置（spec 185）

export function getOperationsSettings(): Promise<SettingsOut> {
  return apiRequest<SettingsOut>(`${OPS_BASE}/settings`);
}

export function updateOperationsSettings(
  payload: SettingsUpdatePayload,
): Promise<SettingsOut> {
  return apiRequest<SettingsOut>(`${OPS_BASE}/settings`, {
    method: 'PUT',
    data: payload,
  });
}

// ============================================================ 知识语料（spec 183）

export function listCorpus(
  query: CorpusQuery = {},
  signal?: AbortSignal,
): Promise<CorpusListOut> {
  return apiRequest<CorpusListOut>(`${OPS_BASE}/corpus`, {
    params: query,
    signal,
  });
}

/** 语料页启用知识库下拉项（corpus:display，不要求 knowledge 权限） */
export function listCorpusKnowledgeOptions(): Promise<CorpusKnowledgeOption[]> {
  return apiRequest<CorpusKnowledgeOption[]>(
    `${OPS_BASE}/corpus/knowledge-options`,
  );
}

export function createCorpusFaq(
  payload: CorpusFaqCreatePayload,
): Promise<CorpusItemOut> {
  return apiRequest<CorpusItemOut>(`${OPS_BASE}/corpus/faqs`, {
    method: 'POST',
    data: payload,
  });
}

export function seedCorpusFaqs(
  knowledgeId: number,
): Promise<CorpusSeedFaqsOut> {
  return apiRequest<CorpusSeedFaqsOut>(`${OPS_BASE}/corpus/seed-faqs`, {
    method: 'POST',
    data: { mode: 'missing_only', knowledge_id: knowledgeId },
  });
}

export function batchIndexCorpus(ids: number[]): Promise<CorpusBatchOut> {
  return apiRequest<CorpusBatchOut>(`${OPS_BASE}/corpus/batch-index`, {
    method: 'POST',
    data: { ids },
  });
}

export function batchDeleteCorpus(ids: number[]): Promise<CorpusBatchOut> {
  return apiRequest<CorpusBatchOut>(`${OPS_BASE}/corpus/batch-delete`, {
    method: 'POST',
    data: { ids },
  });
}

/**
 * 训练 JSONL 流式导出：raw fetch（成功信封不适用），下载文件名固定
 * corpus-export.jsonl；错误详情只取服务端文案，不拼接内部信息。
 */
export async function downloadCorpusJsonl(
  query: CorpusQuery = {},
): Promise<void> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value));
    }
  });
  const queryString = params.toString();
  const response = await fetch(
    `${API_BASE_URL}${OPS_BASE}/corpus/export.jsonl${queryString ? `?${queryString}` : ''}`,
    { method: 'GET', headers: buildAuthTenantHeaders() },
  );
  if (!response.ok) {
    let detail = '';
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('json')) {
      try {
        const data = await response.json();
        const raw = data?.detail ?? data?.message;
        detail = typeof raw === 'string' ? raw : '';
      } catch {
        detail = '';
      }
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  downloadFile(blob, 'corpus-export.jsonl');
}
