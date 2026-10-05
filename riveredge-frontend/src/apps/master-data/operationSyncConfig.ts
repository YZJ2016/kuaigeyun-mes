import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import {
  getOperationSyncBinding,
  syncOperationsFromSource,
} from './services/process';
import {
  OPERATION_SYNC_AVAILABLE_TARGET_FIELDS,
  OPERATION_SYNC_REQUIRED_TARGETS,
  OPERATION_SYNC_TARGET_FIELDS,
} from './pages/process/operations/operationSyncFields';

export function createOperationSyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.master-data.operations.syncFromSource',
    hintKey: 'app.master-data.operations.syncHint',
    apiRealtimeHintKey: 'app.master-data.operations.syncApiHint',
    datasetBatchHintKey: 'app.master-data.operations.syncDatasetHint',
    targetFields: OPERATION_SYNC_TARGET_FIELDS,
    availableTargetFields: OPERATION_SYNC_AVAILABLE_TARGET_FIELDS,
    requiredTargets: OPERATION_SYNC_REQUIRED_TARGETS,
    getBinding: getOperationSyncBinding,
    syncFromSource: syncOperationsFromSource,
    completeSuccessKey: 'app.master-data.operations.syncComplete',
    completePartialKey: 'app.master-data.operations.syncPartial',
    failedKey: 'app.master-data.operations.syncFailed',
  };
}
