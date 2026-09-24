/**
 * 星AI 全宽对话页（/apps/kuaiai/chat）。
 *
 * - 左侧会话列表：新建（POST 后选中）/ 行内重命名（PATCH title）/ 删除（DELETE 确认后）；
 *   选中会话加载 listChatMessages 渲染历史（含 tool 轨迹）。
 * - 右上：档案下拉（agents/options，allowClear）；无档案时显示 chat 模型下拉
 *   （llm-models/options?model_type=chat）；选中档案后隐藏模型下拉（不发模型覆盖）。
 * - 发送：无会话且有 session:add 时先 createChatSession（带当前 agent_id/模型名）→
 *   再走 POST /core/ai/chat/completions（SSE）；无 session:add 不自动建会话。
 *   流式累积渲染，流结束重拉 messages 拿服务端落库的 tool/assistant 行。
 *   发送权限码 kuaiai:act:execute。
 * - 会话恢复（KR-F5）：历史会话 agent_id 不在当前 options → 清空选择且发送
 *   不带 agent_id；切会话先清 modelId，仅无档案时按 session.model 回显；不删消息。
 * - 全宽页不传页上下文（screen/resource_key 等），不注册 useRegisterAiContext。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  App,
  Button,
  Dropdown,
  Empty,
  Input,
  Modal,
  Select,
  Spin,
  Typography,
} from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  MoreOutlined,
  PlusOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { Sender } from '@ant-design/x';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasPermission } from '../../../../utils/permission';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import {
  createChatSession,
  deleteChatSession,
  listChatMessages,
  listChatSessions,
  sendChatMessage,
  updateChatSession,
  type ChatSessionOut,
} from '../../services/chatApi';
import { listAgentOptions } from '../../services/agents';
import { listModelOptions } from '../../services/models';
import { KUAI_AI_OPTION_KEYS } from '../../constants';
import ChatMessageList, { type PendingExchange } from './MessageList';
import './index.less';

/** 会话侧栏拉取上限（后端 page_size 上限 200；侧栏即“最近会话”列表，超出部分不可达） */
const SESSIONS_PAGE_SIZE = 200;

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

const KuaiaiChatPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi, modal } = App.useApp();
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();

  const canListSessions = hasPermission(currentUser, 'kuaiai:session:list');
  const canQuerySession = hasPermission(currentUser, 'kuaiai:session:query');
  const canAddSession = hasPermission(currentUser, 'kuaiai:session:add');
  const canEditSession = hasPermission(currentUser, 'kuaiai:session:edit');
  const canRemoveSession = hasPermission(currentUser, 'kuaiai:session:remove');
  const canSend = hasPermission(currentUser, 'kuaiai:act:execute');

  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [agentId, setAgentId] = useState<number | undefined>(undefined);
  const [modelId, setModelId] = useState<number | undefined>(undefined);
  const [senderValue, setSenderValue] = useState('');
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<PendingExchange | null>(null);
  const [renaming, setRenaming] = useState<{ id: number; title: string } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // 同步发送闸：React state 异步，同帧内两次 onSubmit 都会看到 sending=false
  const sendingRef = useRef(false);

  // ---------------- 数据 ----------------

  const sessionsQuery = useQuery({
    queryKey: ['kuaiai', 'chat-sessions'],
    queryFn: () => listChatSessions(1, SESSIONS_PAGE_SIZE),
    enabled: canListSessions,
  });
  const sessions: ChatSessionOut[] = useMemo(
    () => sessionsQuery.data ?? [],
    [sessionsQuery.data],
  );

  const agentOptionsQuery = useQuery({
    queryKey: KUAI_AI_OPTION_KEYS.agents,
    queryFn: listAgentOptions,
    // /agents/options 需 kuaiai:agent:query；无权限不打 403，下拉恒空
    enabled: hasPermission(currentUser, 'kuaiai:agent:query'),
    retry: 1,
  });
  const agentOptions = useMemo(() => agentOptionsQuery.data ?? [], [agentOptionsQuery.data]);

  const modelOptionsQuery = useQuery({
    queryKey: KUAI_AI_OPTION_KEYS.chatModels,
    queryFn: () => listModelOptions('chat'),
    // /llm-models/options 需 kuaiai:model:query
    enabled: hasPermission(currentUser, 'kuaiai:model:query'),
    retry: 1,
  });
  const modelOptions = useMemo(() => modelOptionsQuery.data ?? [], [modelOptionsQuery.data]);

  const selectedSession = useMemo(
    () => sessions.find((s) => s.id === selectedSessionId),
    [sessions, selectedSessionId],
  );

  const messagesQuery = useQuery({
    queryKey: ['kuaiai', 'chat-messages', selectedSessionId],
    queryFn: () => listChatMessages(selectedSessionId as number),
    enabled: selectedSessionId != null && canQuerySession,
  });
  const messages = useMemo(() => messagesQuery.data ?? [], [messagesQuery.data]);

  const selectedModelName = useMemo(
    () => modelOptions.find((o) => o.id === modelId)?.model_name,
    [modelOptions, modelId],
  );

  // ---------------- KR-F5 会话恢复 ----------------
  // 选中会话的 agent_id 须在 options 内（有使用权且启用），否则清空且不带入 send；
  // 不删消息、不改服务端会话。无档案会话尝试按 session.model 名回显模型下拉。

  useEffect(() => {
    if (!selectedSession) return;
    // 切会话 / 失效档案路径：先清 modelId，避免上一会话残留成为无档案时的非预期 model 覆盖
    setModelId(undefined);
    const sessionAgentId = selectedSession.agent_id;
    const agentValid =
      sessionAgentId != null && agentOptions.some((o) => o.id === sessionAgentId);
    if (agentValid) {
      setAgentId(sessionAgentId);
      // 有档案：不回显/不发送 model_id（send 侧 agentId 存在则 omit）
      return;
    }
    setAgentId(undefined);
    // 无档案（含失效 agent 已清空）：仅从 session.model 回显
    if (selectedSession.model) {
      const hit = modelOptions.find((o) => o.model_name === selectedSession.model);
      if (hit) setModelId(hit.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSessionId, selectedSession?.agent_id, selectedSession?.model, agentOptions, modelOptions]);

  // 滚动到底部（新消息 / 流式增量）
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  useEffect(() => () => abortRef.current?.abort(), []);

  // ---------------- 会话操作 ----------------

  const invalidateSessions = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['kuaiai', 'chat-sessions'] }),
    [queryClient],
  );

  const handleNewSession = useCallback(async () => {
    try {
      // 带上当前档案/模型选择，避免选中后 KR-F5 恢复逻辑清空用户已选项
      const created = await createChatSession({
        ...(agentId ? { agent_id: agentId } : {}),
        ...(!agentId && selectedModelName ? { model: selectedModelName } : {}),
      });
      setSelectedSessionId(created.id);
      await invalidateSessions();
    } catch (error) {
      messageApi.error(
        getApiErrorMessage(
          error,
          t('app.kuaiai.chat.createSessionFailed', { defaultValue: '新建会话失败' }),
        ),
      );
    }
  }, [agentId, invalidateSessions, messageApi, selectedModelName, t]);

  const handleRename = useCallback(async () => {
    if (!renaming) return;
    const title = renaming.title.trim();
    if (!title) return;
    try {
      await updateChatSession(renaming.id, { title });
      setRenaming(null);
      await invalidateSessions();
    } catch (error) {
      messageApi.error(
        getApiErrorMessage(
          error,
          t('app.kuaiai.chat.renameFailed', { defaultValue: '重命名失败' }),
        ),
      );
    }
  }, [invalidateSessions, messageApi, renaming, t]);

  const handleDelete = useCallback(
    (session: ChatSessionOut) => {
      modal.confirm({
        title: t('app.kuaiai.chat.deleteConfirmTitle', { defaultValue: '删除会话' }),
        content: t('app.kuaiai.chat.deleteConfirmContent', {
          defaultValue: '确认删除会话「{{title}}」及其全部消息？',
          title: session.title || `#${session.id}`,
        }),
        okButtonProps: { danger: true },
        onOk: async () => {
          try {
            await deleteChatSession(session.id);
            if (selectedSessionId === session.id) {
              setSelectedSessionId(null);
            }
            await invalidateSessions();
          } catch (error) {
            messageApi.error(
              getApiErrorMessage(
                error,
                t('app.kuaiai.chat.deleteFailed', { defaultValue: '删除会话失败' }),
              ),
            );
          }
        },
      });
    },
    [invalidateSessions, messageApi, modal, selectedSessionId, t],
  );

  // ---------------- 发送 ----------------

  const handleSend = useCallback(
    async (raw: string) => {
      const content = (raw || '').trim();
      // sendingRef 同步拦截同帧重复提交（setSending 异步来不及生效）
      if (!content || sendingRef.current || !canSend) return;
      // 无会话时须有 session:add 才能自动建会话；按钮门控之外再拦发送路径
      if (selectedSessionId == null && !canAddSession) {
        const msg = t('app.kuaiai.chat.noAddSessionPermission', {
          defaultValue: '当前账号无新建会话权限（kuaiai:session:add），无法发送',
        });
        setSenderValue(content);
        messageApi.error(msg);
        return;
      }
      sendingRef.current = true;
      setSending(true);
      setPending({ user: content, assistant: '', sessionId: selectedSessionId });
      let sessionId = selectedSessionId;
      let failed = false;
      try {
        if (sessionId == null) {
          const created = await createChatSession({
            ...(agentId ? { agent_id: agentId } : {}),
            ...(!agentId && selectedModelName ? { model: selectedModelName } : {}),
          });
          sessionId = created.id;
          setSelectedSessionId(created.id);
          setPending((p) => (p ? { ...p, sessionId } : p));
        }
        abortRef.current = new AbortController();
        await sendChatMessage({
          sessionId,
          content,
          agentId,
          modelId: agentId ? undefined : modelId,
          signal: abortRef.current.signal,
          onDelta: (full) =>
            setPending((p) => (p ? { ...p, assistant: full } : p)),
        });
      } catch (error) {
        if (!isAbortError(error)) {
          failed = true;
          const msg = getApiErrorMessage(
            error,
            t('app.kuaiai.chat.sendFailed', { defaultValue: '发送失败' }),
          );
          // 保留 pending.error 气泡原位展示失败；回填输入框便于重试
          setPending((p) => (p ? { ...p, error: msg } : p));
          setSenderValue(content);
          messageApi.error(msg);
        }
      } finally {
        sendingRef.current = false;
        setSending(false);
        abortRef.current = null;
        if (sessionId != null) {
          // 流结束重拉：拿服务端落库的 user/tool/assistant 行（工具轨迹唯一来源）
          await queryClient
            .fetchQuery({
              queryKey: ['kuaiai', 'chat-messages', sessionId],
              queryFn: () => listChatMessages(sessionId as number),
            })
            .catch(() => undefined);
          await invalidateSessions();
        }
        // 失败时保留 pending（error 气泡 + 原始用户消息），下一次发送/取消时覆盖
        if (!failed) setPending(null);
      }
    },
    [
      agentId,
      canAddSession,
      canSend,
      invalidateSessions,
      messageApi,
      modelId,
      queryClient,
      selectedModelName,
      selectedSessionId,
      t,
    ],
  );

  const handleCancelSend = useCallback(() => {
    abortRef.current?.abort();
    // 取消时清掉 pending（abort 路径 failed=false，finally 也会清）
    setPending(null);
  }, []);

  // ---------------- 渲染 ----------------

  const sessionMenuItems = (session: ChatSessionOut) => {
    const items: { key: string; label: React.ReactNode; danger?: boolean }[] = [];
    if (canEditSession) {
      items.push({
        key: 'rename',
        label: (
          <>
            <EditOutlined /> {t('app.kuaiai.chat.rename', { defaultValue: '重命名' })}
          </>
        ),
      });
    }
    if (canRemoveSession) {
      items.push({
        key: 'delete',
        danger: true,
        label: (
          <>
            <DeleteOutlined /> {t('app.kuaiai.chat.delete', { defaultValue: '删除' })}
          </>
        ),
      });
    }
    return items;
  };

  // pending 绑定会话：发送中切换会话不把进行中的气泡渲染到别的会话里
  const visiblePending =
    pending && pending.sessionId === selectedSessionId ? pending : null;

  const showEmpty =
    selectedSessionId == null && messages.length === 0 && !visiblePending;

  return (
    <div className="kuaiai-chat-page">
      {/* 左：会话列表 */}
      <aside className="kuaiai-chat-sidebar">
        <div className="kuaiai-chat-sidebar-head">
          <Button
            type="primary"
            block
            icon={<PlusOutlined />}
            onClick={handleNewSession}
            disabled={!canAddSession}
          >
            {t('app.kuaiai.chat.newSession', { defaultValue: '新建会话' })}
          </Button>
        </div>
        <div className="kuaiai-chat-session-list">
          {sessionsQuery.isLoading ? (
            <div className="kuaiai-chat-list-loading">
              <Spin />
            </div>
          ) : sessions.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('app.kuaiai.chat.noSessions', { defaultValue: '暂无会话' })}
            />
          ) : (
            sessions.map((s) => {
              const menuItems = sessionMenuItems(s);
              return (
                <div
                  key={s.id}
                  className={`kuaiai-chat-session-item${
                    s.id === selectedSessionId ? ' is-active' : ''
                  }`}
                  onClick={() => setSelectedSessionId(s.id)}
                >
                  <div className="kuaiai-chat-session-main">
                    <div className="kuaiai-chat-session-title">
                      {s.title?.trim() ||
                        t('app.kuaiai.chat.untitledSession', { defaultValue: '未命名会话' })}
                    </div>
                    <div className="kuaiai-chat-session-time">
                      {s.last_message_at || s.updated_at
                        ? dayjs(s.last_message_at || s.updated_at).format('MM-DD HH:mm')
                        : ''}
                    </div>
                  </div>
                  {menuItems.length > 0 ? (
                    <Dropdown
                      trigger={['click']}
                      menu={{
                        items: menuItems,
                        onClick: ({ key, domEvent }) => {
                          domEvent.stopPropagation();
                          if (key === 'rename') {
                            setRenaming({ id: s.id, title: s.title || '' });
                          } else if (key === 'delete') {
                            handleDelete(s);
                          }
                        },
                      }}
                    >
                      <Button
                        type="text"
                        size="small"
                        icon={<MoreOutlined />}
                        className="kuaiai-chat-session-more"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Dropdown>
                  ) : null}
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* 右：对话区 */}
      <section className="kuaiai-chat-main">
        <header className="kuaiai-chat-main-head">
          <div className="kuaiai-chat-main-title">
            <RobotOutlined />
            <span>{t('app.kuaiai.chat.title', { defaultValue: '星AI 对话' })}</span>
            {selectedSession?.title ? (
              <Typography.Text type="secondary" className="kuaiai-chat-session-name">
                {selectedSession.title}
              </Typography.Text>
            ) : null}
          </div>
          <div className="kuaiai-chat-main-actions">
            <Select
              className="kuaiai-chat-select"
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaiai.chat.agentPlaceholder', {
                defaultValue: '选择档案（可选）',
              })}
              value={agentId}
              onChange={(v) => setAgentId(v ?? undefined)}
              options={agentOptions.map((o) => ({
                value: o.id,
                label: o.name,
                title: o.description || o.name,
              }))}
              loading={agentOptionsQuery.isLoading}
            />
            {!agentId ? (
              <Select
                className="kuaiai-chat-select"
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder={t('app.kuaiai.chat.modelPlaceholder', {
                  defaultValue: '选择模型（可选）',
                })}
                value={modelId}
                onChange={(v) => setModelId(v ?? undefined)}
                options={modelOptions.map((o) => ({
                  value: o.id,
                  label: o.provider_name ? `${o.provider_name}/${o.model_name}` : o.model_name,
                }))}
                loading={modelOptionsQuery.isLoading}
              />
            ) : null}
          </div>
        </header>

        <div className="kuaiai-chat-scroll" ref={scrollRef}>
          {showEmpty ? (
            <div className="kuaiai-chat-welcome">
              <RobotOutlined className="kuaiai-chat-welcome-icon" />
              <div className="kuaiai-chat-welcome-title">
                {t('app.kuaiai.chat.welcomeTitle', { defaultValue: '星AI 智能助手' })}
              </div>
              <div className="kuaiai-chat-welcome-desc">
                {t('app.kuaiai.chat.welcomeDesc', {
                  defaultValue: '选择档案或直接提问；选中会话可查看历史消息与工具轨迹。',
                })}
              </div>
            </div>
          ) : messagesQuery.isLoading ? (
            <div className="kuaiai-chat-list-loading">
              <Spin />
            </div>
          ) : (
            <ChatMessageList
              messages={messages}
              pending={visiblePending}
              loading={sending}
            />
          )}
        </div>

        <footer className="kuaiai-chat-composer">
          {!canSend ? (
            <Typography.Text type="secondary" className="kuaiai-chat-no-permission">
              {t('app.kuaiai.chat.noSendPermission', {
                defaultValue: '当前账号无对话发送权限（kuaiai:act:execute）',
              })}
            </Typography.Text>
          ) : null}
          <Sender
            value={senderValue}
            onChange={setSenderValue}
            onSubmit={(v) => {
              setSenderValue('');
              void handleSend(v);
            }}
            onCancel={handleCancelSend}
            loading={sending}
            disabled={!canSend}
            placeholder={t('app.kuaiai.chat.senderPlaceholder', {
              defaultValue: '输入问题，Enter 发送，Shift+Enter 换行',
            })}
            autoSize={{ minRows: 2, maxRows: 6 }}
          />
        </footer>
      </section>

      {/* 重命名弹窗 */}
      <Modal
        open={renaming != null}
        title={t('app.kuaiai.chat.rename', { defaultValue: '重命名' })}
        okText={t('common.ok', { defaultValue: '确定' })}
        cancelText={t('common.cancel', { defaultValue: '取消' })}
        onOk={handleRename}
        onCancel={() => setRenaming(null)}
        destroyOnHidden
      >
        <Input
          value={renaming?.title ?? ''}
          maxLength={300}
          placeholder={t('app.kuaiai.chat.sessionTitlePlaceholder', {
            defaultValue: '请输入会话标题',
          })}
          onChange={(e) =>
            setRenaming((r) => (r ? { ...r, title: e.target.value } : r))
          }
          onPressEnter={handleRename}
        />
      </Modal>
    </div>
  );
};

export default KuaiaiChatPage;
