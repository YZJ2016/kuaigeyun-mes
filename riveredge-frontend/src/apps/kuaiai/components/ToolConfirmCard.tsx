/**
 * KU-AI 人工确认闸确认卡（spec 194）。
 *
 * 全宽 `/chat`（MessageList）与右侧 KU-Ask 抽屉共用：
 * - 展示中断帧下发的动作中文 label、参数摘要、业务对象与过期倒计时；
 * - 仅「确认 / 拒绝」两个动作（H4=a，无参数编辑）；
 * - 终态：已确认 / 已拒绝 / 已取消（未确认，H2=a 新消息自动拒绝）/
 *   已过期或已处理（倒计时归零或 resume 404）；提交失败保留待确认态并给重试。
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Space, Tag, theme, Typography } from 'antd';
import { SafetyCertificateOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { KuaiInterrupt } from '../../../services/deepseekChat';

export type ToolConfirmStatus =
  | 'pending'
  | 'deciding'
  | 'approved'
  | 'rejected'
  | 'cancelled'
  | 'expired';

export interface ToolConfirmCardModel {
  interrupt: KuaiInterrupt;
  status: ToolConfirmStatus;
  /** deciding 时为本次决策；pending+error 时为上次失败的决策（重试回放任一） */
  deciding?: 'approve' | 'reject';
  /** resume 提交失败（非 404）的错误文案；卡片保持待确认态 */
  error?: string;
  /** 归属会话（全宽页切换会话过滤用；抽屉可省略） */
  sessionId?: number | null;
}

interface ToolConfirmCardProps {
  model: ToolConfirmCardModel;
  /** 父级提交中（resume 在飞）：按钮禁用，防连点重复提交 */
  busy?: boolean;
  onDecide?: (decision: 'approve' | 'reject') => void;
  /** 客户端倒计时归零（后端懒过期），父级把卡片置为 expired */
  onExpire?: () => void;
}

function formatRemaining(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

const ToolConfirmCard: React.FC<ToolConfirmCardProps> = ({
  model,
  busy = false,
  onDecide,
  onExpire,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { interrupt, status, deciding, error } = model;
  // 非法 expiresAt（脏帧/截断帧）不当作有期限：dayjs(...).isValid() 为 false 时置空
  const parsedExpiresAt = interrupt.expiresAt ? dayjs(interrupt.expiresAt) : null;
  const expiresAt = parsedExpiresAt?.isValid() ? parsedExpiresAt : null;
  const [now, setNow] = useState(() => Date.now());
  const expiredNotifiedRef = useRef(false);

  // 续跑后同一卡换上新 interrupt（再次挂起，新/同 token 都算新挂起）：
  // 过期通知标记按 interrupt 对象标识复位
  useEffect(() => {
    expiredNotifiedRef.current = false;
  }, [interrupt]);

  const actionable = status === 'pending';
  const remainingMs = expiresAt ? expiresAt.valueOf() - now : null;
  const countdownDone = remainingMs != null && remainingMs <= 0;

  useEffect(() => {
    if (!expiresAt || !actionable) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [expiresAt, actionable]);

  // 客户端倒计时归零：后端为懒过期，先本地置终态（点按钮兜底 resume 404 同态）
  useEffect(() => {
    if (!countdownDone || expiredNotifiedRef.current) return;
    expiredNotifiedRef.current = true;
    onExpire?.();
  }, [countdownDone, onExpire]);

  const statusTag = useMemo(() => {
    switch (status) {
      case 'deciding':
        return (
          <Tag color="processing">
            {deciding === 'reject'
              ? t('app.kuaiai.chat.confirm.statusRejecting', { defaultValue: '正在拒绝…' })
              : t('app.kuaiai.chat.confirm.statusApproving', {
                  defaultValue: '已确认，执行中',
                })}
          </Tag>
        );
      case 'approved':
        return (
          <Tag color="success">
            {t('app.kuaiai.chat.confirm.statusApproved', { defaultValue: '已确认' })}
          </Tag>
        );
      case 'rejected':
        return (
          <Tag>
            {t('app.kuaiai.chat.confirm.statusRejected', { defaultValue: '已拒绝' })}
          </Tag>
        );
      case 'cancelled':
        return (
          <Tag>
            {t('app.kuaiai.chat.confirm.statusCancelled', {
              defaultValue: '已取消（未确认）',
            })}
          </Tag>
        );
      case 'expired':
        return (
          <Tag color="warning">
            {t('app.kuaiai.chat.confirm.statusExpired', {
              defaultValue: '已过期或已处理',
            })}
          </Tag>
        );
      default:
        return null;
    }
  }, [status, deciding, t]);

  const retryDecision = deciding === 'reject' ? 'reject' : 'approve';
  const otherDecision = retryDecision === 'approve' ? 'reject' : 'approve';

  return (
    <div
      style={{
        border: `1px solid ${token.colorWarningBorder}`,
        background: token.colorWarningBg,
        borderRadius: token.borderRadiusLG,
        padding: '10px 12px',
        maxWidth: 520,
        fontSize: 13,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <SafetyCertificateOutlined style={{ color: token.colorWarning }} />
        <Typography.Text strong>
          {t('app.kuaiai.chat.confirm.title', { defaultValue: '待确认操作' })}
        </Typography.Text>
        {statusTag}
        {actionable && remainingMs != null && !countdownDone ? (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('app.kuaiai.chat.confirm.expiresIn', {
              defaultValue: '剩余 {{time}}',
              time: formatRemaining(remainingMs),
            })}
          </Typography.Text>
        ) : null}
      </div>

      <ul style={{ margin: '8px 0 0', padding: 0, listStyle: 'none' }}>
        {interrupt.actions.map((action, index) => (
          <li key={`${action.tool}-${index}`} style={{ marginBottom: 6 }}>
            <div style={{ fontWeight: 500 }}>{action.label}</div>
            {action.argsSummary ? (
              <div style={{ color: token.colorTextSecondary, wordBreak: 'break-all' }}>
                {t('app.kuaiai.chat.confirm.argsLabel', { defaultValue: '参数' })}
                ：{action.argsSummary}
              </div>
            ) : null}
            {action.businessObject ? (
              <div style={{ color: token.colorTextSecondary }}>
                {t('app.kuaiai.chat.confirm.businessObject', {
                  defaultValue: '业务对象',
                })}
                ：{action.businessObject}
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      {actionable ? (
        <Typography.Text
          type="secondary"
          style={{ display: 'block', marginTop: 4, fontSize: 12 }}
        >
          {t('app.kuaiai.chat.confirm.waitHint', {
            defaultValue: '确认前不会执行写操作',
          })}
        </Typography.Text>
      ) : null}

      {error ? (
        <Typography.Text
          type="danger"
          style={{ display: 'block', marginTop: 6, fontSize: 12 }}
        >
          {error}
        </Typography.Text>
      ) : null}

      {actionable && onDecide ? (
        <Space style={{ marginTop: 8 }} size={8}>
          {error ? (
            <>
              <Button
                type="primary"
                size="small"
                disabled={busy}
                onClick={() => onDecide(retryDecision)}
              >
                {t('app.kuaiai.chat.confirm.retry', { defaultValue: '重试' })}
              </Button>
              <Button
                size="small"
                danger={otherDecision === 'reject'}
                disabled={busy}
                onClick={() => onDecide(otherDecision)}
              >
                {otherDecision === 'approve'
                  ? t('app.kuaiai.chat.confirm.approve', { defaultValue: '确认' })
                  : t('app.kuaiai.chat.confirm.reject', { defaultValue: '拒绝' })}
              </Button>
            </>
          ) : (
            <>
              <Button
                type="primary"
                size="small"
                disabled={busy || countdownDone}
                onClick={() => onDecide('approve')}
              >
                {t('app.kuaiai.chat.confirm.approve', { defaultValue: '确认' })}
              </Button>
              <Button
                size="small"
                danger
                disabled={busy || countdownDone}
                onClick={() => onDecide('reject')}
              >
                {t('app.kuaiai.chat.confirm.reject', { defaultValue: '拒绝' })}
              </Button>
            </>
          )}
        </Space>
      ) : null}
    </div>
  );
};

export default ToolConfirmCard;
