/**
 * KU-AI 会话/消息 REST + options + SSE 发送（spec 138 契约 C）。
 *
 * - 产品 REST 走 apiRequest（base 已含 /api/v1），路径前缀 /apps/kuaiai。
 * - 对话发送走现网网关 POST /api/v1/core/ai/chat/completions（kuaiai:act:execute），
 *   OpenAI chunk SSE 线格式；session_id / model_id 必须放 context.extra
 *   （AiBusinessContext.extra 会被摊平到顶层，顶层未声明键被 pydantic 丢弃），
 *   agent_id（string）为声明字段放顶层；选中档案时不传 model_id/knowledge_id。
 */

import { apiRequest, API_BASE_URL } from '../../../services/api';
import {
  buildKuaiChatAuthHeaders,
  parseKuaiChatErrorResponse,
  stripAssistantThinkContent,
} from '../../../services/deepseekChat';

const KUAI_AI_API = '/apps/kuaiai';
const CHAT_COMPLETIONS_URL = `${API_BASE_URL}/core/ai/chat/completions`;

// ============================================================ 类型

export interface ChatSessionOut {
  id: number;
  uuid: string;
  user_id: number;
  title: string;
  agent_id?: number | null;
  model?: string | null;
  last_message_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionCreatePayload {
  title?: string;
  agent_id?: number;
  model?: string;
}

export interface ChatSessionUpdatePayload {
  title?: string;
  agent_id?: number;
  model?: string;
}

/** 消息表 tool_calls 列存 OpenAI 线格式 {id,type,function:{name,arguments}}；
 * 兼容 LangChain 形态 {name,args,id}。 */
export interface ChatToolCall {
  id?: string;
  type?: string;
  name?: string;
  args?: unknown;
  function?: { name?: string; arguments?: unknown };
}

export interface ChatMessageOut {
  id: number;
  uuid: string;
  session_id: number;
  seq: number;
  role: 'user' | 'assistant' | 'tool' | string;
  content?: string | null;
  tool_calls?: ChatToolCall[] | null;
  tool_call_id?: string | null;
  tool_name?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  created_at: string;
}

// ============================================================ 会话 / 消息 REST

/** 会话列表页：后端现网回裸数组（丢弃 total）；兼容 {items,total} 信封。 */
export interface ChatSessionListPage {
  items: ChatSessionOut[];
  /** 有信封时带回；裸数组时为 undefined，由调用方用满页探测 */
  total?: number;
}

function normalizeSessionListPage(raw: unknown): ChatSessionListPage {
  if (Array.isArray(raw)) {
    return { items: raw as ChatSessionOut[] };
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    const items = Array.isArray(obj.items)
      ? (obj.items as ChatSessionOut[])
      : Array.isArray(obj.data)
        ? (obj.data as ChatSessionOut[])
        : [];
    const totalRaw = obj.total;
    const total =
      typeof totalRaw === 'number' && Number.isFinite(totalRaw) ? totalRaw : undefined;
    return { items, total };
  }
  return { items: [] };
}

export async function listChatSessions(
  page = 1,
  pageSize = 50,
): Promise<ChatSessionListPage> {
  const raw = await apiRequest<unknown>(`${KUAI_AI_API}/sessions`, {
    method: 'GET',
    params: { page, page_size: pageSize },
  });
  return normalizeSessionListPage(raw);
}

export function createChatSession(payload: ChatSessionCreatePayload): Promise<ChatSessionOut> {
  return apiRequest<ChatSessionOut>(`${KUAI_AI_API}/sessions`, {
    method: 'POST',
    data: payload,
  });
}

export function getChatSession(id: number): Promise<ChatSessionOut> {
  return apiRequest<ChatSessionOut>(`${KUAI_AI_API}/sessions/${id}`, { method: 'GET' });
}

export function updateChatSession(
  id: number,
  payload: ChatSessionUpdatePayload,
): Promise<ChatSessionOut> {
  return apiRequest<ChatSessionOut>(`${KUAI_AI_API}/sessions/${id}`, {
    method: 'PATCH',
    data: payload,
  });
}

export function deleteChatSession(id: number): Promise<void> {
  return apiRequest<void>(`${KUAI_AI_API}/sessions/${id}`, { method: 'DELETE' });
}

export function listChatMessages(sessionId: number): Promise<ChatMessageOut[]> {
  return apiRequest<ChatMessageOut[]>(`${KUAI_AI_API}/sessions/${sessionId}/messages`, {
    method: 'GET',
  });
}

// ============================================================ SSE 发送

export interface SendChatMessageOptions {
  sessionId: number;
  content: string;
  /** Agent 档案 ID；选中后走档案装配路径（后端忽略模型覆盖，不得再传 model_id） */
  agentId?: number | null;
  /** chat 模型目录行 ID；仅在无档案时生效 */
  modelId?: number | null;
  signal?: AbortSignal;
  /** 流式累积回调：每次增量到达时回传「当前完整正文」（已去 think 标记） */
  onDelta?: (fullText: string) => void;
}

type OpenAiChunk = {
  choices?: Array<{
    delta?: { content?: string };
    message?: { content?: string };
  }>;
  error?: { message?: string };
};

function accumulateChunk(chunk: OpenAiChunk, accumulated: string): string {
  let text = accumulated;
  chunk?.choices?.forEach((choice) => {
    const piece = choice?.delta?.content ?? choice?.message?.content ?? '';
    if (piece) text += piece;
  });
  return text;
}

/**
 * 发送一条用户消息并消费 SSE 流（手写 fetch + ReadableStream，按行解析 data: 帧）。
 * 返回 assistant 最终正文（已剥离 think 标记）；工具轨迹不落线格式，由调用方
 * 在流结束后重新拉 listChatMessages 展示。
 */
export async function sendChatMessage(options: SendChatMessageOptions): Promise<string> {
  const { sessionId, content, agentId, modelId, signal, onDelta } = options;

  const context: Record<string, unknown> = {
    ...(agentId ? { agent_id: String(agentId) } : {}),
    extra: {
      session_id: String(sessionId),
      // 选中档案时不下发模型覆盖（后端用档案 default_model_id）
      ...(agentId ? {} : modelId ? { model_id: modelId } : {}),
    },
  };

  const response = await fetch(CHAT_COMPLETIONS_URL, {
    method: 'POST',
    headers: {
      ...buildKuaiChatAuthHeaders(),
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      messages: [{ role: 'user', content }],
      stream: true,
      temperature: 0.7,
      context,
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(await parseKuaiChatErrorResponse(response));
  }

  // 非 SSE 回退（端点/网关异常时可能直接回 JSON）
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('text/event-stream')) {
    const data = (await response.json().catch(() => null)) as OpenAiChunk | null;
    if (data?.error?.message) {
      throw new Error(String(data.error.message));
    }
    const text = stripAssistantThinkContent(String(accumulateChunk(data ?? {}, '')));
    if (text) onDelta?.(text);
    return text;
  }

  const reader = response.body?.getReader();
  if (!reader) return '';

  const decoder = new TextDecoder();
  let buffer = '';
  let accumulated = '';

  const handleLine = (line: string) => {
    if (!line.startsWith('data:')) return;
    const payload = line.slice(5).trim();
    if (!payload || payload === '[DONE]') return;
    let parsed: OpenAiChunk;
    try {
      parsed = JSON.parse(payload) as OpenAiChunk;
    } catch {
      return; // 忽略不完整/非 JSON 帧
    }
    if (parsed?.error?.message) {
      throw new Error(String(parsed.error.message));
    }
    const next = accumulateChunk(parsed, accumulated);
    if (next !== accumulated) {
      accumulated = next;
      onDelta?.(stripAssistantThinkContent(accumulated));
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx = buffer.indexOf('\n');
      while (idx >= 0) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        handleLine(line.trim());
        idx = buffer.indexOf('\n');
      }
    }
    // 收尾：flush 解码器并处理残余缓冲（无尾换行的最后一行）
    buffer += decoder.decode();
    if (buffer.trim()) handleLine(buffer.trim());
  } finally {
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }

  return stripAssistantThinkContent(accumulated);
}
