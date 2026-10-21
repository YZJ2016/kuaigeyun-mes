import { API_BASE_URL, apiRequest, buildWriteAuthHeaders } from '../../services/api';

import { serializeKuAiMessagesForApi } from './kuAiMessageMeta';
import type { KuAiConversationRecord, KuAiStoredMessage } from './kuAiConversationStore';

const BASE = '/core/ai/conversations';

type ApiSummary = {
  id: string;
  title: string;
  updated_at: string;
  last_speaker_name?: string | null;
  last_spoken_at?: string | null;
  inquirer_name?: string | null;
};

type ApiDetail = ApiSummary & {
  messages: KuAiStoredMessage[];
};

function parseUpdatedAtMs(updatedAt: string): number {
  const ms = Date.parse(updatedAt.replace(' ', 'T'));
  return Number.isFinite(ms) ? ms : Date.now();
}

function toRecord(summary: ApiSummary, messages: KuAiStoredMessage[] = []): KuAiConversationRecord {
  return {
    id: summary.id,
    title: summary.title,
    updatedAt: parseUpdatedAtMs(summary.updated_at),
    messages,
    last_speaker_name: summary.last_speaker_name ?? undefined,
    last_spoken_at: summary.last_spoken_at ?? undefined,
    inquirer_name: summary.inquirer_name ?? undefined,
  };
}

export async function fetchKuAiConversationList(): Promise<KuAiConversationRecord[]> {
  const res = await apiRequest<{ items: ApiSummary[] }>(BASE, { method: 'GET' });
  return (res.items ?? []).map((item) => toRecord(item));
}

export async function fetchKuAiConversationDetail(id: string): Promise<KuAiConversationRecord> {
  const res = await apiRequest<ApiDetail>(`${BASE}/${encodeURIComponent(id)}`, { method: 'GET' });
  return toRecord(res, res.messages ?? []);
}

export async function createKuAiConversationRemote(
  record: KuAiConversationRecord,
): Promise<KuAiConversationRecord> {
  const res = await apiRequest<ApiDetail>(BASE, {
    method: 'POST',
    body: JSON.stringify({
      id: record.id,
      title: record.title,
      messages: serializeKuAiMessagesForApi(record.messages),
    }),
  });
  return toRecord(res, res.messages ?? []);
}

export async function upsertKuAiConversationRemote(
  record: KuAiConversationRecord,
): Promise<KuAiConversationRecord> {
  const res = await apiRequest<ApiDetail>(`${BASE}/${encodeURIComponent(record.id)}`, {
    method: 'PUT',
    body: JSON.stringify({
      title: record.title,
      messages: serializeKuAiMessagesForApi(record.messages),
    }),
  });
  return toRecord(res, res.messages ?? []);
}

/** 页面关闭/刷新前尽力落库（fetch keepalive） */
export function upsertKuAiConversationKeepalive(record: KuAiConversationRecord): void {
  const url = `${API_BASE_URL}${BASE}/${encodeURIComponent(record.id)}`;
  const body = JSON.stringify({
    title: record.title,
    messages: serializeKuAiMessagesForApi(record.messages),
  });
  try {
    void fetch(url, {
      method: 'PUT',
      headers: buildWriteAuthHeaders(),
      body,
      keepalive: true,
    });
  } catch {
    // 关闭阶段失败即暴露为丢数，不静默吞错以外的第二路径
  }
}

export async function deleteKuAiConversationRemote(id: string): Promise<void> {
  await apiRequest<void>(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function importKuAiConversationsRemote(
  records: KuAiConversationRecord[],
): Promise<KuAiConversationRecord[]> {
  if (records.length === 0) return [];
  const res = await apiRequest<{ items: ApiSummary[] }>(`${BASE}/import`, {
    method: 'POST',
    body: JSON.stringify({
      items: records.map((r) => ({
        id: r.id,
        title: r.title,
        messages: serializeKuAiMessagesForApi(r.messages),
      })),
    }),
  });
  return (res.items ?? []).map((item) => toRecord(item));
}
