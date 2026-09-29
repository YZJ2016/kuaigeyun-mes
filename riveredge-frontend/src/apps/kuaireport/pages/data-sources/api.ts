/**
 * 数据源登记接口。挂载后路径为 /api/v1/apps/kuaireport/data-sources。
 * 与设计器 listDataSources 同一条 GET，请求走 apiRequest。
 */

import { apiRequest } from '../../../../services/api';

const DATA_SOURCES_BASE = '/apps/kuaireport/data-sources';

export type DataSourceType = 'static' | 'dataset' | 'http';

/** 与 DataSourceOut 一致。列表和详情都是这个形态。 */
export interface DataSourceRow {
  id: number;
  uuid: string;
  name: string;
  type: string;
  config: Record<string, unknown> | null;
  description: string | null;
  is_default: boolean;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

/** 与 DataSourceCreate / DataSourceUpdate 一致，不传 tenant_id、is_system。 */
export interface DataSourceWrite {
  name: string;
  type: DataSourceType;
  config: Record<string, unknown>;
  description?: string | null;
  is_default: boolean;
}

export function listDataSources(): Promise<DataSourceRow[]> {
  return apiRequest<DataSourceRow[]>(DATA_SOURCES_BASE, { method: 'GET' });
}

export function getDataSource(sourceId: number): Promise<DataSourceRow> {
  return apiRequest<DataSourceRow>(`${DATA_SOURCES_BASE}/${sourceId}`, { method: 'GET' });
}

export function createDataSource(data: DataSourceWrite): Promise<DataSourceRow> {
  return apiRequest<DataSourceRow>(DATA_SOURCES_BASE, { method: 'POST', data });
}

export function updateDataSource(sourceId: number, data: DataSourceWrite): Promise<DataSourceRow> {
  return apiRequest<DataSourceRow>(`${DATA_SOURCES_BASE}/${sourceId}`, { method: 'PUT', data });
}

export function deleteDataSource(sourceId: number): Promise<void> {
  return apiRequest<void>(`${DATA_SOURCES_BASE}/${sourceId}`, { method: 'DELETE' });
}
