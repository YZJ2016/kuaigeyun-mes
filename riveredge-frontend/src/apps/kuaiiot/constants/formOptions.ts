import type { TFunction } from 'i18next';

export function buildConnectionTypeOptions(t: TFunction) {
  return [
    { label: t('app.kuaiiot.option.connectionType.httpWebhook'), value: 'http_webhook' },
    { label: t('app.kuaiiot.option.connectionType.mqtt'), value: 'mqtt' },
    { label: t('app.kuaiiot.option.connectionType.thingsboard'), value: 'thingsboard' },
    { label: t('app.kuaiiot.option.connectionType.jetlinks'), value: 'jetlinks' },
  ];
}

export function buildPayloadFormatOptions(t: TFunction) {
  return [
    { label: t('app.kuaiiot.option.payloadFormat.auto'), value: 'auto' },
    { label: t('app.kuaiiot.option.payloadFormat.kuaiiot'), value: 'kuaiiot' },
    { label: t('app.kuaiiot.option.payloadFormat.sanyiLine'), value: 'sanyi_line' },
  ];
}

export function translatePayloadFormat(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    auto: t('app.kuaiiot.option.payloadFormat.auto'),
    kuaiiot: t('app.kuaiiot.option.payloadFormat.kuaiiot'),
    sanyi_line: t('app.kuaiiot.option.payloadFormat.sanyiLine'),
    invalid_json: t('app.kuaiiot.option.payloadFormat.invalidJson'),
    unknown: t('app.kuaiiot.status.unknown'),
  };
  return map[value] ?? value;
}

export function translateConnectionType(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    http_webhook: t('app.kuaiiot.option.connectionType.httpWebhook'),
    mqtt: t('app.kuaiiot.option.connectionType.mqtt'),
    thingsboard: t('app.kuaiiot.option.connectionType.thingsboard'),
    jetlinks: t('app.kuaiiot.option.connectionType.jetlinks'),
  };
  return map[value] ?? value;
}

export function translateHealthStatus(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    healthy: t('app.kuaiiot.option.health.healthy'),
    unhealthy: t('app.kuaiiot.option.health.unhealthy'),
    unknown: t('app.kuaiiot.status.unknown'),
  };
  return map[value] ?? value;
}

export function buildValueTypeOptions(t: TFunction) {
  return [
    { label: t('app.kuaiiot.option.valueType.number'), value: 'number' },
    { label: t('app.kuaiiot.option.valueType.string'), value: 'string' },
    { label: t('app.kuaiiot.option.valueType.boolean'), value: 'boolean' },
  ];
}

export function translateValueType(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    number: t('app.kuaiiot.option.valueType.number'),
    string: t('app.kuaiiot.option.valueType.string'),
    boolean: t('app.kuaiiot.option.valueType.boolean'),
  };
  return map[value] ?? value;
}

export function buildMapTargetOptions(t: TFunction) {
  return [
    { label: t('app.kuaiiot.option.mapTarget.status'), value: 'status' },
    { label: t('app.kuaiiot.option.mapTarget.temperature'), value: 'temperature' },
    { label: t('app.kuaiiot.option.mapTarget.pressure'), value: 'pressure' },
    { label: t('app.kuaiiot.option.mapTarget.vibration'), value: 'vibration' },
    { label: t('app.kuaiiot.option.mapTarget.isOnline'), value: 'is_online' },
  ];
}

export function formatIotTagLabel(name?: string | null, tagKey?: string | null) {
  const n = (name || '').trim();
  const k = (tagKey || '').trim();
  if (n && k && n !== k) return `${n} / ${k}`;
  return n || k || '-';
}

export function translateMapTarget(t: TFunction, value?: string | null, displayName?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    status: t('app.kuaiiot.option.mapTarget.status'),
    temperature: t('app.kuaiiot.option.mapTarget.temperature'),
    pressure: t('app.kuaiiot.option.mapTarget.pressure'),
    vibration: t('app.kuaiiot.option.mapTarget.vibration'),
    is_online: t('app.kuaiiot.option.mapTarget.isOnline'),
  };
  if (map[value]) return map[value];
  if (value.startsWith('other_parameters.')) {
    const field = (displayName || '').trim() || value.slice('other_parameters.'.length);
    return t('app.kuaiiot.option.mapTarget.otherParametersNamed', { name: field });
  }
  return value;
}

export function buildFillTargetOptions(t: TFunction) {
  return [
    { label: t('app.kuaiiot.option.fillTarget.sopTemp'), value: 'sop_parameters.temp' },
    { label: t('app.kuaiiot.option.fillTarget.sopPressure'), value: 'sop_parameters.pressure' },
    { label: t('app.kuaiiot.option.fillTarget.spotCheckItem'), value: 'spot_check.item_code' },
  ];
}

export function buildSeverityOptions(t: TFunction) {
  return [
    { label: t('app.kuaiiot.option.severity.info'), value: 'info' },
    { label: t('app.kuaiiot.option.severity.warning'), value: 'warning' },
    { label: t('app.kuaiiot.option.severity.critical'), value: 'critical' },
  ];
}

export function translateSeverity(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    info: t('app.kuaiiot.option.severity.info'),
    warning: t('app.kuaiiot.option.severity.warning'),
    critical: t('app.kuaiiot.option.severity.critical'),
  };
  return map[value] ?? value;
}

export const OPERATOR_OPTIONS = [
  { label: '>', value: 'gt' },
  { label: '<', value: 'lt' },
  { label: '>=', value: 'gte' },
  { label: '<=', value: 'lte' },
  { label: '=', value: 'eq' },
  { label: '!=', value: 'ne' },
];

export function buildProtocolOptions(t: TFunction) {
  return [
    { label: t('app.kuaiiot.option.protocol.modbusTcp'), value: 'modbus_tcp' },
    { label: t('app.kuaiiot.option.protocol.modbusRtu'), value: 'modbus_rtu' },
    { label: t('app.kuaiiot.option.protocol.opcUa'), value: 'opc_ua' },
    { label: t('app.kuaiiot.option.protocol.s7'), value: 's7' },
  ];
}

export function translateProtocol(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    modbus_tcp: t('app.kuaiiot.option.protocol.modbusTcp'),
    modbus_rtu: t('app.kuaiiot.option.protocol.modbusRtu'),
    opc_ua: t('app.kuaiiot.option.protocol.opcUa'),
    s7: t('app.kuaiiot.option.protocol.s7'),
  };
  return map[value] ?? value;
}

export const QOS_OPTIONS = [
  { label: '0', value: 0 },
  { label: '1', value: 1 },
  { label: '2', value: 2 },
];

export function buildCooldownOptions(t: TFunction) {
  return [
    { label: t('app.kuaiiot.option.cooldown.1m'), value: 60 },
    { label: t('app.kuaiiot.option.cooldown.5m'), value: 300 },
    { label: t('app.kuaiiot.option.cooldown.10m'), value: 600 },
    { label: t('app.kuaiiot.option.cooldown.30m'), value: 1800 },
    { label: t('app.kuaiiot.option.cooldown.1h'), value: 3600 },
  ];
}

export function translatePipelineStatus(t: TFunction, status: string) {
  const map: Record<string, string> = {
    healthy: t('app.kuaiiot.option.health.healthy'),
    unhealthy: t('app.kuaiiot.option.health.unhealthy'),
    unknown: t('app.kuaiiot.status.unknown'),
    online: t('app.kuaiiot.status.online'),
    offline: t('app.kuaiiot.status.offline'),
    enabled: t('app.kuaiiot.option.pipelineStatus.enabled'),
    disabled: t('app.kuaiiot.option.pipelineStatus.disabled'),
    bound: t('app.kuaiiot.option.pipelineStatus.bound'),
    open: t('app.kuaiiot.status.open'),
    acknowledged: t('app.kuaiiot.status.acknowledged'),
  };
  return map[status] ?? status;
}

export function buildCommonTagKeyOptions() {
  return [
    { label: 'status', value: 'status' },
    { label: 'online', value: 'online' },
    { label: 'temp', value: 'temp' },
    { label: 'pressure', value: 'pressure' },
    { label: 'vibration', value: 'vibration' },
    { label: 'barrel_temp', value: 'barrel_temp' },
    { label: 'mold_pressure', value: 'mold_pressure' },
    { label: 'spindle_speed', value: 'spindle_speed' },
    { label: 'feed_rate', value: 'feed_rate' },
    { label: 'load', value: 'load' },
    { label: 'cycle_time', value: 'cycle_time' },
  ];
}

export function buildEventLevelOptions(t: TFunction) {
  return buildSeverityOptions(t);
}

export function buildDispatchChannelOptions(t: TFunction) {
  return [
    { label: t('app.kuaiiot.option.dispatchChannel.edge'), value: 'edge' },
    { label: t('app.kuaiiot.option.dispatchChannel.thingsboard'), value: 'thingsboard' },
    { label: t('app.kuaiiot.option.dispatchChannel.jetlinks'), value: 'jetlinks' },
  ];
}

export function translateDispatchChannel(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    edge: t('app.kuaiiot.option.dispatchChannel.edge'),
    thingsboard: t('app.kuaiiot.option.dispatchChannel.thingsboard'),
    jetlinks: t('app.kuaiiot.option.dispatchChannel.jetlinks'),
  };
  return map[value] ?? value;
}

export function translateCommandStatus(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    pending: t('app.kuaiiot.status.command.pending'),
    sent: t('app.kuaiiot.status.command.sent'),
    success: t('app.kuaiiot.status.command.success'),
    failed: t('app.kuaiiot.status.command.failed'),
    timeout: t('app.kuaiiot.status.command.timeout'),
  };
  return map[value] ?? value;
}

export function translateMessageDirection(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    up: t('app.kuaiiot.option.messageDirection.up'),
    down: t('app.kuaiiot.option.messageDirection.down'),
  };
  return map[value] ?? value;
}

export function translateMessageType(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    ingest: t('app.kuaiiot.option.messageType.ingest'),
    event: t('app.kuaiiot.option.messageType.event'),
    command: t('app.kuaiiot.option.messageType.command'),
    command_result: t('app.kuaiiot.option.messageType.commandResult'),
  };
  return map[value] ?? value;
}

export function translateMessageResult(t: TFunction, value?: string | null) {
  if (!value) return '-';
  const map: Record<string, string> = {
    accepted: t('app.kuaiiot.option.messageResult.accepted'),
    rejected: t('app.kuaiiot.option.messageResult.rejected'),
    synced: t('app.kuaiiot.option.messageResult.synced'),
    error: t('app.kuaiiot.option.messageResult.error'),
  };
  return map[value] ?? value;
}
