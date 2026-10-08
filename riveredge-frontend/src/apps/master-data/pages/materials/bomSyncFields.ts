import type { SyncTargetField } from '../../../../components/sync-from-source-modal/types';

export const BOM_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'parent_code', labelKey: 'app.master-data.bom.syncField.parentCode', required: true },
  { value: 'component_code', labelKey: 'app.master-data.bom.syncField.componentCode', required: true },
  { value: 'quantity', labelKey: 'app.master-data.bom.syncField.quantity', required: true },
  { value: 'version', labelKey: 'app.master-data.bom.syncField.version' },
  { value: 'bom_code', labelKey: 'app.master-data.bom.syncField.bomCode' },
];

export const BOM_SYNC_AVAILABLE_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'base_quantity', labelKey: 'app.master-data.bom.syncField.baseQuantity' },
  { value: 'waste_rate', labelKey: 'app.master-data.bom.syncField.wasteRate' },
  { value: 'unit', labelKey: 'app.master-data.bom.syncField.unit' },
  { value: 'bom_name', labelKey: 'app.master-data.bom.syncField.bomName' },
  { value: 'is_required', labelKey: 'app.master-data.bom.syncField.isRequired' },
];

export const BOM_SYNC_REQUIRED_TARGETS = ['parent_code', 'component_code', 'quantity'];
