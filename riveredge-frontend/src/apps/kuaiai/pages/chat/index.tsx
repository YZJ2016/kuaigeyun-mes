/**
 * 星AI 全宽对话页（/apps/kuaiai/chat）。
 *
 * - 左侧会话列表：新建（POST 后选中）/ 行内重命名（PATCH title）/ 删除（DELETE 确认后）；
 *   选中会话加载 listChatMessages 渲染历史（含 tool 轨迹）。
 * - 右上：档案下拉（agents/options，allowClear）。对话模型用应用连接器的对话选用连接。
 * - 发送：无会话且有 session:create 时先 createChatSession（带当前档案）→
 *   再走 POST /core/ai/chat/completions（SSE）；无 session:create 不自动建会话。
 *   流式累积渲染，流结束重拉 messages 拿服务端落库的 tool/assistant 行。
 *   发送权限码 kuaiai:act:execute。
 * - 会话恢复：地址 `?session=` 选中会话。有 agent_id 且仍在 options 内则恢复档案。
 *   失效档案只清本地选择，不删消息。
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
import { useSearchParams } from 'react-router-dom';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasPermission } from '../../../../utils/permission';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatMessages,
  listChatSessions,
  sendChatMessage,
  updateChatSession,
  type ChatSessionOut,
  type ChatSessionUpdatePayload,
} from '../../services/chatApi';
import { listAgentOptions } from '../../services/agents';
import { KUAI_AI_OPTION_KEYS } from '../../constants';
import ChatMessageList, { type PendingExchange } from './MessageList';
import { parseSessionQueryId, sessionSelectionPayload } from './sessionSelection';
import './index.less';

/** 每页条数（与后端 page_size 上限一致；首屏仍只拉第 1 页，更多靠「加载更多」） */
const SESSIONS_PAGE_SIZE = 200;

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

/** 有 total 时比累计条数；裸数组时满页即可能还有下一页 */
function sessionsPageHasMore(
  pageItems: ChatSessionOut[],
  pageSize: number,
  loadedCount: number,
  total?: number,
): boolean {
  if (total != null) return loadedCount < total;
  return pageItems.length >= pageSize;
}

const KuaiaiChatPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi, modal } = App.useApp();
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const canListSessions = hasPermission(currentUser, 'kuaiai:session:display');
  const canQuerySession = hasPermission(currentUser, 'kuaiai:session:read');
  const canAddSession = hasPermission(currentUser, 'kuaiai:session:create');
  const canEditSession = hasPermission(currentUser, 'kuaiai:session:update');
  const canRemoveSession = hasPermission(currentUser, 'kuaiai:session:delete');
  const canSend = hasPermission(currentUser, 'kuaiai:act:execute');

  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(() =>
    parseSessionQueryId(searchParams.get('session')),
  );
  const [agentId, setAgentId] = useState<number | undefined>(undefined);
  const [senderValue, setSenderValue] = useState('');
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<PendingExchange | null>(null);
  const [renaming, setRenaming] = useState<{ id: number; title: string } | null>(null);
  const [sessions, setSessions] = useState<ChatSessionOut[]>([]);
  // 不在已加载列表里、但 ?session= 指向的会话（例如不在第 1 页）
  const [extraSession, setExtraSession] = useState<ChatSessionOut | null>(null);
  const [sessionsPage, setSessionsPage] = useState(1);
  const [sessionsTotal, setSessionsTotal] = useState<number | undefined>(undefined);
  const [sessionsHasMore, setSessionsHasMore] = useState(false);
  const [loadingMoreSessions, setLoadingMoreSessions] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // 同步发送闸：React state 异步，同帧内两次 onSubmit 都会看到 sending=false
  const sendingRef = useRef(false);
  // 首屏 invalidate 时递增，丢弃进行中的「加载更多」结果，避免追加到已重置列表
  const sessionsListGenRef = useRef(0);
  // 同一会话连续切换时只采纳最后一次 PATCH，避免慢响应把下拉写回去
  const selectionWriteGenRef = useRef<Record<number, number>>({});
  const sessionProbeRef = useRef<number | null>(null);

  // ---------------- 数据 ----------------

  const sessionsQuery = useQuery({
    queryKey: ['kuaiai', 'chat-sessions'],
    queryFn: () => listChatSessions(1, SESSIONS_PAGE_SIZE),
    enabled: canListSessions,
  });

  // 首屏（或 invalidate 后）重置为第 1 页；已加载的后续页丢弃（选中会话/消息区不动）
  useEffect(() => {
    if (!sessionsQuery.data) return;
    sessionsListGenRef.current += 1;
    const { items, total } = sessionsQuery.data;
    setSessions(items);
    setSessionsPage(1);
    setSessionsTotal(total);
    setSessionsHasMore(sessionsPageHasMore(items, SESSIONS_PAGE_SIZE, items.length, total));
  }, [sessionsQuery.data]);

  const agentOptionsQuery = useQuery({
    queryKey: KUAI_AI_OPTION_KEYS.agents,
    queryFn: listAgentOptions,
    // /agents/options 需 kuaiai:agent:read；无权限不打 403，下拉恒空
    enabled: hasPermission(currentUser, 'kuaiai:agent:read'),
    retry: 1,
  });
  const agentOptions = useMemo(() => agentOptionsQuery.data ?? [], [agentOptionsQuery.data]);

  const displaySessions = useMemo(() => {
    if (extraSession && !sessions.some((s) => s.id === extraSession.id)) {
      return [extraSession, ...sessions];
    }
    return sessions;
  }, [extraSession, sessions]);

  const selectedSession = useMemo(
    () => displaySessions.find((s) => s.id === selectedSessionId),
    [displaySessions, selectedSessionId],
  );

  const selectedInLoadedSessions =
    selectedSessionId != null && sessions.some((s) => s.id === selectedSessionId);

  const messagesQuery = useQuery({
    queryKey: ['kuaiai', 'chat-messages', selectedSessionId],
    queryFn: () => listChatMessages(selectedSessionId as number),
    enabled: selectedSessionId != null && canQuerySession,
  });
  const messages = useMemo(() => messagesQuery.data ?? [], [messagesQuery.data]);

  // ---------------- 会话与右上角恢复 ----------------
  // 档案优先：agent_id 仍在 options 内则只恢复档案。否则按 #id: 或唯一模型名回显。
  // 失效档案只清本地选择，不改服务端、不删消息。

  useEffect(() => {
    if (!selectedSession) return;
    const sessionAgentId = selectedSession.agent_id;
    const agentValid =
      sessionAgentId != null && agentOptions.some((o) => o.id === sessionAgentId);
    setAgentId(agentValid ? sessionAgentId : undefined);
  }, [selectedSession, selectedSessionId, agentOptions]);

  // 选中 / 新建 / 删除后把 ?session= 写回路由；无效 query 去掉。replace 避免整页跳转。
  useEffect(() => {
    const raw = searchParams.get('session');
    const rawInvalid = raw != null && raw !== '' && parseSessionQueryId(raw) == null;
    const desired = selectedSessionId == null ? null : String(selectedSessionId);
    if (!rawInvalid && raw === desired) return;
    const next = new URLSearchParams(searchParams);
    if (desired == null) next.delete('session');
    else next.set('session', desired);
    setSearchParams(next, { replace: true });
  }, [searchParams, selectedSessionId, setSearchParams]);

  // 列表里没有该 id 时再查一次；404/403 视为无效并清掉 query，其它错误不抛到渲染。
  useEffect(() => {
    if (selectedSessionId == null) {
      sessionProbeRef.current = null;
      return;
    }
    if (canListSessions && !sessionsQuery.isSuccess) return;
    if (selectedInLoadedSessions) {
      sessionProbeRef.current = null;
      setExtraSession((prev) => (prev ? null : prev));
      return;
    }
    if (extraSession?.id === selectedSessionId) return;
    if (!canQuerySession) {
      if (canListSessions && sessionsQuery.isSuccess) {
        setSelectedSessionId((cur) => (cur === selectedSessionId ? null : cur));
      }
      return;
    }
    if (sessionProbeRef.current === selectedSessionId) return;
    sessionProbeRef.current = selectedSessionId;
    const id = selectedSessionId;
    let cancelled = false;
    getChatSession(id)
      .then((session) => {
        if (!cancelled) setExtraSession(session);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const status =
          error && typeof error === 'object' && 'response' in error
            ? (error as { response?: { status?: number } }).response?.status
            : undefined;
        if (status === 404 || status === 403) {
          setExtraSession((prev) => (prev?.id === id ? null : prev));
          setSelectedSessionId((cur) => (cur === id ? null : cur));
        } else {
          sessionProbeRef.current = null;
        }
      });
    return () => {
      cancelled = true;
      if (sessionProbeRef.current === id) sessionProbeRef.current = null;
    };
  }, [
    canListSessions,
    canQuerySession,
    extraSession?.id,
    selectedInLoadedSessions,
    selectedSessionId,
    sessionsQuery.isSuccess,
  ]);

  // 滚动到底部（新消息 / 流式增量）
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  useEffect(() => () => abortRef.current?.abort(), []);

  // ---------------- 会话操作 ----------------

  const applySessionUpdate = useCallback((session: ChatSessionOut) => {
    setSessions((prev) => {
      const index = prev.findIndex((s) => s.id === session.id);
      if (index === -1) return prev;
      const next = prev.slice();
      next[index] = session;
      return next;
    });
    setExtraSession((prev) => (prev && prev.id === session.id ? session : prev));
  }, []);

  const prependCreatedSession = useCallback((session: ChatSessionOut) => {
    setSessions((prev) => [session, ...prev.filter((s) => s.id !== session.id)]);
  }, []);

  const writeSessionSelection = useCallback(
    async (sessionId: number, payload: ChatSessionUpdatePayload) => {
      const gen = (selectionWriteGenRef.current[sessionId] ?? 0) + 1;
      selectionWriteGenRef.current[sessionId] = gen;
      try {
        const updated = await updateChatSession(sessionId, payload);
        if (selectionWriteGenRef.current[sessionId] !== gen) return;
        applySessionUpdate(updated);
      } catch (error) {
        if (selectionWriteGenRef.current[sessionId] !== gen) return;
        messageApi.error(
          getApiErrorMessage(
            error,
            t('app.kuaiai.chat.saveSelectionFailed', {
              defaultValue: '保存模型或档案选择失败',
            }),
          ),
        );
      }
    },
    [messageApi, applySessionUpdate, t],
  );

  const handleAgentChange = useCallback(
    (value: number | null | undefined) => {
      const next = value ?? undefined;
      setAgentId(next);
      if (selectedSessionId == null) return;
      void writeSessionSelection(
        selectedSessionId,
        next != null ? { agent_id: next, model: null } : { agent_id: null },
      );
    },
    [selectedSessionId, writeSessionSelection],
  );

  const invalidateSessions = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ['kuaiai', 'chat-sessions'] }),
    [queryClient],
  );

  const handleLoadMoreSessions = useCallback(async () => {
    if (loadingMoreSessions || !sessionsHasMore || !canListSessions) return;
    const gen = sessionsListGenRef.current;
    const nextPage = sessionsPage + 1;
    setLoadingMoreSessions(true);
    try {
      const { items, total } = await listChatSessions(nextPage, SESSIONS_PAGE_SIZE);
      if (gen !== sessionsListGenRef.current) return;
      const mergedTotal = total ?? sessionsTotal;
      const seen = new Set(sessions.map((s) => s.id));
      const appended = items.filter((s) => !seen.has(s.id));
      const next = appended.length ? [...sessions, ...appended] : sessions;
      setSessions(next);
      setSessionsPage(nextPage);
      if (total != null) setSessionsTotal(total);
      setSessionsHasMore(
        sessionsPageHasMore(items, SESSIONS_PAGE_SIZE, next.length, mergedTotal),
      );
    } catch (error) {
      if (gen !== sessionsListGenRef.current) return;
      messageApi.error(
        getApiErrorMessage(
          error,
          t('app.kuaiai.chat.loadMoreSessionsFailed', {
            defaultValue: '加载更多会话失败',
          }),
        ),
      );
    } finally {
      setLoadingMoreSessions(false);
    }
  }, [
    canListSessions,
    loadingMoreSessions,
    messageApi,
    sessions,
    sessionsHasMore,
    sessionsPage,
    sessionsTotal,
    t,
  ]);

  const handleNewSession = useCallback(async () => {
    try {
      const created = await createChatSession(
        sessionSelectionPayload(agentId, undefined),
      );
      prependCreatedSession(created);
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
  }, [agentId, invalidateSessions, messageApi, prependCreatedSession, t]);

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
            setExtraSession((prev) => (prev?.id === session.id ? null : prev));
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
      // 无会话时须有 session:create 才能自动建会话；按钮门控之外再拦发送路径
      if (selectedSessionId == null && !canAddSession) {
        const msg = t('app.kuaiai.chat.noAddSessionPermission', {
          defaultValue: '当前账号无新建会话权限（kuaiai:session:create），无法发送',
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
          const created = await createChatSession(
            sessionSelectionPayload(agentId, undefined),
          );
          sessionId = created.id;
          prependCreatedSession(created);
          setSelectedSessionId(created.id);
          setPending((p) => (p ? { ...p, sessionId } : p));
        }
        abortRef.current = new AbortController();
        await sendChatMessage({
          sessionId,
          content,
          agentId,
          signal: abortRef.current.signal,
          onDelta: (view) =>
            setPending((p) =>
              p ? { ...p, assistant: view.answer, reasoning: view.reasoning } : p,
            ),
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
        let reloaded = false;
        if (sessionId != null) {
          // 刚落库，忽略全局 staleTime，必须向服务器重拉 user/tool/assistant
          try {
            await queryClient.fetchQuery({
              queryKey: ['kuaiai', 'chat-messages', sessionId],
              queryFn: () => listChatMessages(sessionId as number),
              staleTime: 0,
            });
            reloaded = true;
          } catch {
            // 重拉失败则保留 pending，避免对话框先空掉
          }
          await invalidateSessions();
        }
        // 流失败或重拉失败都保留 pending（error 气泡 + 原始用户消息）
        if (!failed && reloaded) setPending(null);
      }
    },
    [
      agentId,
      canAddSession,
      canSend,
      invalidateSessions,
      messageApi,
      queryClient,
      prependCreatedSession,
      selectedSessionId,
      t,
    ],
  );

  const handleCancelSend = useCallback(() => {
    abortRef.current?.abort();
    // 取消时立刻清掉 pending；finally 只在重拉成功后清
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
          ) : displaySessions.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('app.kuaiai.chat.noSessions', { defaultValue: '暂无会话' })}
            />
          ) : (
            <>
              {displaySessions.map((s) => {
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
              })}
              {sessionsHasMore ? (
                <div className="kuaiai-chat-load-more">
                  <Button
                    type="link"
                    size="small"
                    block
                    loading={loadingMoreSessions}
                    disabled={loadingMoreSessions}
                    onClick={() => void handleLoadMoreSessions()}
                  >
                    {t('common.loadMore', { defaultValue: '加载更多' })}
                  </Button>
                </div>
              ) : null}
            </>
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
              onChange={handleAgentChange}
              options={agentOptions.map((o) => ({
                value: o.id,
                label: o.name,
                title: o.description || o.name,
              }))}
              loading={agentOptionsQuery.isLoading}
            />
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

        {/* 布局样式 `.ant-pro-layout-container footer { display: none }` 会藏掉 footer，输入区不能用 footer */}
        <div className="kuaiai-chat-composer">
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
        </div>
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
