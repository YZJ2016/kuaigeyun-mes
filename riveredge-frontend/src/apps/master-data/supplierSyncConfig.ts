import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import { loadSyncCustomTargetFields } from '../../components/sync-from-source-modal/loadSyncCustomTargetFields';
import { getSupplierSyncBinding, syncSuppliersFromSource } from './services/supply-chain';
import {
  SUPPLIER_SYNC_AVAILABLE_TARGET_FIELDS,
  SUPPLIER_SYNC_CUSTOM_FIELD_TABLE,
  SUPPLIER_SYNC_MAPPING_EXPORT_FILENAME,
  SUPPLIER_SYNC_PREVIEW_PREFERRED_SOURCE_KEYS,
  SUPPLIER_SYNC_REQUIRED_TARGETS,
  SUPPLIER_SYNC_TARGET_ALIASES,
  SUPPLIER_SYNC_TARGET_FIELDS,
} from './pages/supply-chain/suppliers/supplierSyncFields';

export function createSupplierSyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.master-data.suppliers.syncFromSource',
    hintKey: 'app.master-data.suppliers.syncHint',
    apiRealtimeHintKey: 'app.master-data.suppliers.syncApiHint',
    datasetBatchHintKey: 'app.master-data.suppliers.syncDatasetHint',
    targetFields: SUPPLIER_SYNC_TARGET_FIELDS,
    availableTargetFields: SUPPLIER_SYNC_AVAILABLE_TARGET_FIELDS,
    loadAvailableTargetFields: () => loadSyncCustomTargetFields(SUPPLIER_SYNC_CUSTOM_FIELD_TABLE),
    customFieldTableName: SUPPLIER_SYNC_CUSTOM_FIELD_TABLE,
    requiredTargets: SUPPLIER_SYNC_REQUIRED_TARGETS,
    // 默认优先「苍穹查询供应商」query_supplier；别名见 docs/供应商.md
    preferredApiCodeSuffixes: ['query_supplier'],
    preferredApiPathTokens: ['bd_supplier', 'executebillquery'],
    preferredConnectorTypes: ['kingdee_cosmic', 'kingdee_galaxy', 'kingdee_xinghan'],
    previewPreferredSourceKeys: SUPPLIER_SYNC_PREVIEW_PREFERRED_SOURCE_KEYS,
    targetAliases: SUPPLIER_SYNC_TARGET_ALIASES,
    mappingExportFileName: SUPPLIER_SYNC_MAPPING_EXPORT_FILENAME,
    getBinding: getSupplierSyncBinding,
    syncFromSource: syncSuppliersFromSource,
    completeSuccessKey: 'app.master-data.suppliers.syncComplete',
    completePartialKey: 'app.master-data.suppliers.syncPartial',
    failedKey: 'app.master-data.suppliers.syncFailed',
    historySourceType: 'supplier',
  };
}
