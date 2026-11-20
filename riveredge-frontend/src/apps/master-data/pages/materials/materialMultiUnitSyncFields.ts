import type { SyncTargetField } from '../../../../components/sync-from-source-modal/types';

export const MATERIAL_MULTI_UNIT_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  {
    value: 'material_code',
    labelKey: 'app.master-data.materials.multiUnitSyncField.materialCode',
    required: true,
  },
  {
    value: 'unit_code',
    labelKey: 'app.master-data.materials.multiUnitSyncField.unitCode',
    required: true,
  },
  {
    value: 'unit_name',
    labelKey: 'app.master-data.materials.multiUnitSyncField.unitName',
  },
  {
    value: 'numerator',
    labelKey: 'app.master-data.materials.multiUnitSyncField.numerator',
  },
  {
    value: 'denominator',
    labelKey: 'app.master-data.materials.multiUnitSyncField.denominator',
  },
  {
    value: 'conversion_type',
    labelKey: 'app.master-data.materials.multiUnitSyncField.conversionType',
  },
];

export const MATERIAL_MULTI_UNIT_SYNC_REQUIRED_TARGETS = ['material_code', 'unit_code'];
