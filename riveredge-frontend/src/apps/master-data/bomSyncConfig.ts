import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import {
  getEngineeringBomSyncBinding,
  syncEngineeringBomFromSource,
} from './services/material';
import {
  BOM_SYNC_AVAILABLE_TARGET_FIELDS,
  BOM_SYNC_REQUIRED_TARGETS,
  BOM_SYNC_TARGET_FIELDS,
} from './pages/materials/bomSyncFields';

export function createEngineeringBomSyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.master-data.bom.syncFromSource',
    hintKey: 'app.master-data.bom.syncHint',
    apiRealtimeHintKey: 'app.master-data.bom.syncApiHint',
    datasetBatchHintKey: 'app.master-data.bom.syncDatasetHint',
    targetFields: BOM_SYNC_TARGET_FIELDS,
    availableTargetFields: BOM_SYNC_AVAILABLE_TARGET_FIELDS,
    requiredTargets: BOM_SYNC_REQUIRED_TARGETS,
    // line_key 由 parent|version|component 派生，不必映射源列
    matchKeyField: 'line_key',
    getBinding: getEngineeringBomSyncBinding,
    syncFromSource: syncEngineeringBomFromSource,
    completeSuccessKey: 'app.master-data.bom.syncComplete',
    completePartialKey: 'app.master-data.bom.syncPartial',
    failedKey: 'app.master-data.bom.syncFailed',
  };
}
