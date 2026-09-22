/**
 * IM 第三栏内嵌 KU-AI 对话（不打开独立助手面板）
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Avatar, Button, Input } from 'antd';
import { useXChat, XRequest } from '@ant-design/x-sdk';
import { useTranslation } from 'react-i18next';
import { KuAiLottieMark } from '../ai-assistant/KuAiLottieMark';
import AiAssistantMarkdown from '../ai-assistant/AiAssistantMarkdown';
import { useAiContext, toAiContextApiPayload } from '../../contexts/AiContext';
import { useChatIntegrationStatus } from '../../hooks/useChatIntegrationStatus';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useUserAvatarUrl } from '../../hooks/useUserAvatarUrl';
import {
  buildKuaiChatAuthHeaders,
  KuaiDeepSeekChatProvider,
  KUAI_CHAT_COMPLETIONS_URL,
  parseKuaiChatErrorResponse,
  stripAssistantThinkContent,
} from '../../services/deepseekChat';
import {
  getAvatarFontSize,
  getAvatarText,
  getImageAvatarCircleStyle,
} from '../../utils/avatar';
import styles from './uni-im.module.css';

type XChatMessage = {
  role: string;
  content: string;
};

type UniImKuAiChatProps = {
  active: boolean;
};

const kuaiImProviderCache = new Map<
  string,
  KuaiDeepSeekChatProvider<XChatMessage, Record<string, unknown>, Record<string, unknown>>
>();

function getKuaiImChatProvider(model: string) {
  let provider = kuaiImProviderCache.get(model);
  if (!provider) {
    provider = new KuaiDeepSeekChatProvider<XChatMessage, Record<string, unknown>, Record<string, unknown>>({
      request: XRequest(KUAI_CHAT_COMPLETIONS_URL, {
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
            };
            return [url, { ...options, headers }];
          },
          onResponse: async (response: Response) => {
            if (!response.ok) {
              throw new Error(await parseKuaiChatErrorResponse(response));
            }
            return response;
          },
        },
      }),
    });
    kuaiImProviderCache.set(model, provider);
  }
  return provider;
}

export default function UniImKuAiChat({ active }: UniImKuAiChatProps) {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  const { context } = useAiContext();
  const { avatarUrl, setImageFailed, showTextAvatar } = useUserAvatarUrl(currentUser);
  const [draft, setDraft] = useState('');
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const { data: chatStatus, isLoading: statusLoading, isError: statusError } = useChatIntegrationStatus({
    enabled: active,
  });

  const model = chatStatus?.model?.trim() || 'deepseek-chat';
  const chatReady = !!chatStatus?.configured && !!chatStatus?.enabled;
  const provider = useMemo(() => getKuaiImChatProvider(model), [model]);

  const chat = useXChat<XChatMessage, XChatMessage, Record<string, unknown>, Record<string, unknown>>({
    provider,
    conversationKey: 'riveredge-uni-im-kuai',
    defaultMessages: [],
    requestFallback: (_requestParams, { error }) => ({
      role: 'assistant',
      content: error?.message || t('ui.aiAssistant.requestFailed'),
    }),
  });

  const messageRows = useMemo(() => {
    return chat.messages.map((m) => {
      const msg = m.message as XChatMessage;
      const isSelf = msg?.role === 'user';
      const raw = typeof msg?.content === 'string' ? msg.content : '';
      const content = isSelf ? raw : stripAssistantThinkContent(raw);
      return {
        key: String(m.id),
        isSelf,
        content,
        status: m.status,
      };
    });
  }, [chat.messages]);

  useEffect(() => {
    if (!active) {
      return;
    }
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [active, messageRows.length, chat.isRequesting]);

  const onSend = useCallback(() => {
    const q = draft.trim();
    if (!q || chat.isRequesting || !chatReady) {
      return;
    }
    setDraft('');
    const apiContext = toAiContextApiPayload(context);
    chat.onRequest(
      {
        messages: [{ role: 'user', content: q }],
        ...(apiContext ? { context: apiContext } : {}),
      },
      { extraInfo: {} },
    );
  }, [chat, chatReady, context, draft]);

  const statusHint = useMemo(() => {
    if (statusLoading) {
      return t('common.loading');
    }
    if (statusError) {
      return t('ui.aiAssistant.statusError', { message: t('common.loadFailed') });
    }
    if (!chatStatus?.configured) {
      return t('ui.aiAssistant.notConfigured');
    }
    if (!chatStatus?.enabled) {
      return t('ui.aiAssistant.notEnabled');
    }
    return null;
  }, [chatStatus?.configured, chatStatus?.enabled, statusError, statusLoading, t]);

  const messageAvatarSize = 36;

  return (
    <>
      <div className={styles.messageList}>
        {statusHint && messageRows.length === 0 ? (
          <div className={styles.emptyChat}>{statusHint}</div>
        ) : messageRows.length === 0 ? (
          <div className={styles.emptyChat}>{t('components.uniIm.kuAiEmptyChat')}</div>
        ) : (
          messageRows.map((row) => (
            <div
              key={row.key}
              className={`${styles.messageRow} ${row.isSelf ? styles.messageRowSelf : ''}`}
            >
              {row.isSelf ? (
                <Avatar
                  size={messageAvatarSize}
                  src={showTextAvatar ? undefined : avatarUrl}
                  onError={() => setImageFailed(true)}
                  className={`${styles.imAvatar} ${styles.msgAvatarSelf}`}
                  style={{
                    ...(showTextAvatar
                      ? {
                          backgroundColor: '#576b95',
                          color: '#ffffff',
                          border: 'none',
                          boxShadow: 'none',
                        }
                      : getImageAvatarCircleStyle()),
                    fontSize: getAvatarFontSize(messageAvatarSize),
                    fontWeight: 500,
                  }}
                >
                  {showTextAvatar
                    ? getAvatarText(currentUser?.full_name, currentUser?.username)
                    : null}
                </Avatar>
              ) : (
                <span className={`${styles.imAvatar} ${styles.kuAiMsgAvatar}`} aria-hidden>
                  <KuAiLottieMark size={40} />
                </span>
              )}
              <div className={styles.bubbleWrap}>
                <div className={`${styles.bubble} ${row.isSelf ? styles.bubbleSelf : styles.bubbleKuAi}`}>
                  {row.isSelf ? (
                    row.content
                  ) : row.status === 'loading' && !row.content ? (
                    t('common.loading')
                  ) : (
                    <AiAssistantMarkdown content={row.content} />
                  )}
                </div>
              </div>
            </div>
          ))
        )}
        {chat.isRequesting ? (
          <div className={styles.messageRow}>
            <span className={`${styles.imAvatar} ${styles.kuAiMsgAvatar}`} aria-hidden>
              <KuAiLottieMark size={40} />
            </span>
            <div className={styles.bubbleWrap}>
              <div className={`${styles.bubble} ${styles.bubbleKuAi}`}>{t('common.loading')}</div>
            </div>
          </div>
        ) : null}
        <div ref={messagesEndRef} />
      </div>
      <div className={styles.composer}>
        <div className={styles.composerBox}>
          <Input.TextArea
            className={styles.composerInput}
            variant="borderless"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={
              chatReady
                ? t('ui.aiAssistant.senderPlaceholder')
                : t('components.uniIm.kuAiUnavailablePlaceholder')
            }
            disabled={!chatReady || chat.isRequesting}
            autoSize={{ minRows: 3, maxRows: 6 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
          />
          <div className={styles.composerFooter}>
            <Button
              type="primary"
              className={styles.sendBtn}
              onClick={onSend}
              loading={chat.isRequesting}
              disabled={!chatReady || !draft.trim()}
            >
              {t('pages.personal.im.send')}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
