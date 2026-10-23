import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { createCache, StyleProvider } from '@ant-design/cssinjs'
import { message, Button, Spin, theme, Tag, Empty, Popconfirm, Result } from 'antd'
import BorderBeam from 'antd/es/border-beam'
import {
  CloseOutlined,
  CopyOutlined,
  ReloadOutlined,
  PlusOutlined,
  CaretDownOutlined,
  FullscreenOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import { Bubble, Prompts, Sender } from '@ant-design/x'
import type { PromptsItemType } from '@ant-design/x'
import { useXChat, XRequest } from '@ant-design/x-sdk'
import { chatMessagesStoreHelper } from '@ant-design/x-sdk/es/x-chat/store'
import Lottie from 'lottie-react'
import { useTranslation } from 'react-i18next'
import {
  buildKuaiChatAuthHeaders,
  KuaiDeepSeekChatProvider,
  KUAI_CHAT_COMPLETIONS_URL,
  parseKuaiChatErrorResponse,
  stripAssistantThinkContent,
  type ChatIntegrationStatus,
  type KuaiInterrupt,
  type KuaiToolTrace,
} from '../../services/deepseekChat'
import { useChatIntegrationStatus } from '../../hooks/useChatIntegrationStatus'
import { useCurrentUser } from '../../hooks/useCurrentUser'
import { hasPermission } from '../../utils/permission'
import { useAiContext, toAiContextApiPayload, type AiContextPayload } from '../../contexts/AiContext'
import { executeAiAction } from '../../apps/kuaiai/services/catalog'
import {
  ChatResumeGoneError,
  createChatSession,
  profileHasWriteTools,
  resumeChat,
  type ChatResumeDecision,
  type LiveReasoningStep,
} from '../../apps/kuaiai/services/chatApi'
import ToolConfirmCard, {
  type ToolConfirmStatus,
} from '../../apps/kuaiai/components/ToolConfirmCard'
import welcomeAnimation from '../../../static/lottie/welcome.json'
import { KuAiLottieMark } from './KuAiLottieMark'
import AiAssistantMarkdown from './AiAssistantMarkdown'
import { KUAIAI_ASSISTANT_TAB_PATH } from '../../constants/kuaiaiAssistantTab'
import { resolveSessionTenantScope } from '../../config/sessionQueries'
import { useCurrentUserQuery } from '../../hooks/useCurrentUserQuery'
import { getTenantId, getToken, getTokenTenantId, isInfraSuperAdminFromToken } from '../../utils/auth'
import { nowSiteDateTimeString } from '../../utils/formDate'
import {
  buildKuAiStoredMessagesFromChat,
  deriveKuAiInquirerName,
  deriveKuAiLastMessageMeta,
  resolveKuAiUserDisplayName,
  buildXChatMessagesFromKuAiStored,
  kuAiConversationMessagesFingerprint,
  seedKuAiMessageMetaFromStored,
  type KuAiMessageMeta,
} from './kuAiMessageMeta'
import {
  createKuAiConversationRemote,
  deleteKuAiConversationRemote,
  fetchKuAiConversationDetail,
  fetchKuAiConversationList,
  importKuAiConversationsRemote,
  upsertKuAiConversationKeepalive,
  upsertKuAiConversationRemote,
} from './kuAiConversationApi'
import {
  clearKuAiConversationsLocal,
  createKuAiConversationId,
  deriveKuAiConversationTitle,
  listKuAiConversationsFromLocal,
  mergeKuAiConversationDetailIntoRecord,
  moveKuAiConversationToFront,
  resolveKuAiConversationScope,
  shouldMoveKuAiThreadToFrontOnPersist,
  type KuAiConversationRecord,
  type KuAiStoredMessage,
} from './kuAiConversationStore'
import './index.less'

type XChatMessage = {
  role: string
  content: string
  toolTraces?: KuaiToolTrace[]
  /** spec 194：kuaiai_interrupt 帧载荷（HITL 待确认），不拼进正文 */
  interrupt?: KuaiInterrupt
}

/** spec 194：确认卡渲染所需的 per-message 附加上下文 */
type ConfirmExtra = {
  messageId?: string | number
  interrupt?: KuaiInterrupt
  confirmStatus?: ToolConfirmStatus
  confirmDeciding?: 'approve' | 'reject'
  confirmError?: string
}

/** Bubble.List 单条 item 形状（与 Ant Design X 默认对话样式一致） */
type BubbleItem = {
  key: string | number
  role: 'user' | 'ai'
  content: string
  status?: 'local' | 'loading' | 'updating' | 'success' | 'error' | 'abort'
  extraInfo?: { lastUserMessage?: string; toolTraces?: KuaiToolTrace[] } & ConfirmExtra
}

export interface AIAssistantProps {
  open?: boolean
  onClose?: () => void
  /**
   * 仅界面预览：不接入真实 API，用本地 mock 数据展示对话框样式。
   * 未传时根据站点设置中的 DeepSeek 集成配置自动判断。
   */
  designOnly?: boolean
}

const SCROLL_LOCK_CLASSES = ['ant-scrolling-effect', 'ant-modal-open'] as const

const SCROLL_LOCK_STYLE_KEYS = ['overflow', 'overflow-x', 'overflow-y', 'padding-right', 'width'] as const

const aiAssistantStyleCache = createCache()

function releaseScrollLockStyles(element: HTMLElement) {
  SCROLL_LOCK_STYLE_KEYS.forEach(key => {
    element.style.removeProperty(key)
  })
}

function releaseGlobalScrollLock() {
  const hasOtherOverlay = document.querySelector(
    '.ant-modal-wrap:not([aria-hidden="true"]), .ant-drawer-open, .ant-image-preview-wrap',
  )
  if (hasOtherOverlay) return

  releaseScrollLockStyles(document.body)
  releaseScrollLockStyles(document.documentElement)

  SCROLL_LOCK_CLASSES.forEach(className => {
    document.body.classList.remove(className)
    document.documentElement.classList.remove(className)
  })
}

function requestProLayoutReflow() {
  window.dispatchEvent(new Event('resize'))
  requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
}

function scheduleScrollLockRelease() {
  const run = () => {
    releaseGlobalScrollLock()
    requestProLayoutReflow()
  }

  run()
  const raf1 = requestAnimationFrame(run)
  const raf2 = requestAnimationFrame(() => requestAnimationFrame(run))
  const timeout0 = window.setTimeout(run, 0)
  const timeout50 = window.setTimeout(run, 50)

  return () => {
    cancelAnimationFrame(raf1)
    cancelAnimationFrame(raf2)
    window.clearTimeout(timeout0)
    window.clearTimeout(timeout50)
  }
}

function usePromptItems(): PromptsItemType[] {
  const { t } = useTranslation()
  return useMemo(
    () => [
      {
        key: 'work-order',
        label: t('ui.aiAssistant.prompt.workOrder'),
        icon: <span className="ai-qa-prompt-hash">#</span>,
      },
      {
        key: 'inventory',
        label: t('ui.aiAssistant.prompt.inventory'),
        icon: <span className="ai-qa-prompt-hash">#</span>,
      },
      {
        key: 'reporting',
        label: t('ui.aiAssistant.prompt.reporting'),
        icon: <span className="ai-qa-prompt-hash">#</span>,
      },
      {
        key: 'shortage-week',
        label: t('ui.aiAssistant.prompt.shortageWeek'),
        icon: <span className="ai-qa-prompt-hash">#</span>,
      },
      {
        key: 'delayed-orders',
        label: t('ui.aiAssistant.prompt.delayedOrders'),
        icon: <span className="ai-qa-prompt-hash">#</span>,
      },
      {
        key: 'progress',
        label: t('ui.aiAssistant.prompt.progress'),
        icon: <span className="ai-qa-prompt-hash">#</span>,
      },
    ],
    [t],
  )
}

function blurPanelFocus(shell: HTMLElement | null) {
  const active = document.activeElement
  if (active instanceof HTMLElement && shell?.contains(active)) {
    active.blur()
  }
}

const kuaiChatProviderCache = new Map<
  string,
  KuaiDeepSeekChatProvider<XChatMessage, Record<string, unknown>, Record<string, unknown>>
>()

function getKuaiChatProvider(model: string) {
  let provider = kuaiChatProviderCache.get(model)
  if (!provider) {
    provider = new KuaiDeepSeekChatProvider<XChatMessage, Record<string, unknown>, Record<string, unknown>>({
      request: buildKuaiChatRequest(model),
    })
    kuaiChatProviderCache.set(model, provider)
  }
  return provider
}

function buildKuaiChatRequest(model: string) {
  return XRequest(KUAI_CHAT_COMPLETIONS_URL, {
    manual: true,
    timeout: 120000,
    headers: buildKuaiChatAuthHeaders(),
    params: {
      model,
      stream: true,
      temperature: 0.7,
    },
    middlewares: {
      onRequest: async (url, options) => {
        const headers = {
          ...options.headers,
          ...buildKuaiChatAuthHeaders(),
          'Content-Type': 'application/json',
        }
        return [url, { ...options, headers }]
      },
      onResponse: async (response: Response) => {
        if (!response.ok) {
          throw new Error(await parseKuaiChatErrorResponse(response))
        }
        return response
      },
    },
  })
}

function extractConfirmToken(text: string): string | null {
  const jsonMatch = text.match(/"confirm_token"\s*:\s*"([^"]+)"/)
  if (jsonMatch?.[1]) return jsonMatch[1]
  const bareMatch = text.match(/confirm_token[:：]\s*([A-Za-z0-9_-]{16,})/)
  return bareMatch?.[1] ?? null
}

function renderAiBubbleContent(content: unknown) {
  const text = typeof content === 'string' ? content : ''
  if (!text.trim()) return null
  return <AiAssistantMarkdown content={text} />
}

/** spec 194：resume 流式 view 的工具步骤 → 抽屉 toolTraces 形态 */
function stepToToolTrace(step: LiveReasoningStep): KuaiToolTrace {
  return {
    phase: step.tool.resultSummary ? 'end' : 'start',
    name: step.tool.name,
    ...(step.tool.argsSummary ? { argsSummary: step.tool.argsSummary } : {}),
    ...(step.tool.resultSummary ? { resultSummary: step.tool.resultSummary } : {}),
  }
}

function ToolTraceList({ traces }: { traces: KuaiToolTrace[] }) {
  if (!traces.length) return null
  return (
    <ul className="ai-qa-tool-traces">
      {traces.map((trace, index) => (
        <li key={`${trace.name}-${index}`}>
          <span className="ai-qa-tool-trace-phase">
            {trace.phase === 'start' ? '正在调用' : '已调用'} {trace.name}
          </span>
          {trace.phase === 'start' && trace.argsSummary ? (
            <span className="ai-qa-tool-trace-detail">{trace.argsSummary}</span>
          ) : null}
          {trace.phase === 'end' && trace.resultSummary ? (
            <span className="ai-qa-tool-trace-detail">{trace.resultSummary}</span>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

type AIAssistantDialogUIProps = {
  open: boolean
  onClose?: () => void
  displayItems: BubbleItem[]
  isLoading: boolean
  onSubmit: (question: string) => void
  onNewChat: () => void
  senderDisabled?: boolean
  /** 输入框上方常显的禁用原因（如缺少 kuaiai:act:execute） */
  senderHint?: React.ReactNode
  welcomeHint?: React.ReactNode
  modelName?: string
  contextBadge?: string | null
  onConfirmAction?: (confirmToken: string) => void
  /** spec 194：HITL 确认卡决策回调（messageId → approve|reject） */
  onConfirmDecision?: (messageId: string | number, decision: 'approve' | 'reject') => void
  /** spec 194：确认卡倒计时归零回调 */
  onConfirmExpire?: (messageId: string | number) => void
  /** spec 194：resume 提交中，确认卡按钮禁用 */
  confirmBusy?: boolean
  embedded?: boolean
  embeddedSplit?: boolean
  canOpenAssistantTab?: boolean
  onOpenAssistantTab?: () => void
}

const AIAssistantDialogUI: React.FC<AIAssistantDialogUIProps> = ({
  open,
  onClose,
  displayItems,
  isLoading,
  onSubmit,
  onNewChat,
  senderDisabled = false,
  senderHint,
  welcomeHint,
  modelName,
  contextBadge,
  onConfirmAction,
  onConfirmDecision,
  onConfirmExpire,
  confirmBusy = false,
  embedded = false,
  embeddedSplit = false,
  canOpenAssistantTab = false,
  onOpenAssistantTab,
}) => {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const promptItems = usePromptItems()
  const { token } = theme.useToken()
  const [senderValue, setSenderValue] = useState('')
  const borderBeamColor = useMemo(
    () => [
      { color: token.colorPrimary, percent: 0 },
      { color: token.colorPrimaryHover, percent: 48 },
      { color: '#69b1ff', percent: 100 },
    ],
    [token.colorPrimary, token.colorPrimaryHover],
  )

  const handleCopy = (text: string) => {
    if (!text) return
    navigator.clipboard.writeText(text).then(
      () => message.success(t('ui.aiAssistant.copySuccess')),
      () => message.error(t('common.copyFailed')),
    )
  }

  const handleRegenerate = (lastUserMessage: string) => {
    if (!lastUserMessage?.trim() || senderDisabled || isLoading) return
    onSubmit(lastUserMessage.trim())
    setSenderValue('')
  }

  const handleSenderSubmit = useCallback(
    (value: string) => {
      const q = value?.trim?.() || ''
      if (!q || senderDisabled || isLoading) return
      onSubmit(value)
      setSenderValue('')
    },
    [isLoading, onSubmit, senderDisabled],
  )

  const handleNewChatClick = () => {
    onNewChat()
    setSenderValue('')
  }

  const handleOpenFullChat = () => {
    navigate('/apps/kuaiai/chat')
    onClose?.()
  }

  const senderFooter = useCallback(
    (_oriNode: React.ReactNode, { components }: { components: Record<string, React.ComponentType> }) => {
      const ActionBtn = isLoading ? components.LoadingButton : components.SendButton
      return (
        <div className={`ai-qa-sender-toolbar${modelName?.trim() ? '' : ' ai-qa-sender-toolbar--end'}`}>
          {modelName?.trim() ? (
            <span className="ai-qa-sender-model" title={modelName}>
              <span className="ai-qa-sender-model-name">{modelName}</span>
              <CaretDownOutlined className="ai-qa-sender-model-caret" />
            </span>
          ) : null}
          <ActionBtn />
        </div>
      )
    },
    [isLoading, modelName],
  )

  const senderProps = useMemo(
    () => ({
      placeholder: t('ui.aiAssistant.senderPlaceholder'),
      loading: isLoading,
      disabled: senderDisabled || !open,
      value: senderValue,
      onChange: setSenderValue,
      onSubmit: handleSenderSubmit,
      suffix: false as const,
      footer: senderFooter,
      autoSize: { minRows: 3, maxRows: 8 },
    }),
    [isLoading, open, senderDisabled, senderValue, handleSenderSubmit, senderFooter, t],
  )

  const qaContent = (
    <div className="ai-qa-layout">
      <header className="ai-qa-panel-header">
        <span className="ai-qa-panel-header-title">{t('ui.aiAssistant.title')}</span>
        <div className="ai-qa-panel-header-actions">
          {contextBadge ? (
            <Tag className="ai-qa-context-badge" color="processing" title={contextBadge}>
              {contextBadge}
            </Tag>
          ) : null}
          <Button
            type="text"
            icon={<PlusOutlined />}
            onClick={handleNewChatClick}
            className="ai-qa-header-icon-btn"
            aria-label={t('ui.aiAssistant.newChat')}
            title={t('ui.aiAssistant.newChat')}
          />
          {!embedded && canOpenAssistantTab && onOpenAssistantTab ? (
            <Button
              type="text"
              icon={<FullscreenOutlined />}
              onClick={onOpenAssistantTab}
              className="ai-qa-header-icon-btn"
              aria-label={t('ui.aiAssistant.openAssistantTab')}
              title={t('ui.aiAssistant.openAssistantTab')}
            />
          ) : !embedded ? (
            <Button
              type="text"
              icon={<FullscreenOutlined />}
              onClick={handleOpenFullChat}
              className="ai-qa-header-icon-btn"
              aria-label={t('ui.aiAssistant.openFullChat', { defaultValue: '打开全宽对话' })}
              title={t('ui.aiAssistant.openFullChat', { defaultValue: '打开全宽对话' })}
            />
          ) : null}
          {!embedded ? (
            <Button
              type="text"
              icon={<CloseOutlined />}
              onClick={onClose}
              className="ai-qa-header-icon-btn"
              aria-label={t('common.close')}
              title={t('common.close')}
            />
          ) : null}
        </div>
      </header>

      <div className="ai-qa-panel-main">
        {displayItems.length === 0 ? (
          <div className="ai-qa-welcome-screen">
            <div className="ai-qa-welcome-copy">
              <Lottie
                className="ai-qa-lottie-enhance ai-qa-welcome-hero"
                animationData={welcomeAnimation}
                loop
              />
              <div className="ai-qa-welcome-hi">{t('ui.aiAssistant.welcomeHi')}</div>
              <div className="ai-qa-welcome-title">{t('ui.aiAssistant.welcomeTitle')}</div>
              <div className="ai-qa-welcome-desc">{t('ui.aiAssistant.welcomeDesc')}</div>
              {welcomeHint}
            </div>
            {open && !senderDisabled ? (
              <div className="ai-qa-prompts-wrap">
                <Prompts
                  items={promptItems}
                  vertical
                  onItemClick={({ data }) => {
                    const label = typeof data.label === 'string' ? data.label : ''
                    if (label) handleSenderSubmit(label)
                  }}
                />
              </div>
            ) : null}
          </div>
        ) : (
          <div className="ai-qa-chat-scroll">
            <Bubble.List
              items={displayItems}
              autoScroll
              role={{
                ai: {
                  placement: 'start',
                  contentRender: renderAiBubbleContent,
                  styles: {
                    root: {
                      // 默认 columnGap≈paddingSM(12)；54px 头像耳机略出框，略增至 padding(16)
                      columnGap: token.padding,
                    },
                    content: {
                      background: token.colorFillTertiary,
                      color: token.colorText,
                    },
                  },
                  avatar: (
                    <KuAiLottieMark
                      size={54}
                      className="ai-qa-lottie-enhance ai-qa-bubble-avatar-mark"
                    />
                  ),
                  footer: (content: unknown, info: { status?: string; extraInfo?: { lastUserMessage?: string; toolTraces?: KuaiToolTrace[] } & ConfirmExtra }) => {
                    if (info?.status === 'loading') return null
                    const lastUser = info?.extraInfo?.lastUserMessage ?? ''
                    const text = typeof content === 'string' ? content : ''
                    const traces = info?.extraInfo?.toolTraces ?? []
                    const confirmToken = extractConfirmToken(text)
                    const interrupt = info?.extraInfo?.interrupt
                    const interruptMsgId = info?.extraInfo?.messageId
                    return (
                      <div className="ai-qa-bubble-footer-wrap">
                        {interrupt && interruptMsgId != null ? (
                          <ToolConfirmCard
                            model={{
                              interrupt,
                              status: info?.extraInfo?.confirmStatus ?? 'pending',
                              ...(info?.extraInfo?.confirmDeciding
                                ? { deciding: info.extraInfo.confirmDeciding }
                                : {}),
                              ...(info?.extraInfo?.confirmError
                                ? { error: info.extraInfo.confirmError }
                                : {}),
                            }}
                            busy={confirmBusy}
                            onDecide={
                              onConfirmDecision
                                ? (decision) => onConfirmDecision(interruptMsgId, decision)
                                : undefined
                            }
                            onExpire={
                              onConfirmExpire
                                ? () => onConfirmExpire(interruptMsgId)
                                : undefined
                            }
                          />
                        ) : null}
                        <ToolTraceList traces={traces} />
                      <div className="ai-qa-bubble-actions">
                        {confirmToken && onConfirmAction ? (
                          <Button
                            type="link"
                            size="small"
                            className="ai-qa-bubble-action"
                            onClick={() => onConfirmAction(confirmToken)}
                          >
                            {t('ui.aiAssistant.confirmAction')}
                          </Button>
                        ) : null}
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={() => handleCopy(text)}
                          onKeyDown={e => e.key === 'Enter' && handleCopy(text)}
                          className="ai-qa-bubble-action"
                        >
                          <CopyOutlined /> {t('ui.aiAssistant.copy')}
                        </span>
                        {lastUser ? (
                          <span
                            role="button"
                            tabIndex={0}
                            onClick={() => handleRegenerate(lastUser)}
                            onKeyDown={e => e.key === 'Enter' && handleRegenerate(lastUser)}
                            className="ai-qa-bubble-action"
                          >
                            <ReloadOutlined /> {t('ui.aiAssistant.regenerate')}
                          </span>
                        ) : null}
                      </div>
                      </div>
                    )
                  },
                },
                user: {
                  placement: 'end',
                  styles: {
                    content: {
                      background: token.colorPrimary,
                      color: '#fff',
                    },
                  },
                },
              }}
            />
          </div>
        )}
      </div>

      <div className="ai-qa-composer">
        {senderHint ? <p className="ai-qa-disclaimer">{senderHint}</p> : null}
        <div className="ai-qa-sender-wrap">
          <Sender {...senderProps} />
        </div>
        <p className="ai-qa-disclaimer">{t('ui.aiAssistant.disclaimer')}</p>
      </div>
    </div>
  )

  const panelContainer = (
    <div className="ai-qa-panel-container">
      <div className="ai-qa-panel-content">
        <div className="ai-qa-panel-body ai-assistant-modal-content">{qaContent}</div>
      </div>
    </div>
  )

  if (embedded) {
    return (
      <div
        className={`ai-qa-panel ai-qa-panel--embedded${embeddedSplit ? ' ai-qa-panel--embedded-split' : ''}`}
        role="region"
        aria-label={t('ui.aiAssistant.ariaLabel')}
      >
        {panelContainer}
      </div>
    )
  }

  return (
    <div
      className="ai-qa-panel"
      role="dialog"
      aria-label={t('ui.aiAssistant.ariaLabel')}
      aria-modal={false}
    >
      <div className="ai-qa-panel-glow">
        <BorderBeam color={borderBeamColor}>{panelContainer}</BorderBeam>
      </div>
    </div>
  )
}

type AIAssistantShellLayoutProps = {
  embedded?: boolean
  embeddedSplit?: boolean
  canOpenAssistantTab?: boolean
  onOpenAssistantTab?: () => void
  conversationId?: string
  initialMessages?: KuAiStoredMessage[]
  onPersistConversation?: (conversationId: string, messages: KuAiStoredMessage[]) => void
  onNewChatExternal?: () => void
}

type AIAssistantLivePanelProps = {
  open: boolean
  onClose?: () => void
  model: string
} & AIAssistantShellLayoutProps

const AIAssistantLivePanel: React.FC<AIAssistantLivePanelProps> = ({
  open,
  onClose,
  model,
  embedded,
  embeddedSplit,
  canOpenAssistantTab,
  onOpenAssistantTab,
  conversationId,
  initialMessages,
  onPersistConversation,
  onNewChatExternal,
}) => {
  const { t } = useTranslation()
  const currentUser = useCurrentUser()
  const userDisplayName = useMemo(() => resolveKuAiUserDisplayName(currentUser), [currentUser])
  const assistantDisplayName = t('ui.aiAssistant.title')
  const { context, contextBadge, pendingAssistant, setPendingAssistant } = useAiContext()
  // 发送走 canonical /core/ai/chat/completions，需 kuaiai:act:execute（与全宽对话页一致）
  const canSend = hasPermission(currentUser, 'kuaiai:act:execute')
  // spec 194 H1=a：写类档案判定（kuaiai:agent:read）与建会话（kuaiai:session:create）
  const canAgentRead = hasPermission(currentUser, 'kuaiai:agent:read')
  const canCreateSession = hasPermission(currentUser, 'kuaiai:session:create')
  const provider = useMemo(() => getKuaiChatProvider(model), [model])
  const [messageMeta, setMessageMeta] = useState<Map<string, KuAiMessageMeta>>(() => new Map())
  const messageMetaRef = useRef(messageMeta)
  messageMetaRef.current = messageMeta

  // spec 194：确认卡状态按 messageId 记（interrupt 对象复核：续跑中再挂起换上
  // 新 interrupt 对象即视为新待确认，同 token 也不例外——后端 token 可能复用）
  type ConfirmEntry = {
    interrupt: KuaiInterrupt
    status: ToolConfirmStatus
    deciding?: 'approve' | 'reject'
    error?: string
  }
  const [confirmStates, setConfirmStates] = useState<Record<string, ConfirmEntry>>({})
  // resume 手动拉流期间：阻止新发送、Sender 显示 loading（防连点重复提交）
  const [resuming, setResuming] = useState(false)
  const resumingRef = useRef(false)
  // H1=a：conversationKey+agentId → 已建 kuaiai session id（同对话内复用）
  const hitlSessionRef = useRef(new Map<string, number>())
  // conversationKey → 该抽屉会话最近一次发送实际携带的 kuaiai session id：
  // 挂起卡归属判定用（换档案换会话时旧会话挂起不被新消息收口，本地也不能标已取消）
  const hitlActiveSessionRef = useRef(new Map<string, number>())

  const conversationKey = conversationId
    ? `riveredge-kuaiai-${conversationId}`
    : 'riveredge-ai-assistant-qa'

  const defaultMessages = useMemo(
    () =>
      (initialMessages ?? []).map((m, index) => ({
        id: `stored-${conversationId ?? 'float'}-${index}`,
        message: { role: m.role, content: m.content },
        status: 'success' as const,
      })),
    [conversationId, initialMessages],
  )

  const chat = useXChat<XChatMessage, XChatMessage, Record<string, unknown>, Record<string, unknown>>({
    provider,
    conversationKey,
    defaultMessages,
    requestFallback: (_requestParams, { error }) => ({
      role: 'assistant',
      content: error?.message || t('ui.aiAssistant.requestFailed'),
    }),
  })

  const { setMessages: setChatMessages } = chat
  const hydratedMessagesFingerprintRef = useRef('')

  useEffect(() => {
    if (!conversationId) return
    return () => {
      chatMessagesStoreHelper.delete(conversationKey)
      hydratedMessagesFingerprintRef.current = ''
    }
  }, [conversationId, conversationKey])

  useEffect(() => {
    if (!conversationId) return
    const stored = initialMessages ?? []
    const fingerprint = kuAiConversationMessagesFingerprint(conversationId, stored)
    if (fingerprint === hydratedMessagesFingerprintRef.current) return
    setChatMessages(buildXChatMessagesFromKuAiStored(conversationId, stored))
    hydratedMessagesFingerprintRef.current = fingerprint
  }, [conversationId, initialMessages, setChatMessages])

  useEffect(() => {
    if (!conversationId) return
    setMessageMeta((prev) => {
      const next = new Map(prev)
      seedKuAiMessageMetaFromStored(next, conversationId, initialMessages ?? [])
      return next
    })
  }, [conversationId, initialMessages])

  useEffect(() => {
    if (!userDisplayName && !assistantDisplayName) return
    setMessageMeta((prev) => {
      const next = new Map(prev)
      let changed = false
      for (const item of chat.messages) {
        const role = (item.message as XChatMessage)?.role
        if (role !== 'user' && role !== 'assistant') continue
        if (role === 'assistant' && item.status !== 'success') continue
        const id = String(item.id)
        if (next.has(id)) continue
        if (id.startsWith('stored-')) continue
        const speaker_name = role === 'user' ? userDisplayName : assistantDisplayName
        if (!speaker_name) continue
        next.set(id, { speaker_name, spoken_at: nowSiteDateTimeString() })
        changed = true
      }
      return changed ? next : prev
    })
  }, [chat.messages, chat.isRequesting, userDisplayName, assistantDisplayName])

  const bubbleItems = useMemo(() => {
    return chat.messages.map((m, i) => {
      const msg = m.message as XChatMessage
      const role = msg?.role === 'user' ? ('user' as const) : ('ai' as const)
      const content =
        role === 'ai'
          ? stripAssistantThinkContent(typeof msg?.content === 'string' ? msg.content : '')
          : typeof msg?.content === 'string'
            ? msg.content
            : ''
      const prevMsg = chat.messages[i - 1]?.message as XChatMessage | undefined
      const lastUserMessage =
        role === 'ai' && prevMsg?.role === 'user'
          ? typeof prevMsg?.content === 'string'
            ? prevMsg.content
            : ''
          : ''
      // spec 194：确认卡状态按 interrupt 对象标识复核（续跑中再挂起换上新
      // interrupt 对象 → 视为新待确认；同 token 但 expiresAt/对象不同同样新挂起）
      const interrupt = role === 'ai' ? msg?.interrupt : undefined
      const stored = confirmStates[String(m.id)]
      const confirmEntry: ConfirmEntry | undefined =
        interrupt && stored && stored.interrupt === interrupt
          ? stored
          : interrupt
            ? { interrupt, status: 'pending' as const }
            : undefined
      return {
        key: m.id,
        role,
        content,
        status: m.status,
        extraInfo: {
          ...((m.extraInfo as object) || {}),
          lastUserMessage,
          ...(role === 'ai' && msg?.toolTraces?.length ? { toolTraces: msg.toolTraces } : {}),
          ...(interrupt && confirmEntry
            ? {
                messageId: m.id,
                interrupt,
                confirmStatus: confirmEntry.status,
                ...(confirmEntry.deciding ? { confirmDeciding: confirmEntry.deciding } : {}),
                ...(confirmEntry.error ? { confirmError: confirmEntry.error } : {}),
              }
            : {}),
        },
      }
    })
  }, [chat.messages, confirmStates])

  const displayItems = useMemo(() => {
    if (!chat.isRequesting) return bubbleItems
    return [
      ...bubbleItems,
      {
        key: 'ai-loading',
        role: 'ai' as const,
        content: '',
        status: 'loading' as const,
        loading: true,
      },
    ]
  }, [bubbleItems, chat.isRequesting])

  const handleNewChat = () => {
    if (onNewChatExternal) {
      onNewChatExternal()
      return
    }
    const c = chat as {
      clearMessages?: () => void
      setMessages?: (messages: []) => void
      onClear?: () => void
    }
    if (typeof c.clearMessages === 'function') c.clearMessages()
    else if (typeof c.setMessages === 'function') c.setMessages([])
    else if (typeof c.onClear === 'function') c.onClear()
  }

  /**
   * spec 194 H1=a：选用含写 Tool 的档案时先建 kuaiai 会话再发送；
   * 判定/建会话失败照常发送（后端确认闸会返回明确错误，不静默降级）。
   */
  const ensureWriteToolSession = async (
    ctx: AiContextPayload | null,
  ): Promise<number | null> => {
    if (!canAgentRead || !canCreateSession) return null
    const agentId = Number(ctx?.agentId)
    if (!agentId || !Number.isSafeInteger(agentId) || agentId <= 0) return null
    const cacheKey = `${conversationKey}:${agentId}`
    const cached = hitlSessionRef.current.get(cacheKey)
    if (cached) return cached
    try {
      if (!(await profileHasWriteTools(agentId))) return null
      const session = await createChatSession({ agent_id: agentId, model: null })
      hitlSessionRef.current.set(cacheKey, session.id)
      return session.id
    } catch {
      return null
    }
  }

  const sendToChat = async (prompt: string, ctx: AiContextPayload | null) => {
    const sessionId = await ensureWriteToolSession(ctx)
    // H2=a（F-M2）：仅当本次发送落进与挂起卡相同的 kuaiai 会话时才收口为已取消；
    // 换档案换会话/无会话发送后端不会写拒绝行，本地保持待确认
    const prevSessionId = hitlActiveSessionRef.current.get(conversationKey) ?? null
    if (sessionId != null) hitlActiveSessionRef.current.set(conversationKey, sessionId)
    if (sessionId != null && sessionId === prevSessionId) {
      cancelPendingConfirmations()
    }
    const base = toAiContextApiPayload(ctx)
    const apiContext = sessionId
      ? {
          ...(base ?? {}),
          extra: {
            ...((base?.extra as Record<string, unknown> | undefined) ?? {}),
            session_id: String(sessionId),
          },
        }
      : base
    chat.onRequest(
      {
        messages: [{ role: 'user', content: prompt }],
        ...(apiContext ? { context: apiContext } : {}),
      },
      { extraInfo: {} },
    )
  }

  /** spec 194 H2=a：挂起中的确认卡随新消息转「已取消」（后端同步补写拒绝行） */
  const cancelPendingConfirmations = () => {
    const list = chatMessagesStoreHelper.getMessages(conversationKey) ?? []
    setConfirmStates((prev) => {
      const next = { ...prev }
      for (const item of list) {
        const interrupt = (item.message as XChatMessage)?.interrupt
        if (!interrupt) continue
        const key = String(item.id)
        const stored = next[key]
        const effective =
          stored && stored.interrupt === interrupt ? stored.status : 'pending'
        if (effective === 'pending') {
          next[key] = { interrupt, status: 'cancelled' }
        }
      }
      return next
    })
  }

  const setConfirmEntry = (messageId: string | number, entry: ConfirmEntry) => {
    setConfirmStates((prev) => ({ ...prev, [String(messageId)]: entry }))
  }

  const handleConfirmExpire = (messageId: string | number) => {
    const list = chatMessagesStoreHelper.getMessages(conversationKey) ?? []
    const interrupt = (list.find((m) => String(m.id) === String(messageId))?.message as
      | XChatMessage
      | undefined)?.interrupt
    if (!interrupt) return
    setConfirmEntry(messageId, { interrupt, status: 'expired' })
  }

  /** spec 194：resume 手动拉流，续跑正文/工具轨迹写回同一条 assistant 消息 */
  const handleConfirmDecision = (messageId: string | number, decision: ChatResumeDecision) => {
    const list = chatMessagesStoreHelper.getMessages(conversationKey) ?? []
    const msg = (list.find((m) => String(m.id) === String(messageId))?.message as
      | XChatMessage
      | undefined)
    const interrupt = msg?.interrupt
    if (!interrupt || resumingRef.current || chat.isRequesting) return
    resumingRef.current = true
    setResuming(true)
    setConfirmEntry(messageId, {
      interrupt,
      status: 'deciding',
      deciding: decision,
    })
    const baseContent = typeof msg?.content === 'string' ? msg.content : ''
    const baseTraces = msg?.toolTraces ?? []
    resumeChat({
      threadToken: interrupt.threadToken,
      decision,
      // 后端校验决策数与 pending actions 数一致：一次点击对全部动作同决策
      actionCount: interrupt.actions.length,
      onDelta: (view) => {
        chat.setMessage(messageId, (info) => {
          const cur = info.message as XChatMessage
          return {
            ...info,
            status: 'updating',
            message: {
              ...cur,
              content: stripAssistantThinkContent(`${baseContent}${view.answer}`),
              toolTraces: [...baseTraces, ...view.reasoning.map(stepToToolTrace)],
              ...(view.pendingConfirmation
                ? { interrupt: view.pendingConfirmation }
                : {}),
            },
          }
        })
      },
    })
      .then((view) => {
        // 续跑流中 pendingConfirmation 出现即视为新挂起（同/异 token 一致处理，
        // interrupt 对象已在 onDelta 里换上新对象）→ 卡回到待确认
        const nextInterrupt = view.pendingConfirmation ?? null
        setConfirmEntry(
          messageId,
          nextInterrupt
            ? { interrupt: nextInterrupt, status: 'pending' }
            : {
                interrupt,
                status: decision === 'approve' ? 'approved' : 'rejected',
              },
        )
      })
      .catch((error: unknown) => {
        if (error instanceof ChatResumeGoneError) {
          setConfirmEntry(messageId, { interrupt, status: 'expired' })
        } else {
          // 网络/服务错误：保持待确认态 + 错误 + 重试（不改变终态）
          setConfirmEntry(messageId, {
            interrupt,
            status: 'pending',
            deciding: decision,
            error:
              error instanceof Error
                ? error.message
                : t('app.kuaiai.chat.confirm.submitFailed', { defaultValue: '确认提交失败' }),
          })
        }
      })
      .finally(() => {
        chat.setMessage(messageId, { status: 'success' })
        resumingRef.current = false
        setResuming(false)
      })
  }

  const handleSubmit = (question: string) => {
    const q = question?.trim?.() || ''
    // resumingRef 同步闸：state 有一帧窗口，连点可能穿透 resuming state
    if (!q || chat.isRequesting || resumingRef.current || !canSend) return
    // H2=a：同会话挂起卡的收口在 sendToChat 内按 sessionId 判定，不阻止发送
    void sendToChat(q, context)
  }

  const handleConfirmAction = useCallback(
    async (confirmToken: string) => {
      try {
        const result = await executeAiAction(confirmToken)
        message.success(String(result.message || t('ui.aiAssistant.actionExecuted')))
      } catch (error: unknown) {
        message.error(error instanceof Error ? error.message : t('common.operationFailed'))
      }
    },
    [t],
  )

  useEffect(() => {
    if (!open || !pendingAssistant?.prompt || chat.isRequesting || resuming) return
    const prompt = pendingAssistant.prompt.trim()
    const pendingContext = pendingAssistant.context ?? context
    setPendingAssistant(null)
    if (!prompt) return
    if (!canSend) {
      message.warning(
        t('app.kuaiai.chat.noSendPermission', {
          defaultValue: '当前账号无对话发送权限（kuaiai:act:execute）',
        }),
      )
      return
    }
    // H2=a：场景首问同样视为新消息；挂起卡收口在 sendToChat 内按 sessionId 判定
    void sendToChat(prompt, pendingContext)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pendingAssistant, chat.isRequesting, resuming, context, setPendingAssistant, chat, canSend, t])

  useEffect(() => {
    if (!conversationId || !onPersistConversation) return
    const metaById = new Map(messageMetaRef.current)
    const messages = buildKuAiStoredMessagesFromChat({
      chatMessages: chat.messages,
      metaById,
      userDisplayName,
      assistantDisplayName,
      stripAssistantContent: stripAssistantThinkContent,
    }).filter((msg) => msg.content.trim().length > 0 || msg.role === 'user')
    if (messages.length === 0) return
    onPersistConversation(conversationId, messages)
  }, [chat.messages, conversationId, onPersistConversation, userDisplayName, assistantDisplayName])

  return (
    <AIAssistantDialogUI
      open={open}
      onClose={onClose}
      displayItems={displayItems}
      isLoading={chat.isRequesting || resuming}
      onSubmit={handleSubmit}
      onNewChat={handleNewChat}
      senderDisabled={!canSend}
      senderHint={
        canSend
          ? null
          : t('app.kuaiai.chat.noSendPermission', {
              defaultValue: '当前账号无对话发送权限（kuaiai:act:execute）',
            })
      }
      modelName={model}
      contextBadge={contextBadge}
      onConfirmAction={(token) => void handleConfirmAction(token)}
      onConfirmDecision={handleConfirmDecision}
      onConfirmExpire={handleConfirmExpire}
      confirmBusy={resuming}
      embedded={embedded}
      embeddedSplit={embeddedSplit}
      canOpenAssistantTab={canOpenAssistantTab}
      onOpenAssistantTab={onOpenAssistantTab}
    />
  )
}

type FallbackReason = 'preview' | 'loading' | 'unconfigured' | 'status_error'

type AIAssistantFallbackPanelProps = {
  open: boolean
  onClose?: () => void
  reason: FallbackReason
  chatStatus?: ChatIntegrationStatus | null
  statusError?: string | null
} & AIAssistantShellLayoutProps

const AIAssistantFallbackPanel: React.FC<AIAssistantFallbackPanelProps> = ({
  open,
  onClose,
  reason,
  chatStatus,
  statusError,
  embedded,
  embeddedSplit,
  canOpenAssistantTab,
  onOpenAssistantTab,
}) => {
  const { t } = useTranslation()
  const [messages, setMessages] = useState<BubbleItem[]>([])
  const [loading, setLoading] = useState(false)

  const configHint = useMemo(() => {
    if (reason === 'loading') return null
    if (reason === 'status_error' && statusError) {
      return t('ui.aiAssistant.statusError', { message: statusError })
    }
    if (!chatStatus?.configured) {
      return t('ui.aiAssistant.notConfigured')
    }
    if (!chatStatus?.enabled) {
      return t('ui.aiAssistant.notEnabled')
    }
    return null
  }, [reason, chatStatus, statusError, t])

  const welcomeHint = useMemo(() => {
    if (reason === 'loading') {
      return (
        <div style={{ marginTop: 4, color: 'var(--ant-colorTextSecondary)' }}>
          <Spin size="small" style={{ marginRight: 8 }} />
          {t('ui.aiAssistant.connecting')}
        </div>
      )
    }
    if (configHint) {
      return <div style={{ marginTop: 4, color: 'var(--ant-colorWarning)' }}>{configHint}</div>
    }
    return null
  }, [reason, configHint, t])

  const handleNewChat = () => setMessages([])

  const handleSubmit = (question: string) => {
    const q = question?.trim?.() || ''
    if (!q || reason === 'loading') return

    if (configHint) {
      message.warning(configHint)
    }

    const userItem: BubbleItem = {
      key: `fallback-user-${Date.now()}`,
      role: 'user',
      content: q,
      status: 'success',
    }
    setMessages(prev => [...prev, userItem])
    setLoading(true)
    window.setTimeout(() => {
      const reply =
        reason === 'preview'
          ? t('ui.aiAssistant.previewReply')
          : configHint || t('ui.aiAssistant.notReadyReply')
      setMessages(prev => [
        ...prev,
        {
          key: `fallback-ai-${Date.now()}`,
          role: 'ai',
          content: reply,
          status: 'success',
          extraInfo: { lastUserMessage: q },
        },
      ])
      setLoading(false)
    }, 500)
  }

  const displayItems = useMemo(() => {
    if (!loading) return messages
    return [
      ...messages,
      {
        key: 'fallback-loading',
        role: 'ai' as const,
        content: '',
        status: 'loading' as const,
      },
    ]
  }, [messages, loading])

  return (
    <AIAssistantDialogUI
      open={open}
      onClose={onClose}
      displayItems={displayItems}
      isLoading={loading}
      onSubmit={handleSubmit}
      onNewChat={handleNewChat}
      senderDisabled={reason === 'loading'}
      welcomeHint={welcomeHint}
      modelName={chatStatus?.model}
      embedded={embedded}
      embeddedSplit={embeddedSplit}
      canOpenAssistantTab={canOpenAssistantTab}
      onOpenAssistantTab={onOpenAssistantTab}
    />
  )
}

type AIAssistantPanelProps = {
  open: boolean
  onClose?: () => void
  designOnly?: boolean
} & AIAssistantShellLayoutProps

const AIAssistantPanel: React.FC<AIAssistantPanelProps> = ({
  open,
  onClose,
  designOnly,
  embedded,
  embeddedSplit,
  canOpenAssistantTab,
  onOpenAssistantTab,
  conversationId,
  initialMessages,
  onPersistConversation,
  onNewChatExternal,
}) => {
  const { t } = useTranslation()
  const {
    data: chatStatus,
    isPending: statusPending,
    error: statusQueryError,
  } = useChatIntegrationStatus({ enabled: designOnly !== true })

  const layoutProps = {
    embedded,
    embeddedSplit,
    canOpenAssistantTab,
    onOpenAssistantTab,
    conversationId,
    initialMessages,
    onPersistConversation,
    onNewChatExternal,
  }

  if (designOnly === true) {
    return <AIAssistantFallbackPanel open={open} onClose={onClose} reason="preview" {...layoutProps} />
  }

  if (statusPending) {
    return <AIAssistantFallbackPanel open={open} onClose={onClose} reason="loading" {...layoutProps} />
  }

  const statusError =
    statusQueryError instanceof Error
      ? statusQueryError.message
      : statusQueryError
        ? t('ui.aiAssistant.requestError')
        : null

  if (statusError) {
    return (
      <AIAssistantFallbackPanel
        open={open}
        onClose={onClose}
        reason="status_error"
        statusError={statusError}
        {...layoutProps}
      />
    )
  }

  if (!chatStatus) {
    return <AIAssistantFallbackPanel open={open} onClose={onClose} reason="loading" {...layoutProps} />
  }

  if (chatStatus.configured && chatStatus.enabled) {
    return (
      <AIAssistantLivePanel open={open} onClose={onClose} model={chatStatus.model} {...layoutProps} />
    )
  }

  return (
    <AIAssistantFallbackPanel
      open={open}
      onClose={onClose}
      reason="unconfigured"
      chatStatus={chatStatus}
      {...layoutProps}
    />
  )
}

const AIAssistant: React.FC<AIAssistantProps> = ({ open = false, onClose, designOnly }) => {
  // 生命周期约定：Portal 常驻 + ai-qa-modal-hidden 隐藏；禁止 if (!open) return null，避免卸载触发全局样式误清理。
  const shellRef = useRef<HTMLDivElement | null>(null)
  const [styleContainer, setStyleContainer] = useState<HTMLElement | null>(null)
  const navigate = useNavigate()

  const handleClose = useCallback(() => {
    blurPanelFocus(shellRef.current)
    onClose?.()
  }, [onClose])

  const handleOpenAssistantTab = useCallback(() => {
    navigate(KUAIAI_ASSISTANT_TAB_PATH)
    handleClose()
  }, [navigate, handleClose])

  useEffect(() => {
    if (!open) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      e.stopPropagation()
      handleClose()
    }

    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [open, handleClose])

  useEffect(() => {
    if (open) return
    return scheduleScrollLockRelease()
  }, [open])

  return createPortal(
    <div
      ref={node => {
        shellRef.current = node
        if (node !== styleContainer) setStyleContainer(node)
      }}
      className={`ai-qa-modal-shell ai-qa-modal-bottom-right${open ? '' : ' ai-qa-modal-hidden'}`}
      aria-hidden={!open}
    >
      <StyleProvider cache={aiAssistantStyleCache} container={styleContainer ?? document.body}>
        <AIAssistantPanel
          open={open}
          onClose={handleClose}
          designOnly={designOnly}
          canOpenAssistantTab
          onOpenAssistantTab={handleOpenAssistantTab}
        />
      </StyleProvider>
    </div>,
    document.body,
  )
}

function pickDefaultActiveThreadId(sorted: KuAiConversationRecord[]): string {
  const withInquirer = sorted.find((item) => (item.inquirer_name?.trim()?.length ?? 0) > 0)
  return (withInquirer ?? sorted[0]).id
}

/** 列表/落库 API 须带租户；超管未选组织时不应误判为空并新建会话 */
function isKuAiConversationApiTenantReady(): boolean {
  if (isInfraSuperAdminFromToken()) {
    const tenantId = getTenantId()
    return tenantId != null && String(tenantId).trim() !== ''
  }
  return getTokenTenantId() != null || getTenantId() != null
}

const AIAssistantEmbeddedWithHistory: React.FC = () => {
  const { t } = useTranslation()
  const tokenPresent = !!getToken()
  const userQuery = useCurrentUserQuery({ enabled: tokenPresent })
  const currentUser = useCurrentUser()
  const userId = currentUser?.id != null ? Number(currentUser.id) : null
  const scopeKey = useMemo(() => resolveKuAiConversationScope(userId), [userId])
  const historyEligible =
    tokenPresent && userQuery.isFetched && userId != null && Number.isFinite(userId) && !!scopeKey
  const newTitle = t('ui.aiAssistant.newConversationTitle')

  const [threads, setThreads] = useState<KuAiConversationRecord[]>([])
  const [activeId, setActiveId] = useState<string>(() => createKuAiConversationId())
  const [activeMessages, setActiveMessages] = useState<KuAiStoredMessage[]>([])
  const [scopeReady, setScopeReady] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [activeDetailLoading, setActiveDetailLoading] = useState(false)
  const tenantScope = resolveSessionTenantScope()
  const activeLoadGenRef = useRef(0)
  const pendingPersistRef = useRef<KuAiConversationRecord | null>(null)
  const lastPersistFingerprintRef = useRef('')
  const listBootstrappedKeyRef = useRef<string | null>(null)
  const threadsRef = useRef(threads)
  threadsRef.current = threads
  const activeIdRef = useRef(activeId)
  activeIdRef.current = activeId

  const createEmptyThreadRemote = useCallback(async () => {
    const id = createKuAiConversationId()
    const record: KuAiConversationRecord = {
      id,
      title: newTitle,
      updatedAt: Date.now(),
      messages: [],
    }
    const created = await createKuAiConversationRemote(record)
    setThreads((prev) => [created, ...prev.filter((item) => item.id !== created.id)])
    setActiveId(created.id)
    setActiveMessages([])
    return created.id
  }, [newTitle])

  useEffect(() => {
    if (!tokenPresent) {
      setScopeReady(true)
      return
    }
    if (!userQuery.isFetched) {
      setScopeReady(false)
      return
    }
    if (userId == null || !Number.isFinite(userId) || !scopeKey) {
      setScopeReady(true)
      return
    }
    if (!isKuAiConversationApiTenantReady()) {
      setScopeReady(false)
      return
    }
    const bootstrapKey = `${scopeKey}:${tenantScope ?? 'none'}`
    if (listBootstrappedKeyRef.current === bootstrapKey) {
      setScopeReady(true)
      return
    }
    let cancelled = false
    setScopeReady(false)
    setLoadError(null)
    ;(async () => {
      try {
        let list = await fetchKuAiConversationList()
        if (list.length === 0) {
          const legacy = listKuAiConversationsFromLocal(scopeKey)
          if (legacy.length > 0) {
            list = await importKuAiConversationsRemote(legacy)
            clearKuAiConversationsLocal(scopeKey)
          }
        }
        if (cancelled) return
        if (list.length === 0) {
          await createEmptyThreadRemote()
          if (cancelled) return
        } else {
          setThreads(list)
          setActiveId((current) =>
            list.some((item) => item.id === current) ? current : pickDefaultActiveThreadId(list),
          )
        }
        listBootstrappedKeyRef.current = bootstrapKey
      } catch (err) {
        if (cancelled) return
        const msg = err instanceof Error ? err.message : String(err)
        setLoadError(msg)
      } finally {
        if (!cancelled) setScopeReady(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [
    tokenPresent,
    userQuery.isFetched,
    userId,
    scopeKey,
    tenantScope,
    createEmptyThreadRemote,
  ])

  useEffect(() => {
    if (!scopeKey || !scopeReady || loadError) return
    if (!activeId) return

    const cached = threadsRef.current.find((item) => item.id === activeId)
    const cachedMessages = cached?.messages ?? []
    const hasCachedMessages = cachedMessages.length > 0

    if (hasCachedMessages) {
      lastPersistFingerprintRef.current = kuAiConversationMessagesFingerprint(activeId, cachedMessages)
      setActiveMessages(cachedMessages)
      setActiveDetailLoading(false)
    } else {
      lastPersistFingerprintRef.current = ''
      setActiveMessages([])
      setActiveDetailLoading(true)
    }

    const generation = ++activeLoadGenRef.current
    ;(async () => {
      try {
        const detail = await fetchKuAiConversationDetail(activeId)
        if (generation !== activeLoadGenRef.current) return
        setActiveMessages(detail.messages)
        setThreads((prev) =>
          prev.map((item) =>
            item.id === detail.id
              ? mergeKuAiConversationDetailIntoRecord(item, detail)
              : item,
          ),
        )
        lastPersistFingerprintRef.current = kuAiConversationMessagesFingerprint(
          detail.id,
          detail.messages,
        )
      } catch (err) {
        if (generation !== activeLoadGenRef.current) return
        const msg = err instanceof Error ? err.message : String(err)
        message.error(t('ui.aiAssistant.historyLoadFailed', { message: msg }))
      } finally {
        if (generation === activeLoadGenRef.current) {
          setActiveDetailLoading(false)
        }
      }
    })()
  }, [activeId, scopeKey, scopeReady, loadError, t])

  const handleSelectThread = useCallback(
    (threadId: string) => {
      if (threadId === activeIdRef.current) return
      const cached = threadsRef.current.find((item) => item.id === threadId)
      const cachedMessages = cached?.messages ?? []
      if (cachedMessages.length > 0) {
        lastPersistFingerprintRef.current = kuAiConversationMessagesFingerprint(
          threadId,
          cachedMessages,
        )
        setActiveMessages(cachedMessages)
        setActiveDetailLoading(false)
      } else {
        lastPersistFingerprintRef.current = ''
        setActiveMessages([])
        setActiveDetailLoading(true)
      }
      setActiveId(threadId)
    },
    [],
  )

  const commitPersistRemote = useCallback(
    async (record: KuAiConversationRecord) => {
      pendingPersistRef.current = null
      const saved = await upsertKuAiConversationRemote(record)
      const savedLast = deriveKuAiLastMessageMeta(saved.messages)
      setThreads((prev) =>
        prev.map((item) =>
          item.id === saved.id
            ? {
                ...item,
                title: saved.title,
                updatedAt: saved.updatedAt,
                messages: saved.messages,
                ...savedLast,
                last_speaker_name: saved.last_speaker_name ?? savedLast.last_speaker_name,
                last_spoken_at: saved.last_spoken_at ?? savedLast.last_spoken_at,
                inquirer_name: saved.inquirer_name ?? deriveKuAiInquirerName(saved.messages),
              }
            : item,
        ),
      )
    },
    [],
  )

  useEffect(() => {
    const flushKeepalive = () => {
      const pending = pendingPersistRef.current
      if (pending) upsertKuAiConversationKeepalive(pending)
    }
    const onHide = () => {
      if (document.visibilityState === 'hidden') flushKeepalive()
    }
    window.addEventListener('pagehide', flushKeepalive)
    document.addEventListener('visibilitychange', onHide)
    return () => {
      window.removeEventListener('pagehide', flushKeepalive)
      document.removeEventListener('visibilitychange', onHide)
      const pending = pendingPersistRef.current
      if (pending) {
        void commitPersistRemote(pending).catch(() => {
          upsertKuAiConversationKeepalive(pending)
        })
      }
    }
  }, [commitPersistRemote])

  const handleCreateThread = useCallback(() => {
    if (!scopeKey) return
    void createEmptyThreadRemote().catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      message.error(t('ui.aiAssistant.historySaveFailed', { message: msg }))
    })
  }, [scopeKey, createEmptyThreadRemote, t])

  const handleDeleteThread = useCallback(
    (id: string) => {
      if (!scopeKey) return
      void (async () => {
        await deleteKuAiConversationRemote(id)
        if (pendingPersistRef.current?.id === id) pendingPersistRef.current = null
        const next = threads.filter((item) => item.id !== id)
        setThreads(next)
        if (activeId !== id) return
        if (next.length > 0) {
          setActiveId(next[0].id)
          return
        }
        await createEmptyThreadRemote()
      })().catch((err) => {
        const msg = err instanceof Error ? err.message : String(err)
        message.error(t('ui.aiAssistant.historySaveFailed', { message: msg }))
      })
    },
    [scopeKey, activeId, createEmptyThreadRemote, t, threads],
  )

  const handlePersist = useCallback(
    (conversationId: string, messages: KuAiStoredMessage[]) => {
      if (!scopeKey) return
      if (conversationId !== activeIdRef.current) return
      const fingerprint = kuAiConversationMessagesFingerprint(conversationId, messages)
      if (fingerprint === lastPersistFingerprintRef.current) return

      const title = deriveKuAiConversationTitle(messages, newTitle)
      const lastMeta = deriveKuAiLastMessageMeta(messages)
      const inquirerName = deriveKuAiInquirerName(messages)

      // 在 updater 外基于 threadsRef 判定变化：updater 可能延迟到渲染期执行，
      // 在其中写副作用标志会静默跳过远端持久化。
      const snapshot = threadsRef.current.find((item) => item.id === conversationId)
      const snapshotFingerprint = kuAiConversationMessagesFingerprint(
        conversationId,
        snapshot?.messages ?? [],
      )
      if (fingerprint === snapshotFingerprint) return
      const updatedAt = Date.now()

      setThreads((prev) => {
        const existing = prev.find((item) => item.id === conversationId)
        const moveToFront = shouldMoveKuAiThreadToFrontOnPersist(existing, messages)
        const mapped = prev.map((item) =>
          item.id === conversationId
            ? { ...item, title, updatedAt, messages, ...lastMeta, inquirer_name: inquirerName }
            : item,
        )
        return moveToFront ? moveKuAiConversationToFront(mapped, conversationId) : mapped
      })

      setActiveMessages(messages)
      const record: KuAiConversationRecord = {
        id: conversationId,
        title,
        updatedAt,
        messages,
        ...lastMeta,
        inquirer_name: inquirerName,
      }
      lastPersistFingerprintRef.current = fingerprint
      pendingPersistRef.current = record
      void commitPersistRemote(record).catch((err) => {
        lastPersistFingerprintRef.current = ''
        const msg = err instanceof Error ? err.message : String(err)
        message.error(t('ui.aiAssistant.historySaveFailed', { message: msg }))
      })
    },
    [scopeKey, newTitle, t, commitPersistRemote],
  )

  if (!scopeReady) {
    return (
      <div className="ai-qa-embedded-page ai-qa-embedded-page--loading">
        <Spin />
      </div>
    )
  }

  if (!historyEligible) {
    return (
      <div className="ai-qa-embedded-page ai-qa-embedded-page--empty">
        <Empty description={t('ui.aiAssistant.historyRequiresLogin')} />
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="ai-qa-embedded-page ai-qa-embedded-page--empty">
        <Result
          status="error"
          title={t('ui.aiAssistant.historyLoadFailedTitle')}
          subTitle={loadError}
          extra={
            <Button
              type="primary"
              onClick={() => {
                setLoadError(null)
                listBootstrappedKeyRef.current = null
                setScopeReady(false)
                void (async () => {
                  try {
                    let list = await fetchKuAiConversationList()
                    if (list.length === 0) {
                      await createEmptyThreadRemote()
                    } else {
                      setThreads(list)
                      setActiveId((current) =>
                        list.some((item) => item.id === current)
                          ? current
                          : pickDefaultActiveThreadId(list),
                      )
                    }
                    listBootstrappedKeyRef.current = `${scopeKey}:${tenantScope ?? 'none'}`
                  } catch (err) {
                    const msg = err instanceof Error ? err.message : String(err)
                    setLoadError(msg)
                  } finally {
                    setScopeReady(true)
                  }
                })()
              }}
            >
              {t('common.retry')}
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div className="ai-qa-embedded-layout">
      <aside className="ai-qa-history-sidebar" aria-label={t('ui.aiAssistant.historySidebar')}>
        <Button type="primary" icon={<PlusOutlined />} block className="ai-qa-history-new-btn" onClick={handleCreateThread}>
          {t('ui.aiAssistant.newChat')}
        </Button>
        <div className="ai-qa-history-section-label">{t('ui.aiAssistant.historyRecent')}</div>
        <div className="ai-qa-history-list">
          {threads.length === 0 ? (
            <div className="ai-qa-history-empty">{t('ui.aiAssistant.historyEmpty')}</div>
          ) : (
            threads.map((thread) => {
              const active = thread.id === activeId
              return (
                <div
                  key={thread.id}
                  className={`ai-qa-history-card${active ? ' ai-qa-history-card--active' : ''}`}
                >
                  <button
                    type="button"
                    className="ai-qa-history-card-body"
                    onClick={() => handleSelectThread(thread.id)}
                    title={thread.title}
                  >
                    <span className="ai-qa-history-card-title">{thread.title}</span>
                  </button>
                  <div className="ai-qa-history-card-delete-slot">
                    <Popconfirm
                      title={t('ui.aiAssistant.deleteConversationConfirm')}
                      onConfirm={() => handleDeleteThread(thread.id)}
                      okText={t('common.confirm')}
                      cancelText={t('common.cancel')}
                    >
                      <Button
                        type="text"
                        size="small"
                        className="ai-qa-history-card-delete"
                        icon={<DeleteOutlined />}
                        aria-label={t('common.delete')}
                      />
                    </Popconfirm>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </aside>
      <div className="ai-qa-embedded-chat-main">
        {activeDetailLoading ? (
          <div className="ai-qa-embedded-page ai-qa-embedded-page--loading">
            <Spin />
          </div>
        ) : (
          <AIAssistantPanel
            key={activeId}
            open
            embedded
            embeddedSplit
            conversationId={activeId}
            initialMessages={activeMessages}
            onPersistConversation={handlePersist}
            onNewChatExternal={handleCreateThread}
          />
        )}
      </div>
    </div>
  )
}

/** UniTabs 独立标签页内嵌对话（/apps/kuaiai/chat） */
export function AIAssistantEmbedded() {
  const shellRef = useRef<HTMLDivElement | null>(null)
  const [styleContainer, setStyleContainer] = useState<HTMLElement | null>(null)

  return (
    <div
      ref={node => {
        shellRef.current = node
        if (node !== styleContainer) setStyleContainer(node)
      }}
      className="ai-qa-modal-shell ai-qa-embedded-page-shell"
    >
      <StyleProvider cache={aiAssistantStyleCache} container={styleContainer ?? document.body}>
        <AIAssistantEmbeddedWithHistory />
      </StyleProvider>
    </div>
  )
}

export default AIAssistant
