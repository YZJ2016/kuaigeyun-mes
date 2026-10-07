/**
 * 设备连接页接口封装。共享读写复用 services/kuaiiot；
 * 建机/轮换返回 DeviceTokenOut（凭据只在本次响应出现），rotate-token 在 services 未导出，
 * 这里按既有 apiRequest 方式补齐页面封装，URL/method/响应外层不变。
 */

import { apiRequest } from '../../../../services/api';
import type { DeviceOut } from '../../services/kuaiiot';

export type DeviceRow = DeviceOut & {
  created_at?: string | null;
};

/** POST /devices 实际返回 DeviceTokenOut：DeviceOut + 一次性 device_token。 */
export type DeviceTokenRow = DeviceRow & {
  device_token: string;
};

export function listDeviceRows(): Promise<DeviceRow[]> {
  return apiRequest<DeviceRow[]>('/apps/kuaiiot/devices');
}

export function getDeviceRow(deviceId: number): Promise<DeviceRow> {
  return apiRequest<DeviceRow>(`/apps/kuaiiot/devices/${deviceId}`);
}

/** 建机响应含一次性 device_token，调用方必须当次展示、之后不得回显。 */
export function createDeviceRow(payload: {
  connection_id?: number;
  external_device_id: string;
  code: string;
  name: string;
  equipment_uuid?: string;
  template_code?: string;
  remark?: string;
}): Promise<DeviceTokenRow> {
  return apiRequest<DeviceTokenRow>('/apps/kuaiiot/devices', { method: 'POST', data: payload });
}

export function updateDeviceRow(
  deviceId: number,
  payload: {
    name?: string;
    connection_id?: number | null;
    equipment_uuid?: string;
    clear_equipment?: boolean;
    group_id?: number | null;
    product_id?: number | null;
    remark?: string | null;
  },
): Promise<DeviceRow> {
  return apiRequest<DeviceRow>(`/apps/kuaiiot/devices/${deviceId}`, { method: 'PUT', data: payload });
}

export function deleteDeviceRow(deviceId: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaiiot/devices/${deviceId}`, { method: 'DELETE' });
}

/** 轮换设备凭据；新凭据只在本次响应出现一次。 */
export function rotateDeviceToken(deviceId: number): Promise<DeviceTokenRow> {
  return apiRequest<DeviceTokenRow>(`/apps/kuaiiot/devices/${deviceId}/rotate-token`, {
    method: 'POST',
  });
}
