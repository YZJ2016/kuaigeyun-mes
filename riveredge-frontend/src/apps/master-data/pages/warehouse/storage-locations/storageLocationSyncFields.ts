import type { SyncTargetField } from '../../../../../components/sync-from-source-modal/types';

export const STORAGE_LOCATION_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  {
    value: 'code',
    labelKey: 'app.master-data.storageLocations.syncField.code',
    required: true,
  },
  {
    value: 'name',
    labelKey: 'app.master-data.storageLocations.syncField.name',
    required: true,
  },
  {
    value: 'enable',
    labelKey: 'app.master-data.storageLocations.syncField.enable',
  },
  {
    value: 'forbid_status',
    labelKey: 'app.master-data.storageLocations.syncField.forbidStatus',
  },
];

export const STORAGE_LOCATION_SYNC_AVAILABLE_TARGET_FIELDS: SyncTargetField[] = [
  {
    value: 'description',
    labelKey: 'app.master-data.storageLocations.syncField.description',
  },
  {
    value: 'is_active',
    labelKey: 'app.master-data.storageLocations.syncField.isActive',
  },
];

export const STORAGE_LOCATION_SYNC_REQUIRED_TARGETS = ['code', 'name'];
export const STORAGE_LOCATION_SYNC_CUSTOM_FIELD_TABLE =
  'master_data_warehouse_storage_locations';
