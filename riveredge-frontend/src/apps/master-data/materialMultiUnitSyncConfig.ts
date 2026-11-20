import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import {
  getMaterialMultiUnitSyncBinding,
  syncMaterialMultiUnitsFromSource,
} from './services/material';
import {
  MATERIAL_MULTI_UNIT_SYNC_REQUIRED_TARGETS,
  MATERIAL_MULTI_UNIT_SYNC_TARGET_FIELDS,
} from './pages/materials/materialMultiUnitSyncFields';

export function createMaterialMultiUnitSyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.master-data.materials.multiUnitSyncFromSource',
    hintKey: 'app.master-data.materials.multiUnitSyncHint',
    syncCallParamsLocalCodes: 'material',
    apiRealtimeHintKey: 'app.master-data.materials.multiUnitSyncApiHint',
    datasetBatchHintKey: 'app.master-data.materials.multiUnitSyncDatasetHint',
    targetFields: MATERIAL_MULTI_UNIT_SYNC_TARGET_FIELDS,
    requiredTargets: MATERIAL_MULTI_UNIT_SYNC_REQUIRED_TARGETS,
    matchKeyField: 'material_code',
    getBinding: getMaterialMultiUnitSyncBinding,
    syncFromSource: syncMaterialMultiUnitsFromSource,
    completeSuccessKey: 'app.master-data.materials.multiUnitSyncComplete',
    completePartialKey: 'app.master-data.materials.multiUnitSyncPartial',
    failedKey: 'app.master-data.materials.multiUnitSyncFailed',
    historySourceType: 'material_multi_unit',
    preferredApiCodeSuffixes: ['query_multimeasureunit'],
    previewPreferredSourceKeys: [
      'materialid_number',
      'measureunitid_number',
      'measureunitid_name',
      'numerator',
      'denominator',
      'converttype',
    ],
    targetAliases: {
      material_code: [
        'materialid_number',
        'materialid.number',
        'materialidNumber',
        'MaterialId.Number',
      ],
      unit_code: [
        'measureunitid_number',
        'measureunitid.number',
        'measureunitidNumber',
        'MeasureUnitId.Number',
      ],
      unit_name: [
        'measureunitid_name',
        'measureunitid.name',
        'measureunitidName',
        'MeasureUnitId.Name',
      ],
      conversion_type: ['converttype', 'convertType', 'ConvertType'],
    },
    mappingExportFileName: 'material-multi-unit-sync-field-mapping.json',
  };
}
