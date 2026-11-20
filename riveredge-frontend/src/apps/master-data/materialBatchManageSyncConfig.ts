import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import {
  getMaterialBatchManageSyncBinding,
  syncMaterialBatchManageFromSource,
} from './services/material';
import {
  MATERIAL_BATCH_MANAGE_DEFAULT_TARGET_TO_SOURCE,
  MATERIAL_BATCH_MANAGE_SYNC_REQUIRED_TARGETS,
  MATERIAL_BATCH_MANAGE_SYNC_TARGET_FIELDS,
} from './pages/materials/materialBatchManageSyncFields';

export function createMaterialBatchManageSyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.master-data.materials.batchManageSyncFromSource',
    hintKey: 'app.master-data.materials.batchManageSyncHint',
    syncCallParamsLocalCodes: 'material',
    apiRealtimeHintKey: 'app.master-data.materials.batchManageSyncApiHint',
    datasetBatchHintKey: 'app.master-data.materials.batchManageSyncDatasetHint',
    targetFields: MATERIAL_BATCH_MANAGE_SYNC_TARGET_FIELDS,
    requiredTargets: MATERIAL_BATCH_MANAGE_SYNC_REQUIRED_TARGETS,
    matchKeyField: 'material_code',
    getBinding: getMaterialBatchManageSyncBinding,
    syncFromSource: syncMaterialBatchManageFromSource,
    completeSuccessKey: 'app.master-data.materials.batchManageSyncComplete',
    completePartialKey: 'app.master-data.materials.batchManageSyncPartial',
    failedKey: 'app.master-data.materials.batchManageSyncFailed',
    historySourceType: 'material_batch_manage',
    preferredApiCodeSuffixes: [
      'query_material_inventory_info',
      'getmatinfo_bd_materialinventoryinfo',
    ],
    previewPreferredSourceKeys: [
      'masterid_number',
      'masterid.number',
      'enablelot',
      'masterid_enablelot',
      'enableserial',
    ],
    targetAliases: {
      material_code: [
        'masterid_number',
        'masterid.number',
        'masteridNumber',
        'number',
        'Number',
      ],
      batch_managed: [
        'enablelot',
        'enableLot',
        'masterid_enablelot',
        'masterid.enablelot',
        'FIsBatchManage',
      ],
    },
    /** 未手填时注入库存信息固定列；后端 inventory helper 亦不依赖映射 */
    sanitizeMapping: (mapping) => ({
      ...MATERIAL_BATCH_MANAGE_DEFAULT_TARGET_TO_SOURCE,
      ...Object.fromEntries(
        Object.entries(mapping || {}).filter(([, source]) => Boolean(String(source || '').trim())),
      ),
    }),
    mappingExportFileName: 'material-batch-manage-sync-field-mapping.json',
  };
}
