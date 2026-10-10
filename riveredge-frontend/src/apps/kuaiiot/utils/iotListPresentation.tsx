/**
 * 快数采列表展示：在线/健康/类型/严重度/启用 → MarkerTag；告警记录态 → StatusTag。
 * 配置主数据风格：业务列不堆叠（编码与名称分列）；名称唯一 RemainderFlex。
 */
import type { TFunction } from 'i18next';
import { MarkerTag, StatusTag } from '../../../constants/statusBadges';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../utils/uniTableLayoutColumns';
import {
  translateConnectionType,
  translateHealthStatus,
  translateMapTarget,
  translateProtocol,
  translateSeverity,
  translateValueType,
} from '../constants/formOptions';

/** 列表列宽契约：短码/徽章 KeepWidth；名称 RemainderFlex；禁止全表 KeepWidth。 */
export const IOT_LIST_COL = {
  code: { width: 140, minWidth: 140, uniTableKeepWidth: true, resizable: false, ellipsis: true },
  /** 唯一余量列（名称长短不一） */
  name: {
    minWidth: 140,
    uniTableRemainderFlex: true,
    uniTablePrimaryFlex: true,
    resizable: false,
    ellipsis: true,
  },
  /** 描述等次要文本（页上已有 name 余量列时用） */
  text: { width: 160, minWidth: 160, uniTableKeepWidth: true, resizable: false, ellipsis: true },
  /** 告警消息等（页上无 name 时作唯一 RemainderFlex） */
  message: {
    minWidth: 160,
    uniTableRemainderFlex: true,
    uniTablePrimaryFlex: true,
    resizable: false,
    ellipsis: true,
  },
  ref: { width: 160, minWidth: 160, uniTableKeepWidth: true, resizable: false, ellipsis: true },
  tagKey: { width: 140, minWidth: 140, uniTableKeepWidth: true, resizable: false, ellipsis: true },
  externalId: { width: 140, minWidth: 140, uniTableKeepWidth: true, resizable: false, ellipsis: true },
  mapTarget: { width: 120, minWidth: 120, uniTableKeepWidth: true, resizable: false, ellipsis: true },
  fillTarget: { width: 140, minWidth: 140, uniTableKeepWidth: true, resizable: false, ellipsis: true },
  marker: { ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS },
  /** 略长徽章文案（协议/规则类型等） */
  markerMd: { width: 100, minWidth: 100, uniTableKeepWidth: true, resizable: false },
  unit: { width: 72, minWidth: 72, uniTableKeepWidth: true, resizable: false, ellipsis: true },
  count: { width: 100, minWidth: 100, uniTableKeepWidth: true, resizable: false },
  datetime: {
    width: 176,
    minWidth: 176,
    uniTableKeepWidth: true,
    resizable: false,
    uniTableAuditStackedColumn: false,
  },
} as const;

const HEALTH_MARKER_COLOR: Record<string, string> = {
  healthy: 'success',
  unhealthy: 'error',
  unknown: 'default',
};

const SEVERITY_MARKER_COLOR: Record<string, string> = {
  info: 'default',
  warning: 'warning',
  critical: 'error',
};

export function renderIotEnabledMarker(t: TFunction, enabled?: boolean | null) {
  return (
    <MarkerTag color={enabled ? 'success' : 'default'}>
      {enabled ? t('common.yes') : t('common.no')}
    </MarkerTag>
  );
}

export function renderIotOnlineMarker(t: TFunction, online?: boolean | null) {
  return (
    <MarkerTag color={online ? 'success' : 'default'}>
      {online ? t('app.kuaiiot.status.online') : t('app.kuaiiot.status.offline')}
    </MarkerTag>
  );
}

export function renderIotTypeMarker(label: string, color: string = 'processing') {
  const text = String(label ?? '').trim();
  if (!text || text === '-') return '-';
  return <MarkerTag color={color}>{text}</MarkerTag>;
}

export function renderIotConnectionTypeMarker(t: TFunction, value?: string | null) {
  return renderIotTypeMarker(translateConnectionType(t, value));
}

export function renderIotProtocolMarker(t: TFunction, value?: string | null) {
  return renderIotTypeMarker(translateProtocol(t, value));
}

export function renderIotValueTypeMarker(t: TFunction, value?: string | null) {
  return renderIotTypeMarker(translateValueType(t, value));
}

export function renderIotMapTargetMarker(t: TFunction, value?: string | null, displayName?: string | null) {
  return renderIotTypeMarker(translateMapTarget(t, value, displayName));
}

export function renderIotHealthMarker(t: TFunction, value?: string | null) {
  const text = translateHealthStatus(t, value);
  if (text === '-') return '-';
  const key = String(value ?? '').toLowerCase();
  return <MarkerTag color={HEALTH_MARKER_COLOR[key] ?? 'default'}>{text}</MarkerTag>;
}

export function renderIotSeverityMarker(t: TFunction, value?: string | null) {
  const text = translateSeverity(t, value);
  if (text === '-') return '-';
  const key = String(value ?? '').toLowerCase();
  return <MarkerTag color={SEVERITY_MARKER_COLOR[key] ?? 'default'}>{text}</MarkerTag>;
}

export function renderIotAgentStatusMarker(t: TFunction, status?: string | null) {
  const key = String(status ?? '').toLowerCase();
  const label =
    key === 'online'
      ? t('app.kuaiiot.status.online')
      : key === 'offline'
        ? t('app.kuaiiot.status.offline')
        : t('app.kuaiiot.status.unknown');
  const color = key === 'online' ? 'success' : key === 'offline' ? 'default' : 'warning';
  return <MarkerTag color={color}>{label}</MarkerTag>;
}

export function renderIotRuleTypeMarker(t: TFunction, ruleType?: string | null) {
  const text =
    ruleType === 'offline' ? t('app.kuaiiot.ruleType.offline') : t('app.kuaiiot.ruleType.threshold');
  return renderIotTypeMarker(text, ruleType === 'offline' ? 'warning' : 'processing');
}

/** 告警记录流程态（右固定 lifecycle） */
export function renderIotAlertStatusTag(t: TFunction, status?: string | null) {
  const open = String(status ?? '').toLowerCase() === 'open';
  return (
    <StatusTag color={open ? 'error' : 'default'}>
      {open ? t('app.kuaiiot.status.open') : t('app.kuaiiot.status.acknowledged')}
    </StatusTag>
  );
}
