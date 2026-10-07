/**
 * 边缘配置页封装。列表为数组响应，筛选/排序/分页在前端完成；
 * 详情与导出对 config 做脱敏：不回显凭据类键与现场地址类键的值。
 */

import {
  deleteEdgeConfig,
  getEdgeConfig,
  listDevices,
  listEdgeConfigs,
  requestTrial,
  saveEdgeConfig,
  updateEdgeConfig,
  type DeviceOut,
  type EdgeConfigOut,
  type EdgeConfigWrite,
} from '../../services/kuaiiot';
import {
  filterRowsByListKeyword,
  pickListSearchKeyword,
  pickSearchString,
} from '../../../../utils/tableQueryKey';

export type EdgeConfigRow = EdgeConfigOut;

export const EDGE_PROTOCOLS = ['modbus_tcp', 'modbus_rtu', 'opc_ua', 's7'] as const;

export const EDGE_AGENT_STATUSES = ['online', 'offline', 'error', 'unknown'] as const;

export const PUBLISH_MODES = ['http_ingest', 'mqtt'] as const;

export const MODBUS_DATA_TYPES = ['int16', 'uint16', 'int32', 'uint32', 'float32', 'bool'] as const;

export async function listEdgeConfigRows(): Promise<EdgeConfigRow[]> {
  return listEdgeConfigs();
}

export async function getEdgeConfigRow(configId: number): Promise<EdgeConfigRow> {
  return getEdgeConfig(configId);
}

export async function createEdgeConfigRow(payload: EdgeConfigWrite): Promise<EdgeConfigRow> {
  return saveEdgeConfig(payload);
}

export async function updateEdgeConfigRow(
  configId: number,
  payload: EdgeConfigWrite,
): Promise<EdgeConfigRow> {
  return updateEdgeConfig(configId, payload);
}

export async function deleteEdgeConfigRow(configId: number): Promise<void> {
  return deleteEdgeConfig(configId);
}

export async function requestEdgeTrial(configId: number): Promise<EdgeConfigRow> {
  return requestTrial(configId);
}

export async function listEdgeDeviceRows(): Promise<DeviceOut[]> {
  return listDevices();
}

/**
 * 客户端筛选：模糊词覆盖编码/名称/协议/设备名；高级搜索按列字段收敛。
 */
export function filterEdgeConfigRows(
  rows: EdgeConfigRow[],
  searchFormValues: Record<string, unknown> | undefined,
  deviceLabel: (deviceId: number) => string | undefined,
): EdgeConfigRow[] {
  let out = filterRowsByListKeyword(rows, pickListSearchKeyword(searchFormValues), (row) => [
    row.code,
    row.name,
    row.protocol,
    deviceLabel(row.device_id),
  ]);
  const code = pickSearchString(searchFormValues, 'code');
  if (code) {
    const q = code.toLowerCase();
    out = out.filter((row) => (row.code || '').toLowerCase().includes(q));
  }
  const name = pickSearchString(searchFormValues, 'name');
  if (name) {
    const q = name.toLowerCase();
    out = out.filter((row) => (row.name || '').toLowerCase().includes(q));
  }
  const deviceId = pickSearchString(searchFormValues, 'device_id');
  if (deviceId) {
    out = out.filter((row) => String(row.device_id) === deviceId);
  }
  const protocol = pickSearchString(searchFormValues, 'protocol');
  if (protocol) {
    out = out.filter((row) => row.protocol === protocol);
  }
  const agentStatus = pickSearchString(searchFormValues, 'agent_status');
  if (agentStatus) {
    out = out.filter((row) => row.agent_status === agentStatus);
  }
  const isEnabled = pickSearchString(searchFormValues, 'is_enabled');
  if (isEnabled) {
    out = out.filter((row) => String(row.is_enabled) === isEnabled);
  }
  return out;
}

/** 客户端排序：仅在用户点击列头排序时生效，未点保持接口顺序。 */
export function sortLocalRows<T extends Record<string, unknown>>(
  rows: T[],
  sort: Record<string, 'ascend' | 'descend' | null | undefined>,
): T[] {
  const entry = Object.entries(sort || {}).find(([, v]) => v === 'ascend' || v === 'descend');
  if (!entry) return rows;
  const [key, dir] = entry as [string, 'ascend' | 'descend'];
  const factor = dir === 'ascend' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * factor;
    return String(av).localeCompare(String(bv)) * factor;
  });
}

/** 与后端 _SECRET_PARTS 同口径：键名含这些子串的值视为凭据，详情/导出不回显。 */
const SECRET_KEY_PARTS = [
  'token',
  'password',
  'passwd',
  'secret',
  'api_key',
  'access_key',
  'credential',
];

function isSecretKey(key: string): boolean {
  return SECRET_KEY_PARTS.some((part) => key.includes(part));
}

/** 现场地址类键（PLC host、OPC UA endpoint、串口、broker、URL/IP），详情/导出不回显值。 */
function isAddressKey(key: string): boolean {
  return (
    key.includes('host') ||
    key.includes('endpoint') ||
    key.includes('serial_port') ||
    key.includes('broker') ||
    key.includes('url') ||
    key.includes('uri') ||
    key === 'ip' ||
    key.endsWith('_ip') ||
    key.startsWith('ip_')
  );
}

const MASKED_VALUE = '•••';

/** 递归脱敏 config：保留结构（点位键、寄存器、publish 等），凭据/地址类键值替换为 •••。 */
export function maskEdgeConfigForDisplay(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => maskEdgeConfigForDisplay(item));
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      const lowered = key.toLowerCase();
      out[key] =
        isSecretKey(lowered) || isAddressKey(lowered)
          ? MASKED_VALUE
          : maskEdgeConfigForDisplay(item);
    }
    return out;
  }
  return value;
}
