/**
 * 数采链路数据源。连接/设备/点位走各自 list 端点，前端现建关联图；
 * MES 设备名称优先取 equipment-ops-feed 的绑定设备清单，失败时回退
 * 星制造设备列表；两端都失败时该列显示原因。
 */

import {
  getEquipmentOpsFeed,
  listConnections,
  listDevices,
  listTags,
  type ConnectionOut,
  type DeviceOut,
  type TagOut,
} from '../../services/kuaiiot';
import { equipmentApi } from '../../../kuaizhizao/services/equipment';

export type PipelineEquipment = { uuid: string; code: string; name: string };

export type PipelineSourceKey = 'connections' | 'devices' | 'tags' | 'equipment';

export type PipelineSources = {
  connections?: ConnectionOut[];
  devices?: DeviceOut[];
  tags?: TagOut[];
  equipment?: PipelineEquipment[];
  errors: Partial<Record<PipelineSourceKey, string>>;
};

function reasonOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '接口读取失败或无权限';
}

async function loadEquipment(): Promise<PipelineEquipment[]> {
  try {
    const feed = await getEquipmentOpsFeed(24);
    return (feed.equipment_list ?? []).map((row) => ({
      uuid: row.equipment_uuid,
      code: row.code,
      name: row.name,
    }));
  } catch {
    const res = await equipmentApi.list({ is_active: true, limit: 500 });
    const items: Array<{ uuid: string; code: string; name: string }> = res?.items ?? [];
    return items.map((row) => ({ uuid: row.uuid, code: row.code, name: row.name }));
  }
}

export async function loadPipelineSources(): Promise<PipelineSources> {
  const errors: PipelineSources['errors'] = {};
  const sources: PipelineSources = { errors };

  const capture = async <T>(
    key: PipelineSourceKey,
    run: () => Promise<T>,
    apply: (value: T) => void,
  ) => {
    try {
      apply(await run());
    } catch (error) {
      errors[key] = reasonOf(error);
    }
  };

  await Promise.all([
    capture('connections', listConnections, (v) => {
      sources.connections = Array.isArray(v) ? v : [];
    }),
    capture('devices', listDevices, (v) => {
      sources.devices = Array.isArray(v) ? v : [];
    }),
    capture('tags', () => listTags(), (v) => {
      sources.tags = Array.isArray(v) ? v : [];
    }),
    capture('equipment', loadEquipment, (v) => {
      sources.equipment = v;
    }),
  ]);
  return sources;
}
