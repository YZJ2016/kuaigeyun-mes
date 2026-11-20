import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import {
  getWarehouseLocationRefSyncBinding,
  syncWarehouseLocationRefsFromSource,
} from './services/warehouse';
import {
  WAREHOUSE_LOCATION_REF_SYNC_REQUIRED_TARGETS,
  WAREHOUSE_LOCATION_REF_SYNC_TARGET_FIELDS,
} from './pages/warehouse/warehouses/warehouseLocationRefSyncFields';

export function createWarehouseLocationRefSyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.master-data.warehouses.locationRefSyncFromSource',
    hintKey: 'app.master-data.warehouses.locationRefSyncHint',
    syncCallParamsLocalCodes: 'warehouse',
    apiRealtimeHintKey: 'app.master-data.warehouses.locationRefSyncApiHint',
    datasetBatchHintKey: 'app.master-data.warehouses.locationRefSyncDatasetHint',
    targetFields: WAREHOUSE_LOCATION_REF_SYNC_TARGET_FIELDS,
    requiredTargets: WAREHOUSE_LOCATION_REF_SYNC_REQUIRED_TARGETS,
    matchKeyField: 'location_code',
    getBinding: getWarehouseLocationRefSyncBinding,
    syncFromSource: syncWarehouseLocationRefsFromSource,
    completeSuccessKey: 'app.master-data.warehouses.locationRefSyncComplete',
    completePartialKey: 'app.master-data.warehouses.locationRefSyncPartial',
    failedKey: 'app.master-data.warehouses.locationRefSyncFailed',
    historySourceType: 'warehouse_location_ref',
    preferredApiCodeSuffixes: ['query_warelocareference'],
    previewPreferredSourceKeys: [
      'location_number',
      'warehouse_number',
      'isdefaultloc',
      'location_name',
      'warehouse_name',
    ],
    targetAliases: {
      location_code: ['location_number', 'locationNumber', 'LocationNumber'],
      location_name: ['location_name', 'locationName', 'LocationName'],
      warehouse_code: ['warehouse_number', 'warehouseNumber', 'WarehouseNumber'],
      is_default_loc: ['isdefaultloc', 'isDefaultLoc', 'IsDefaultLoc'],
    },
    mappingExportFileName: 'warehouse-location-ref-sync-field-mapping.json',
  };
}
