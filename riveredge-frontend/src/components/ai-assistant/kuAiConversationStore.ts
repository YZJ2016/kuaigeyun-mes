import { getTenantId } from '../../utils/auth';

export type KuAiStoredMessage = {
  role: string;
  content: string;
  /** 发言显示名（用户姓名或 KU-AI） */
  speaker_name?: string;
  /** 站点墙钟 YYYY-MM-DD HH:mm:ss */
  spoken_at?: string;
};

export type KuAiConversationRecord = {
  id: string;
  title: string;
  updatedAt: number;
  messages: KuAiStoredMessage[];
  last_speaker_name?: string;
  last_spoken_at?: string;
  /** 首条用户提问人（侧栏卡片展示） */
  inquirer_name?: string;
};

const STORAGE_VERSION = 'v1';
const MAX_CONVERSATIONS = 80;

function storageKey(tenantId: string, userId: number): string {
  return `riveredge.kuaiai.conversations.${STORAGE_VERSION}:${tenantId}:${userId}`;
}

/** 将会话移到列表最前，其余项相对顺序不变（禁止按 updatedAt 全表重排） */
export function moveKuAiConversationToFront(
  items: KuAiConversationRecord[],
  conversationId: string,
): KuAiConversationRecord[] {
  const index = items.findIndex((item) => item.id === conversationId)
  if (index <= 0) return items
  const next = [...items]
  const [picked] = next.splice(index, 1)
  next.unshift(picked)
  return next
}

/** 仅「继续对话」导致消息变长时置顶；详情灌入、切换、点击不调整顺序 */
export function shouldMoveKuAiThreadToFrontOnPersist(
  existing: KuAiConversationRecord | undefined,
  nextMessages: KuAiStoredMessage[],
): boolean {
  if (!existing) return false
  const prevLen = existing.messages?.length ?? 0
  const nextLen = nextMessages.length
  if (prevLen === 0) return false
  return nextLen > prevLen
}

/** 详情以服务端为准（用于纠正切换瞬间误写的侧栏标题） */
export function mergeKuAiConversationDetailIntoRecord(
  existing: KuAiConversationRecord,
  detail: KuAiConversationRecord,
): KuAiConversationRecord {
  return {
    ...existing,
    title: detail.title,
    updatedAt: detail.updatedAt,
    messages: detail.messages,
    last_speaker_name: detail.last_speaker_name ?? existing.last_speaker_name,
    last_spoken_at: detail.last_spoken_at ?? existing.last_spoken_at,
    inquirer_name: detail.inquirer_name ?? existing.inquirer_name,
  }
}

export function resolveKuAiConversationScope(userId: number | null | undefined): string | null {
  const tenantId = getTenantId();
  if (tenantId == null || userId == null) return null;
  return storageKey(String(tenantId), userId);
}

function readRaw(key: string): KuAiConversationRecord[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is KuAiConversationRecord =>
        item != null &&
        typeof item === 'object' &&
        typeof (item as KuAiConversationRecord).id === 'string' &&
        Array.isArray((item as KuAiConversationRecord).messages),
    );
  } catch {
    return [];
  }
}

function writeRaw(key: string, records: KuAiConversationRecord[]): void {
  const sorted = [...records].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_CONVERSATIONS);
  localStorage.setItem(key, JSON.stringify(sorted));
}

/** 仅用于从浏览器 localStorage 一次性导入服务端 */
export function listKuAiConversationsFromLocal(scopeKey: string): KuAiConversationRecord[] {
  return readRaw(scopeKey).sort((a, b) => b.updatedAt - a.updatedAt);
}

export function clearKuAiConversationsLocal(scopeKey: string): void {
  localStorage.removeItem(scopeKey);
}

export function listKuAiConversations(scopeKey: string): KuAiConversationRecord[] {
  return listKuAiConversationsFromLocal(scopeKey);
}

export function loadKuAiConversation(scopeKey: string, id: string): KuAiConversationRecord | undefined {
  return readRaw(scopeKey).find((item) => item.id === id);
}

export function createKuAiConversationId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `kuai-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function upsertKuAiConversation(
  scopeKey: string,
  record: KuAiConversationRecord,
): KuAiConversationRecord[] {
  const list = readRaw(scopeKey).filter((item) => item.id !== record.id);
  list.push(record);
  writeRaw(scopeKey, list);
  return listKuAiConversations(scopeKey);
}

export function deleteKuAiConversation(scopeKey: string, id: string): KuAiConversationRecord[] {
  writeRaw(
    scopeKey,
    readRaw(scopeKey).filter((item) => item.id !== id),
  );
  return listKuAiConversations(scopeKey);
}

export function deriveKuAiConversationTitle(
  messages: KuAiStoredMessage[],
  fallbackTitle: string,
): string {
  const firstUser = messages.find((m) => m.role === 'user' && m.content.trim());
  if (!firstUser) return fallbackTitle;
  const text = firstUser.content.trim().replace(/\s+/g, ' ');
  if (text.length <= 28) return text;
  return `${text.slice(0, 28)}…`;
}
