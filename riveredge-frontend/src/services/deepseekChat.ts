/**
 * DeepSeek 对话集成（平台核心能力，不依赖专业包 kuaiai）。
 * API Key / 开关由站点设置统一管理，经后端代理调用。
 */

import { DeepSeekChatProvider } from '@ant-design/x-sdk';
import { apiRequest, API_BASE_URL } from './api';
import { getToken } from '../utils/auth';
import i18n from '../config/i18n';

const DEEPSEEK_STATUS_URL = '/core/site-settings/integrations/deepseek/status';
const DEEPSEEK_COMPLETIONS_PATH = '/core/site-settings/integrations/deepseek/completions';
/** 新 AI Runtime 网关（与 site-settings 路径等价，stream 由后端统一处理） */
export const AI_RUNTIME_COMPLETIONS_PATH = '/core/ai/chat/completions';

export const KUAI_CHAT_COMPLETIONS_URL = `${API_BASE_URL}${DEEPSEEK_COMPLETIONS_PATH}`;

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

type DeepSeekChunk = {
  choices?: DeepSeekChoice[];
  kuaiai_tool?: {
    phase?: string;
    name?: string;
    args_summary?: string;
    result_summary?: string;
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
 */
export class KuaiDeepSeekChatProvider<
  ChatMessage extends { role?: string; content?: string; toolTraces?: KuaiToolTrace[] } = {
    role?: string;
    content?: string;
    toolTraces?: KuaiToolTrace[];
  },
  Input = Record<string, unknown>,
  Output = Record<string, unknown>,
> extends DeepSeekChatProvider<ChatMessage, Input, Output> {
  transformMessage(info: Parameters<DeepSeekChatProvider<ChatMessage, Input, Output>['transformMessage']>[0]) {
    const { originMessage, chunk, responseHeaders } = info;
    let currentContent = '';
    let role = 'assistant';
    let toolTraces = originMessage?.toolTraces;

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
    } as ChatMessage;
  }
}

export function buildKuaiChatAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const tenantId = localStorage.getItem('tenant_id');
  if (tenantId?.trim()) headers['X-Tenant-ID'] = tenantId.trim();
  return headers;
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
