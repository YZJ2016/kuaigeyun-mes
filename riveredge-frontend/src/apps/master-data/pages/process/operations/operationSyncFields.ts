import type { SyncTargetField } from '../../../../../components/sync-from-source-modal/types';

export const OPERATION_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'code', labelKey: 'app.master-data.operations.syncField.code', required: true },
  { value: 'name', labelKey: 'app.master-data.operations.syncField.name', required: true },
];

export const OPERATION_SYNC_AVAILABLE_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'description', labelKey: 'app.master-data.operations.syncField.description' },
  { value: 'is_active', labelKey: 'app.master-data.operations.syncField.isActive' },
  { value: 'reporting_type', labelKey: 'app.master-data.operations.syncField.reportingType' },
];

export const OPERATION_SYNC_REQUIRED_TARGETS = ['code', 'name'];
