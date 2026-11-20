import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import { loadSyncCustomTargetFields } from '../../components/sync-from-source-modal/loadSyncCustomTargetFields';
import { getCustomerSyncBinding, syncCustomersFromSource } from './services/supply-chain';
import {
  CUSTOMER_SYNC_AVAILABLE_TARGET_FIELDS,
  CUSTOMER_SYNC_CUSTOM_FIELD_TABLE,
  CUSTOMER_SYNC_MAPPING_EXPORT_FILENAME,
  CUSTOMER_SYNC_REQUIRED_TARGETS,
  CUSTOMER_SYNC_TARGET_ALIASES,
  CUSTOMER_SYNC_TARGET_FIELDS,
} from './pages/supply-chain/customers/customerSyncFields';

export function createCustomerSyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.master-data.customers.syncFromSource',
    hintKey: 'app.master-data.customers.syncHint',
    apiRealtimeHintKey: 'app.master-data.customers.syncApiHint',
    datasetBatchHintKey: 'app.master-data.customers.syncDatasetHint',
    targetFields: CUSTOMER_SYNC_TARGET_FIELDS,
    availableTargetFields: CUSTOMER_SYNC_AVAILABLE_TARGET_FIELDS,
    loadAvailableTargetFields: () => loadSyncCustomTargetFields(CUSTOMER_SYNC_CUSTOM_FIELD_TABLE),
    customFieldTableName: CUSTOMER_SYNC_CUSTOM_FIELD_TABLE,
    requiredTargets: CUSTOMER_SYNC_REQUIRED_TARGETS,
    // 默认优先「苍穹查询客户信息」basedata_query（如 sanyitest_basedata_query）；仍可改选其它接口
    // query_customer 为 batchQuery 预置兜底；别名见 docs/客户信息.md，与销售订单无关
    preferredApiCodeSuffixes: ['basedata_query', 'query_customer'],
    preferredApiPathTokens: ['basedata', 'bd_customer', 'executebillquery'],
    preferredConnectorTypes: ['kingdee_cosmic', 'kingdee_galaxy', 'kingdee_xinghan'],
    targetAliases: CUSTOMER_SYNC_TARGET_ALIASES,
    mappingExportFileName: CUSTOMER_SYNC_MAPPING_EXPORT_FILENAME,
    getBinding: getCustomerSyncBinding,
    syncFromSource: syncCustomersFromSource,
    completeSuccessKey: 'app.master-data.customers.syncComplete',
    completePartialKey: 'app.master-data.customers.syncPartial',
    failedKey: 'app.master-data.customers.syncFailed',
    historySourceType: 'customer',
  };
}
