/**
 * DeepSeek 对话集成（平台核心能力，不依赖专业包 kuaiai）。
 * API Key / 开关由站点设置统一管理，经后端代理调用。
 */

import { DeepSeekChatProvider } from '@ant-design/x-sdk';
import { apiRequest, API_BASE_URL, buildAuthTenantHeaders } from './api';
import i18n from '../config/i18n';

const DEEPSEEK_STATUS_URL = '/core/site-settings/integrations/deepseek/status';
/** canonical AI Runtime 对话端点（site-settings 旧别名仅保留兼容，前端不再调用；
 *  该端点要求 kuaiai:act:execute，403/404/400 透出真实 detail/error.message） */
export const AI_RUNTIME_COMPLETIONS_PATH = '/core/ai/chat/completions';

export const KUAI_CHAT_COMPLETIONS_URL = `${API_BASE_URL}${AI_RUNTIME_COMPLETIONS_PATH}`;

export interface ChatIntegrationStatus {
  configured: boolean;
  enabled: boolean;
  model: string;
}

/** 去掉 DeepSeek 思考链标记，仅展示对用户可见的正文 */
export function stripAssistantThinkContent(text: string): string {
  if (!text) return '';
  return text
    .replace(/<think[^>]*>[\s\S]*?<\/think>/gi, '')
    .replace(/<think>[\s\S]*?<\/redacted_thinking>/gi, '')
    .replace(/<think[^>]*>[\s\S]*/gi, '')
    .replace(/<think>[\s\S]*/gi, '')
    .replace(/<\/?think[^>]*>/gi, '')
    .replace(/<\/?redacted_thinking>/gi, '')
    .trim();
}

type DeepSeekChoice = {
  delta?: { content?: string; role?: string };
  message?: { content?: string; role?: string };
};

export type KuaiToolTrace = {
  phase: 'start' | 'end';
  name: string;
  argsSummary?: string;
  resultSummary?: string;
};

/** spec 193/194：`kuaiai_interrupt` 帧里的一个待确认动作（写类 Tool） */
export type KuaiInterruptAction = {
  /** 后端 Tool 名 */
  tool: string;
  /** 目录中文显示名（后端下发，前端不翻译） */
  label: string;
  argsSummary?: string;
  businessObject?: string;
};

/** spec 193/194：HITL 待确认（不透明 thread_token + 过期时间 + 动作列表） */
export type KuaiInterrupt = {
  threadToken: string;
  expiresAt?: string;
  actions: KuaiInterruptAction[];
};

type DeepSeekChunk = {
  choices?: DeepSeekChoice[];
  kuaiai_tool?: {
    phase?: string;
    name?: string;
    args_summary?: string;
    result_summary?: string;
  };
  kuaiai_interrupt?: {
    thread_token?: string;
    expires_at?: string;
    actions?: Array<{
      tool?: string;
      label?: string;
      args_summary?: string;
      business_object?: string;
    }>;
  };
};

function readToolTrace(raw: DeepSeekChunk['kuaiai_tool']): KuaiToolTrace | null {
  if (!raw || (raw.phase !== 'start' && raw.phase !== 'end')) return null;
  const name = typeof raw.name === 'string' ? raw.name.trim() : '';
  if (!name) return null;
  const trace: KuaiToolTrace = { phase: raw.phase, name };
  if (raw.args_summary) trace.argsSummary = raw.args_summary;
  if (raw.result_summary) trace.resultSummary = raw.result_summary;
  return trace;
}

/** `kuaiai_interrupt` 帧 → 待确认载荷；token 缺失视为无中断。 */
export function readKuaiInterrupt(
  raw: DeepSeekChunk['kuaiai_interrupt'],
): KuaiInterrupt | null {
  if (!raw || typeof raw !== 'object') return null;
  const threadToken = typeof raw.thread_token === 'string' ? raw.thread_token.trim() : '';
  if (!threadToken) return null;
  const actions = (Array.isArray(raw.actions) ? raw.actions : [])
    .map((action): KuaiInterruptAction | null => {
      const tool = typeof action?.tool === 'string' ? action.tool.trim() : '';
      if (!tool) return null;
      const label = typeof action?.label === 'string' && action.label.trim()
        ? action.label.trim()
        : tool;
      return {
        tool,
        label,
        ...(action?.args_summary ? { argsSummary: action.args_summary } : {}),
        ...(action?.business_object ? { businessObject: action.business_object } : {}),
      };
    })
    .filter((a): a is KuaiInterruptAction => a !== null);
  return {
    threadToken,
    ...(typeof raw.expires_at === 'string' && raw.expires_at ? { expiresAt: raw.expires_at } : {}),
    actions,
  };
}

/** 结束帧合并到同名未结束的开始帧，避免抽屉里同一调用占两行。 */
export function mergeToolTrace(origin: KuaiToolTrace[] | undefined, next: KuaiToolTrace): KuaiToolTrace[] {
  const list = origin ? [...origin] : [];
  if (next.phase === 'end') {
    for (let i = list.length - 1; i >= 0; i -= 1) {
      if (list[i].phase === 'start' && list[i].name === next.name) {
        list[i] = { ...list[i], ...next, phase: 'end' };
        return list;
      }
    }
  }
  list.push(next);
  return list;
}

/**
 * 不展示 reasoning_content / think 区块，仅保留回答正文。
 * `kuaiai_interrupt` 帧不拼进正文，透传为 message.interrupt（确认卡渲染）。
 */
export class KuaiDeepSeekChatProvider<
  ChatMessage extends {
    role?: string;
    content?: string;
    toolTraces?: KuaiToolTrace[];
    interrupt?: KuaiInterrupt;
  } = {
    role?: string;
    content?: string;
    toolTraces?: KuaiToolTrace[];
    interrupt?: KuaiInterrupt;
  },
  Input = Record<string, unknown>,
  Output = Record<string, unknown>,
> extends DeepSeekChatProvider<ChatMessage, Input, Output> {
  transformMessage(info: Parameters<DeepSeekChatProvider<ChatMessage, Input, Output>['transformMessage']>[0]) {
    const { originMessage, chunk, responseHeaders } = info;
    let currentContent = '';
    let role = 'assistant';
    let toolTraces = originMessage?.toolTraces;
    let interrupt = originMessage?.interrupt;

    try {
      let message: DeepSeekChunk | undefined;
      if (responseHeaders.get('content-type')?.includes('text/event-stream')) {
        if (chunk && (chunk as { data?: string }).data?.trim() !== '[DONE]') {
          message = JSON.parse((chunk as { data: string }).data) as DeepSeekChunk;
        }
      } else {
        message = chunk as DeepSeekChunk;
      }

      const trace = readToolTrace(message?.kuaiai_tool);
      if (trace) toolTraces = mergeToolTrace(toolTraces, trace);

      const nextInterrupt = readKuaiInterrupt(message?.kuaiai_interrupt);
      if (nextInterrupt) interrupt = nextInterrupt;

      message?.choices?.forEach((choice) => {
        if (choice?.delta) {
          currentContent += choice.delta.content || '';
          role = choice.delta.role || role;
        } else if (choice?.message) {
          currentContent += choice.message.content || '';
          role = choice.message.role || role;
        }
      });
    } catch {
      // ignore parse errors
    }

    const originRaw = originMessage?.content;
    const originMessageContent =
      typeof originRaw === 'string' ? originRaw : (originRaw as { text?: string } | undefined)?.text || '';

    return {
      content: stripAssistantThinkContent(`${originMessageContent}${currentContent}`),
      role: role || 'assistant',
      ...(toolTraces?.length ? { toolTraces } : {}),
      ...(interrupt ? { interrupt } : {}),
    } as ChatMessage;
  }
}

/** 与 apiRequest 一致：含 X-Client-Channel，否则写门禁对 POST 对话返回 403 */
export function buildKuaiChatAuthHeaders(): Record<string, string> {
  return buildAuthTenantHeaders();
}

export async function getChatIntegrationStatus(): Promise<ChatIntegrationStatus> {
  return apiRequest<ChatIntegrationStatus>(DEEPSEEK_STATUS_URL, {
    method: 'GET',
  });
}

export async function parseKuaiChatErrorResponse(response: Response): Promise<string> {
  let detail = i18n.t('ui.aiAssistant.chatRequestFailed', { status: response.status });
  try {
    const data = await response.clone().json();
    if (typeof data?.detail === 'string') {
      detail = data.detail;
    } else if (data?.detail?.message) {
      detail = String(data.detail.message);
    } else if (data?.error?.message) {
      detail = String(data.error.message);
    } else if (data?.message) {
      detail = String(data.message);
    }
  } catch {
    // ignore parse errors
  }
  if (response.status === 404 && (detail === 'Not Found' || detail.includes('Not Found'))) {
    return i18n.t('ui.aiAssistant.chatUnavailable');
  }
  return detail;
}
