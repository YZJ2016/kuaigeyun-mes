/**
 * 星数采语义标签。状态文案与后端枚举一致，未知值原样展示不给假语义。
 */

import React from 'react';
import { Tag } from 'antd';

const SEVERITY: Record<string, { color: string; label: string }> = {
  info: { color: 'blue', label: '提示' },
  warning: { color: 'orange', label: '警告' },
  critical: { color: 'red', label: '严重' },
};

const ALERT_STATUS: Record<string, { color: string; label: string }> = {
  open: { color: 'red', label: '未确认' },
  acknowledged: { color: 'orange', label: '已确认' },
  recovered: { color: 'green', label: '已恢复' },
  closed: { color: 'default', label: '已处置' },
};

const HEALTH_STATUS: Record<string, { color: string; label: string }> = {
  receiving: { color: 'green', label: '接收中' },
  authenticated: { color: 'cyan', label: '已认证' },
  idle: { color: 'blue', label: '空闲' },
  disconnected: { color: 'red', label: '已断开' },
  unavailable: { color: 'orange', label: '不可用' },
  disabled: { color: 'default', label: '已停用' },
  unknown: { color: 'default', label: '未知' },
};

const AGENT_STATUS: Record<string, { color: string; label: string }> = {
  online: { color: 'green', label: '在线' },
  offline: { color: 'default', label: '离线' },
  error: { color: 'red', label: '异常' },
  unknown: { color: 'default', label: '未知' },
};

const RULE_TYPE: Record<string, { color: string; label: string }> = {
  threshold: { color: 'geekblue', label: '阈值' },
  offline: { color: 'purple', label: '离线' },
};

const VALUE_TYPE: Record<string, string> = {
  number: '数值',
  boolean: '布尔',
  text: '文本',
};

function renderStatus(map: Record<string, { color: string; label: string }>, value?: string | null) {
  const key = (value ?? '').trim() || 'unknown';
  const meta = map[key];
  if (meta) {
    return <Tag color={meta.color}>{meta.label}</Tag>;
  }
  return <Tag>{key}</Tag>;
}

/** 告警严重级别：info / warning / critical。 */
export function SeverityTag({ value }: { value?: string | null }) {
  return renderStatus(SEVERITY, value);
}

/** 告警记录状态：open / acknowledged / recovered / closed。 */
export function AlertStatusTag({ value }: { value?: string | null }) {
  return renderStatus(ALERT_STATUS, value);
}

/** 数采连接健康状态。 */
export function HealthStatusTag({ value }: { value?: string | null }) {
  return renderStatus(HEALTH_STATUS, value);
}

/** 边缘 Agent 心跳状态。 */
export function AgentStatusTag({ value }: { value?: string | null }) {
  return renderStatus(AGENT_STATUS, value);
}

/** 告警规则类型：threshold / offline。 */
export function RuleTypeTag({ value }: { value?: string | null }) {
  const key = (value ?? '').trim() || 'threshold';
  const meta = RULE_TYPE[key];
  return meta ? <Tag color={meta.color}>{meta.label}</Tag> : <Tag>{key}</Tag>;
}

/** IoT 设备在线状态。 */
export function OnlineTag({ online }: { online?: boolean | null }) {
  return online ? <Tag color="green">在线</Tag> : <Tag>离线</Tag>;
}

/** 点位值类型。 */
export function ValueTypeTag({ value }: { value?: string | null }) {
  const key = (value ?? '').trim();
  const label = VALUE_TYPE[key];
  return label ? <Tag>{label}</Tag> : <Tag>{key || '—'}</Tag>;
}
