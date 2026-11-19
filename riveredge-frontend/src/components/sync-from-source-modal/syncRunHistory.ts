import {
  listDocumentPushRunHistory,
  type ListSyncRunHistoryFn,
} from '../../apps/kuaizhizao/services/document-push';
import { apiRequest } from '../../services/api';
import type { DocumentPushRunHistoryListResponse } from '../../apps/kuaizhizao/services/document-push';

/** 主数据入站同步：与 core SyncRunLog.entity_type 一致 */
export const MASTER_DATA_SYNC_HISTORY_ENTITIES = new Set([
  'customer',
  'supplier',
  'warehouse',
  'unit',
  'material',
  'material_group',
  'engineering_bom',
  'process_operation',
]);

export async function listMasterDataSyncRunHistory(params: {
  entityType: string;
  skip?: number;
  limit?: number;
}): Promise<DocumentPushRunHistoryListResponse> {
  return apiRequest<DocumentPushRunHistoryListResponse>(
    '/apps/master-data/sync/run-history',
    {
      params: {
        entity_type: params.entityType,
        skip: params.skip ?? 0,
        limit: params.limit ?? 20,
      },
    },
  );
}

/** SyncFromSourceModal 默认历史加载：主数据走 master-data API，其余走 document-push/run-history */
export function createDefaultSyncRunHistoryLoader(historySourceType: string): ListSyncRunHistoryFn {
  const entity = String(historySourceType || '').trim();
  if (MASTER_DATA_SYNC_HISTORY_ENTITIES.has(entity)) {
    return ({ skip, limit }) =>
      listMasterDataSyncRunHistory({ entityType: entity, skip, limit });
  }
  return ({ skip, limit, targetProfiles }) =>
    listDocumentPushRunHistory({
      sourceType: entity,
      skip,
      limit,
      targetProfiles,
    });
}
