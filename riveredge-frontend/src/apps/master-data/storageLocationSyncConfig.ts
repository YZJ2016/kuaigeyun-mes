import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import { loadSyncCustomTargetFields } from '../../components/sync-from-source-modal/loadSyncCustomTargetFields';
import {
  getStorageLocationSyncBinding,
  syncStorageLocationsFromSource,
} from './services/warehouse';
import {
  STORAGE_LOCATION_SYNC_AVAILABLE_TARGET_FIELDS,
  STORAGE_LOCATION_SYNC_CUSTOM_FIELD_TABLE,
  STORAGE_LOCATION_SYNC_REQUIRED_TARGETS,
  STORAGE_LOCATION_SYNC_TARGET_FIELDS,
} from './pages/warehouse/storage-locations/storageLocationSyncFields';

export function createStorageLocationSyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.master-data.storageLocations.syncFromSource',
    hintKey: 'app.master-data.storageLocations.syncHint',
    apiRealtimeHintKey: 'app.master-data.storageLocations.syncApiHint',
    datasetBatchHintKey: 'app.master-data.storageLocations.syncDatasetHint',
    targetFields: STORAGE_LOCATION_SYNC_TARGET_FIELDS,
    availableTargetFields: STORAGE_LOCATION_SYNC_AVAILABLE_TARGET_FIELDS,
    loadAvailableTargetFields: () =>
      loadSyncCustomTargetFields(STORAGE_LOCATION_SYNC_CUSTOM_FIELD_TABLE),
    customFieldTableName: STORAGE_LOCATION_SYNC_CUSTOM_FIELD_TABLE,
    requiredTargets: STORAGE_LOCATION_SYNC_REQUIRED_TARGETS,
    getBinding: getStorageLocationSyncBinding,
    syncFromSource: syncStorageLocationsFromSource,
    completeSuccessKey: 'app.master-data.storageLocations.syncComplete',
    completePartialKey: 'app.master-data.storageLocations.syncPartial',
    failedKey: 'app.master-data.storageLocations.syncFailed',
    historySourceType: 'storage_location',
  };
}
