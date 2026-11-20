import type { SyncTargetField } from '../../../../../components/sync-from-source-modal/types';

export const WAREHOUSE_LOCATION_REF_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  {
    value: 'location_code',
    labelKey: 'app.master-data.warehouses.locationRefSyncField.locationCode',
    required: true,
  },
  {
    value: 'location_name',
    labelKey: 'app.master-data.warehouses.locationRefSyncField.locationName',
    required: true,
  },
  {
    value: 'warehouse_code',
    labelKey: 'app.master-data.warehouses.locationRefSyncField.warehouseCode',
    required: true,
  },
  {
    value: 'is_default_loc',
    labelKey: 'app.master-data.warehouses.locationRefSyncField.isDefaultLoc',
  },
];

export const WAREHOUSE_LOCATION_REF_SYNC_REQUIRED_TARGETS = [
  'location_code',
  'location_name',
  'warehouse_code',
];
