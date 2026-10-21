import { nowSiteDateTimeString } from '../../utils/formDate';

import type { KuAiStoredMessage } from './kuAiConversationStore';

export type KuAiMessageMeta = {
  speaker_name: string;
  spoken_at: string;
};

export function serializeKuAiMessagesForApi(messages: KuAiStoredMessage[]): KuAiStoredMessage[] {
  return messages.map((m) => ({
    role: m.role,
    content: m.content,
    speaker_name: m.speaker_name,
    spoken_at: m.spoken_at,
  }));
}

/** 判断会话消息是否变化（切换会话加载详情时不应触发置顶/落库） */
export function kuAiConversationMessagesFingerprint(
  conversationId: string,
  messages: KuAiStoredMessage[],
): string {
  return `${conversationId}\n${JSON.stringify(serializeKuAiMessagesForApi(messages))}`;
}

export function buildXChatMessagesFromKuAiStored(
  conversationId: string,
  stored: KuAiStoredMessage[],
): Array<{ id: string; message: { role: string; content: string }; status: 'success' }> {
  return stored.map((m, index) => ({
    id: `stored-${conversationId}-${index}`,
    message: { role: m.role, content: m.content },
    status: 'success' as const,
  }));
}

export function resolveKuAiUserDisplayName(
  user: { id?: number | string; full_name?: string; username?: string } | null | undefined,
): string {
  const name = user?.full_name?.trim() || user?.username?.trim();
  if (name) return name;
  if (user?.id != null && String(user.id).trim()) return String(user.id).trim();
  return '';
}

export function buildKuAiStoredMessagesFromChat(params: {
  chatMessages: Array<{
    id: string | number;
    message: { role?: string; content?: unknown };
    status?: string;
  }>;
  metaById: Map<string, KuAiMessageMeta>;
  userDisplayName: string;
  assistantDisplayName: string;
  stripAssistantContent: (raw: string) => string;
}): KuAiStoredMessage[] {
  const { chatMessages, metaById, userDisplayName, assistantDisplayName, stripAssistantContent } =
    params;
  const out: KuAiStoredMessage[] = [];

  for (const item of chatMessages) {
    const role = item.message?.role;
    if (role !== 'user' && role !== 'assistant') continue;
    const raw = typeof item.message.content === 'string' ? item.message.content : '';
    const content = role === 'assistant' ? stripAssistantContent(raw) : raw;
    if (!content.trim() && role !== 'user') continue;
    if (role === 'assistant' && item.status !== 'success') continue;

    const id = String(item.id);
    let meta = metaById.get(id);
    if (!meta) {
      if (id.startsWith('stored-')) {
        out.push({ role, content });
        continue;
      }
      const speaker_name = role === 'user' ? userDisplayName : assistantDisplayName;
      if (speaker_name) {
        meta = { speaker_name, spoken_at: nowSiteDateTimeString() };
        metaById.set(id, meta);
      }
    }

    out.push({
      role,
      content,
      ...(meta
        ? { speaker_name: meta.speaker_name, spoken_at: meta.spoken_at }
        : {}),
    });
  }

  return out;
}

export function deriveKuAiInquirerName(messages: KuAiStoredMessage[]): string | undefined {
  for (const m of messages) {
    if (m.role !== 'user' || !m.content.trim()) continue;
    const name = m.speaker_name?.trim();
    if (name) return name;
    return undefined;
  }
  return undefined;
}

export function deriveKuAiLastMessageMeta(
  messages: KuAiStoredMessage[],
): { last_speaker_name?: string; last_spoken_at?: string } {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i]
    if (!m.content.trim()) continue
    return {
      last_speaker_name: m.speaker_name,
      last_spoken_at: m.spoken_at,
    }
  }
  return {}
}

export function seedKuAiMessageMetaFromStored(
  metaById: Map<string, KuAiMessageMeta>,
  conversationId: string,
  stored: KuAiStoredMessage[],
): void {
  stored.forEach((m, index) => {
    if (!m.speaker_name || !m.spoken_at) return;
    metaById.set(`stored-${conversationId}-${index}`, {
      speaker_name: m.speaker_name,
      spoken_at: m.spoken_at,
    });
  });
}
