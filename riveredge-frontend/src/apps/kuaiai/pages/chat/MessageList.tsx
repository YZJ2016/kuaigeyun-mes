/**
 * KU-AI 全宽对话页消息列表。
 *
 * 渲染 user / assistant / tool 三角色：
 * - assistant 行带 tool_calls 时渲染工具调用块（工具名 + 参数摘要），
 *   并按 tool_call_id 匹配对应 role=tool 行展示工具名 + 结果文本（可折叠）；
 * - 已被 assistant.tool_calls 认领的 tool 行不再单独渲染；
 * - 纯文本 assistant 走 Markdown（复用 AiAssistantMarkdown，只读引用）。
 */

import React, { useMemo } from 'react';
import { Collapse, Typography } from 'antd';
import { RobotOutlined, ToolOutlined, UserOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import AiAssistantMarkdown from '../../../../components/ai-assistant/AiAssistantMarkdown';
import { stripAssistantThinkContent } from '../../../../services/deepseekChat';
import type { ChatMessageOut, ChatToolCall } from '../../services/chatApi';

/** 本地发送中的一轮对话（流式累积态，流结束重拉服务端消息后移除） */
export interface PendingExchange {
  user: string;
  assistant: string;
  error?: string;
  /** 归属会话；仅当与当前选中会话一致时才渲染（发送中切换会话不串场） */
  sessionId?: number | null;
}

/** 工具名 → 中文显示名（i18n defaultValue 兜底；与后端 Tool 闭集一致） */
const TOOL_NAME_LABELS: Record<string, string> = {
  search_knowledge: '检索知识库',
  query_workorder: '查询工单',
  list_workorder_tasks: '查询工序任务',
  submit_production_feedback: '提交报工',
  update_workorder_status: '更新工单状态',
};

const ARGS_SUMMARY_MAX = 160;

interface NormalizedToolCall {
  id: string;
  name: string;
  argsSummary: string;
}

/** 归一 OpenAI 线格式 {id,function:{name,arguments}} 与 LangChain 形态 {name,args,id} */
function normalizeToolCall(call: ChatToolCall): NormalizedToolCall {
  let name = '';
  let args: unknown;
  const fn = call?.function;
  if (fn && typeof fn === 'object') {
    name = fn.name || '';
    args = fn.arguments;
    if (typeof args === 'string') {
      try {
        args = JSON.parse(args);
      } catch {
        // 保留原始字符串
      }
    }
  } else {
    name = call?.name || '';
    args = call?.args;
  }
  let argsSummary = '';
  if (args !== undefined && args !== null && args !== '') {
    argsSummary = typeof args === 'string' ? args : JSON.stringify(args);
    if (argsSummary.length > ARGS_SUMMARY_MAX) {
      argsSummary = `${argsSummary.slice(0, ARGS_SUMMARY_MAX)}…`;
    }
  }
  return { id: call?.id ? String(call.id) : '', name, argsSummary };
}

interface ToolCallCardProps {
  call: NormalizedToolCall;
  result?: ChatMessageOut;
}

const ToolCallCard: React.FC<ToolCallCardProps> = ({ call, result }) => {
  const { t } = useTranslation();
  const label = t(`app.kuaiai.chat.tools.${call.name}`, {
    defaultValue: TOOL_NAME_LABELS[call.name] || call.name || '工具调用',
  });
  return (
    <div className="kuaiai-tool-call">
      <div className="kuaiai-tool-call-head">
        <ToolOutlined className="kuaiai-tool-call-icon" />
        <span className="kuaiai-tool-call-name">{label}</span>
        {call.argsSummary ? (
          <Typography.Text className="kuaiai-tool-call-args" code ellipsis={{ tooltip: true }}>
            {call.argsSummary}
          </Typography.Text>
        ) : null}
      </div>
      {result ? (
        <Collapse
          ghost
          size="small"
          className="kuaiai-tool-result-collapse"
          items={[
            {
              key: 'result',
              label: t('app.kuaiai.chat.toolResult', {
                defaultValue: '工具结果：{{name}}',
                name: result.tool_name || call.name || '',
              }),
              children: (
                <pre className="kuaiai-tool-result-body">{result.content || ''}</pre>
              ),
            },
          ]}
        />
      ) : null}
    </div>
  );
};

interface ChatMessageListProps {
  messages: ChatMessageOut[];
  pending?: PendingExchange | null;
  loading?: boolean;
}

const ChatMessageList: React.FC<ChatMessageListProps> = ({ messages, pending, loading }) => {
  const { t } = useTranslation();

  /** tool_call_id → role=tool 行 */
  const toolResultMap = useMemo(() => {
    const map = new Map<string, ChatMessageOut>();
    messages.forEach((m) => {
      if (m.role === 'tool' && m.tool_call_id) {
        map.set(String(m.tool_call_id), m);
      }
    });
    return map;
  }, [messages]);

  /** 被 assistant.tool_calls 认领的 tool_call_id 集合（其 tool 行不单独渲染） */
  const claimedToolCallIds = useMemo(() => {
    const set = new Set<string>();
    messages.forEach((m) => {
      if (m.role === 'assistant' && Array.isArray(m.tool_calls)) {
        m.tool_calls.forEach((call) => {
          const id = call?.id ? String(call.id) : '';
          if (id) set.add(id);
        });
      }
    });
    return set;
  }, [messages]);

  const renderAssistant = (m: ChatMessageOut) => {
    const calls = Array.isArray(m.tool_calls) ? m.tool_calls.map(normalizeToolCall) : [];
    const text = stripAssistantThinkContent(m.content || '');
    return (
      <div key={m.id} className="kuaiai-msg kuaiai-msg--assistant">
        <div className="kuaiai-msg-avatar">
          <RobotOutlined />
        </div>
        <div className="kuaiai-msg-body">
          {calls.map((call, idx) => (
            <ToolCallCard
              key={call.id || idx}
              call={call}
              result={call.id ? toolResultMap.get(call.id) : undefined}
            />
          ))}
          {text ? (
            <div className="kuaiai-msg-bubble kuaiai-msg-bubble--assistant">
              <AiAssistantMarkdown content={text} />
            </div>
          ) : null}
          {!text && calls.length === 0 ? (
            <div className="kuaiai-msg-bubble kuaiai-msg-bubble--assistant kuaiai-msg-bubble--empty">
              <Typography.Text type="secondary">…</Typography.Text>
            </div>
          ) : null}
        </div>
      </div>
    );
  };

  const renderTool = (m: ChatMessageOut) => (
    // 未被认领的孤儿 tool 行（窗口截断/脏数据）也兜底展示
    <div key={m.id} className="kuaiai-msg kuaiai-msg--assistant">
      <div className="kuaiai-msg-avatar">
        <ToolOutlined />
      </div>
      <div className="kuaiai-msg-body">
        <Collapse
          ghost
          size="small"
          className="kuaiai-tool-result-collapse"
          items={[
            {
              key: 'result',
              label: t('app.kuaiai.chat.toolResult', {
                defaultValue: '工具结果：{{name}}',
                name: m.tool_name || '',
              }),
              children: <pre className="kuaiai-tool-result-body">{m.content || ''}</pre>,
            },
          ]}
        />
      </div>
    </div>
  );

  return (
    <div className="kuaiai-chat-messages">
      {messages.map((m) => {
        if (m.role === 'user') {
          return (
            <div key={m.id} className="kuaiai-msg kuaiai-msg--user">
              <div className="kuaiai-msg-body">
                <div className="kuaiai-msg-bubble kuaiai-msg-bubble--user">{m.content}</div>
              </div>
              <div className="kuaiai-msg-avatar">
                <UserOutlined />
              </div>
            </div>
          );
        }
        if (m.role === 'tool') {
          if (m.tool_call_id && claimedToolCallIds.has(String(m.tool_call_id))) {
            return null;
          }
          return renderTool(m);
        }
        return renderAssistant(m);
      })}

      {pending ? (
        <>
          <div className="kuaiai-msg kuaiai-msg--user">
            <div className="kuaiai-msg-body">
              <div className="kuaiai-msg-bubble kuaiai-msg-bubble--user">{pending.user}</div>
            </div>
            <div className="kuaiai-msg-avatar">
              <UserOutlined />
            </div>
          </div>
          <div className="kuaiai-msg kuaiai-msg--assistant">
            <div className="kuaiai-msg-avatar">
              <RobotOutlined />
            </div>
            <div className="kuaiai-msg-body">
              <div className="kuaiai-msg-bubble kuaiai-msg-bubble--assistant">
                {pending.error ? (
                  <Typography.Text type="danger">{pending.error}</Typography.Text>
                ) : pending.assistant ? (
                  <AiAssistantMarkdown content={pending.assistant} />
                ) : (
                  <span className="kuaiai-msg-loading">
                    {loading !== false
                      ? t('app.kuaiai.chat.thinking', { defaultValue: '思考中…' })
                      : null}
                  </span>
                )}
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
};

export default ChatMessageList;
