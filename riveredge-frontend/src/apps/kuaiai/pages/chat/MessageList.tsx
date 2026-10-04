/**
 * KU-AI 全宽对话页消息列表。
 *
 * 渲染 user / assistant / tool 三角色：
 * - 同一条用户消息后的多轮工具调用收进正式回答下面的「推理过程」；
 * - 带 tool_calls 的 assistant 行只展示工具卡，不展示其 content（调用前的中间说明）；
 * - 推理过程里的工具结果仍可展开；
 * - 已被 assistant.tool_calls 认领的 tool 行不再单独渲染；
 * - 纯文本 assistant 走 Markdown（复用 AiAssistantMarkdown，只读引用）。
 */

import React, { useMemo } from 'react';
import { Collapse, Typography } from 'antd';
import { RobotOutlined, ToolOutlined, UserOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import AiAssistantMarkdown from '../../../../components/ai-assistant/AiAssistantMarkdown';
import { stripAssistantThinkContent } from '../../../../services/deepseekChat';
import type { ChatMessageOut, ChatToolCall, LiveReasoningStep } from '../../services/chatApi';

/** 本地发送中的一轮对话（流式累积态，流结束重拉服务端消息后移除） */
export interface PendingExchange {
  user: string;
  /** 正式回答。有工具时不含工具调用前的中间说明。 */
  assistant: string;
  /** 正式回答下面的工具调用。中间说明不放这里。 */
  reasoning?: LiveReasoningStep[];
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
  /** 流式阶段还没有落库结果时，用工具帧里的短摘要 */
  resultText?: string;
}

const ToolCallCard: React.FC<ToolCallCardProps> = ({ call, result, resultText }) => {
  const { t } = useTranslation();
  const label = t(`app.kuaiai.chat.tools.${call.name}`, {
    defaultValue: TOOL_NAME_LABELS[call.name] || call.name || '工具调用',
  });
  const body = result?.content || resultText || '';
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
      {body ? (
        <Collapse
          ghost
          size="small"
          className="kuaiai-tool-result-collapse"
          items={[
            {
              key: 'result',
              label: t('app.kuaiai.chat.toolResult', {
                defaultValue: '工具结果：{{name}}',
                name: result?.tool_name || call.name || '',
              }),
              children: <pre className="kuaiai-tool-result-body">{body}</pre>,
            },
          ]}
        />
      ) : null}
    </div>
  );
};

function hasToolCalls(message: ChatMessageOut): boolean {
  return message.role === 'assistant' && Array.isArray(message.tool_calls) && message.tool_calls.length > 0;
}

interface AssistantTurn {
  key: string;
  answer: ChatMessageOut | null;
  /** 正式回答以外的 assistant 行（带工具调用的中间轮次），按发生序 */
  steps: ChatMessageOut[];
}

/**
 * 同一条用户消息之后、下一条用户消息之前：
 * 最后一条不带工具调用的 assistant 是正式回答，其余 assistant 归入推理过程。
 */
function buildAssistantTurns(messages: ChatMessageOut[]): Array<
  | { kind: 'user'; message: ChatMessageOut }
  | { kind: 'turn'; turn: AssistantTurn }
  | { kind: 'tool'; message: ChatMessageOut }
> {
  const blocks: Array<
    | { kind: 'user'; message: ChatMessageOut }
    | { kind: 'turn'; turn: AssistantTurn }
    | { kind: 'tool'; message: ChatMessageOut }
  > = [];
  let index = 0;
  while (index < messages.length) {
    const current = messages[index];
    if (current.role === 'user') {
      blocks.push({ kind: 'user', message: current });
      index += 1;
      continue;
    }
    const start = index;
    while (index < messages.length && messages[index].role !== 'user') index += 1;
    const run = messages.slice(start, index);
    const assistants = run.filter((row) => row.role === 'assistant');
    let answer: ChatMessageOut | null = null;
    for (let cursor = assistants.length - 1; cursor >= 0; cursor -= 1) {
      if (!hasToolCalls(assistants[cursor])) {
        answer = assistants[cursor];
        break;
      }
    }
    const steps = assistants.filter((row) => row !== answer);
    if (answer || steps.length > 0) {
      const head = answer ?? steps[0];
      blocks.push({ kind: 'turn', turn: { key: `turn-${head.id}`, answer, steps } });
    }
    const claimed = new Set<string>();
    assistants.forEach((row) => {
      if (!Array.isArray(row.tool_calls)) return;
      row.tool_calls.forEach((call) => {
        if (call?.id) claimed.add(String(call.id));
      });
    });
    run.forEach((row) => {
      if (row.role !== 'tool') return;
      if (row.tool_call_id && claimed.has(String(row.tool_call_id))) return;
      blocks.push({ kind: 'tool', message: row });
    });
  }
  return blocks;
}

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

  const blocks = useMemo(() => buildAssistantTurns(messages), [messages]);

  const renderStep = (step: ChatMessageOut) => {
    const calls = Array.isArray(step.tool_calls) ? step.tool_calls.map(normalizeToolCall) : [];
    // 带工具调用的行：content 是调用前的中间说明，不当回答展示。工具卡保留。
    const prose = hasToolCalls(step) ? '' : stripAssistantThinkContent(step.content || '');
    return (
      <div key={step.id} className="kuaiai-reasoning-step">
        {calls.map((call, idx) => (
          <ToolCallCard
            key={call.id || idx}
            call={call}
            result={call.id ? toolResultMap.get(call.id) : undefined}
          />
        ))}
        {prose ? <div className="kuaiai-reasoning-text">{prose}</div> : null}
      </div>
    );
  };

  const renderLiveReasoning = (steps: LiveReasoningStep[]) => (
    <div className="kuaiai-reasoning-steps">
      {steps.map((step, idx) => (
        <div key={idx} className="kuaiai-reasoning-step">
          <ToolCallCard
            call={{
              id: '',
              name: step.tool.name,
              argsSummary: step.tool.argsSummary || '',
            }}
            resultText={step.tool.resultSummary}
          />
        </div>
      ))}
    </div>
  );

  const renderReasoning = (steps: ChatMessageOut[]) => (
    <Collapse
      ghost
      size="small"
      className="kuaiai-reasoning"
      defaultActiveKey={['reasoning']}
      items={[
        {
          key: 'reasoning',
          label: t('app.kuaiai.chat.reasoning', { defaultValue: '推理过程' }),
          children: <div className="kuaiai-reasoning-steps">{steps.map(renderStep)}</div>,
        },
      ]}
    />
  );

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

  const renderTurn = (turn: AssistantTurn) => {
    const answerText = stripAssistantThinkContent(turn.answer?.content || '');
    return (
      <div key={turn.key} className="kuaiai-msg kuaiai-msg--assistant">
        <div className="kuaiai-msg-avatar">
          <RobotOutlined />
        </div>
        <div className="kuaiai-msg-body">
          {answerText ? (
            <div className="kuaiai-msg-bubble kuaiai-msg-bubble--assistant">
              <AiAssistantMarkdown content={answerText} />
            </div>
          ) : null}
          {turn.steps.length > 0 ? renderReasoning(turn.steps) : null}
          {!answerText && turn.steps.length === 0 ? (
            <div className="kuaiai-msg-bubble kuaiai-msg-bubble--assistant kuaiai-msg-bubble--empty">
              <Typography.Text type="secondary">…</Typography.Text>
            </div>
          ) : null}
        </div>
      </div>
    );
  };

  return (
    <div className="kuaiai-chat-messages">
      {blocks.map((block) => {
        if (block.kind === 'user') {
          const m = block.message;
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
        if (block.kind === 'tool') return renderTool(block.message);
        return renderTurn(block.turn);
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
              {pending.reasoning && pending.reasoning.length > 0 ? (
                <Collapse
                  ghost
                  size="small"
                  className="kuaiai-reasoning"
                  defaultActiveKey={['reasoning']}
                  items={[
                    {
                      key: 'reasoning',
                      label: t('app.kuaiai.chat.reasoning', { defaultValue: '推理过程' }),
                      children: renderLiveReasoning(pending.reasoning),
                    },
                  ]}
                />
              ) : null}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
};

export default ChatMessageList;
