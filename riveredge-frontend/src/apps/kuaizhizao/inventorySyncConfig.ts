import type { TFunction } from 'i18next';
import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import { getInventorySyncBinding, syncInventoryFromSource } from './services/inventory';

export const INVENTORY_SYNC_TARGET_FIELDS: import('../../components/sync-from-source-modal/types').SyncTargetField[] = [
  { value: 'material_code', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.materialCode', required: true },
  { value: 'quantity', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.quantity', required: true },
  { value: 'warehouse_code', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.warehouseCode' },
  { value: 'warehouse_name', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.warehouseName' },
  { value: 'batch_no', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.batchNo' },
  { value: 'material_name', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.materialName' },
  { value: 'unit', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.unit' },
];

/** 苍穹 warehouse 是对方内码，不是本系统仓库主键；即时库存按编码/名称解析即可。 */
export const INVENTORY_SYNC_AVAILABLE_TARGET_FIELDS: import('../../components/sync-from-source-modal/types').SyncTargetField[] =
  [];

const COSMIC_WAREHOUSE_SOURCE_KEYS = new Set(['warehouse', 'warehouse.number', 'warehouse.name']);

export function sanitizeInventorySyncMapping(
  targetToSource: Record<string, string>,
): Record<string, string> {
  const next = { ...targetToSource };
  const warehouseIdSource = String(next.warehouse_id || '').trim();
  if (warehouseIdSource && COSMIC_WAREHOUSE_SOURCE_KEYS.has(warehouseIdSource)) {
    delete next.warehouse_id;
  }
  return next;
}

export const INVENTORY_SYNC_REQUIRED_TARGETS = ['material_code', 'quantity'];

export function validateInventorySyncMapping(
  targetToSource: Record<string, string>,
  t: TFunction,
): string | null {
  for (const required of INVENTORY_SYNC_REQUIRED_TARGETS) {
    if (!targetToSource[required]) {
      const field = INVENTORY_SYNC_TARGET_FIELDS.find((item) => item.value === required);
      return t('components.syncFromSource.mappingRequired', {
        field: field?.labelKey ? t(field.labelKey) : required,
      });
    }
  }
  if (
    !targetToSource.warehouse_code &&
    !targetToSource.warehouse_name &&
    !targetToSource.warehouse_id
  ) {
    return t('app.kuaizhizao.warehouseInventory.syncWarehouseRequired');
  }
  return null;
}

export function createInventorySyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.kuaizhizao.warehouseInventory.syncFromSource',
    hintKey: 'app.kuaizhizao.warehouseInventory.syncHint',
    apiRealtimeHintKey: 'app.kuaizhizao.warehouseInventory.syncApiHint',
    datasetBatchHintKey: 'app.kuaizhizao.warehouseInventory.syncDatasetHint',
    mainStepTitleKey: 'app.kuaizhizao.warehouseInventory.syncStep.inventory',
    targetFields: INVENTORY_SYNC_TARGET_FIELDS,
    availableTargetFields: INVENTORY_SYNC_AVAILABLE_TARGET_FIELDS,
    requiredTargets: INVENTORY_SYNC_REQUIRED_TARGETS,
    validateMapping: validateInventorySyncMapping,
    sanitizeMapping: sanitizeInventorySyncMapping,
    getBinding: getInventorySyncBinding,
    syncFromSource: syncInventoryFromSource,
    completeSuccessKey: 'app.kuaizhizao.warehouseInventory.syncComplete',
    completePartialKey: 'app.kuaizhizao.warehouseInventory.syncPartial',
    failedKey: 'app.kuaizhizao.warehouseInventory.syncFailed',
  };
}
