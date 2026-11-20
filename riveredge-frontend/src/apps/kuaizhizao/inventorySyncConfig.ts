import type { TFunction } from 'i18next';
import type { SyncFromSourceConfig } from '../../components/sync-from-source-modal/types';
import { getInventorySyncBinding, syncInventoryFromSource } from './services/inventory';

export const INVENTORY_SYNC_TARGET_FIELDS: import('../../components/sync-from-source-modal/types').SyncTargetField[] = [
  { value: 'material_code', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.materialCode', required: true },
  { value: 'quantity', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.quantity', required: true },
  { value: 'base_quantity', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.baseQuantity' },
  { value: 'aux_quantity', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.auxQuantity' },
  { value: 'aux_unit', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.auxUnit' },
  { value: 'warehouse_code', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.warehouseCode' },
  { value: 'warehouse_name', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.warehouseName' },
  { value: 'location_code', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.locationCode' },
  { value: 'location_name', labelKey: 'app.kuaizhizao.warehouseInventory.syncField.locationName' },
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

function inventorySyncLooksXingkong(ctx?: {
  connectionType?: string | null;
  apiPath?: string | null;
  apiCode?: string | null;
}): boolean {
  const conn = String(ctx?.connectionType || '').toLowerCase();
  const path = String(ctx?.apiPath || '').toLowerCase().replace(/\\/g, '/');
  const code = String(ctx?.apiCode || '').toLowerCase();
  if (conn.includes('galaxy') || conn.includes('xinghan')) return true;
  if (path.includes('executebillquery') || path.includes('stk_inventory')) return true;
  // 精确后缀：query_inventory（不含 detail/balance）
  if (code === 'query_inventory' || code.endsWith('_query_inventory')) return true;
  return false;
}

function inventorySyncLooksCosmic(ctx?: {
  connectionType?: string | null;
  apiPath?: string | null;
  apiCode?: string | null;
}): boolean {
  const conn = String(ctx?.connectionType || '').toLowerCase();
  const path = String(ctx?.apiPath || '').toLowerCase().replace(/\\/g, '/');
  const code = String(ctx?.apiCode || '').toLowerCase();
  if (conn.includes('cosmic')) return true;
  if (path.includes('getinventorydetail') || path.includes('getinventoryavbqty')) return true;
  if (code.includes('query_inventory_detail') || code.includes('query_inventory_balance')) {
    return true;
  }
  return false;
}

export function validateInventorySyncMapping(
  targetToSource: Record<string, string>,
  t: TFunction,
  ctx?: {
    connectionType?: string | null;
    apiPath?: string | null;
    apiCode?: string | null;
  },
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
  // 苍穹同仓多行靠仓位拆键：缺库位会压行；星空 STK_Inventory 默认无仓位列，禁止一律强制
  const xingkong = inventorySyncLooksXingkong(ctx);
  const cosmic = inventorySyncLooksCosmic(ctx);
  if (cosmic && !xingkong && !targetToSource.location_code && !targetToSource.location_name) {
    return t('app.kuaizhizao.warehouseInventory.syncLocationRequired');
  }
  return null;
}

/**
 * 星空：ExecuteBillQuery STK_Inventory（后缀 query_inventory）
 * 苍穹：getInventoryDetail / getInventoryAvbQty（query_inventory_detail / balance）
 * 须同时声明后缀 + path + 连接器类型，禁止只认苍穹后缀把星空接口挤掉。
 */
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
    historySourceType: 'material_batch',
    preferredApiCodeSuffixes: [
      'query_inventory',
      'query_inventory_detail',
      'query_inventory_balance',
    ],
    preferredApiPathTokens: [
      'executebillquery',
      'getinventorydetail',
      'getinventoryavbqty',
      'stk_inventory',
    ],
    preferredConnectorTypes: ['kingdee_galaxy', 'kingdee_cosmic', 'kingdee_xinghan'],
    previewPreferredSourceKeys: [
      // 星空 STK_Inventory
      'FMaterialId.FNumber',
      'FMaterialName',
      'FStockId.FNumber',
      'FStockName',
      'FLot.FNumber',
      'FBaseQty',
      'FQty',
      // 苍穹 getInventory*
      'material.number',
      'material_number',
      'avbqty',
      'qty',
      'baseqty',
      'avbqty2nd',
      'qty2nd',
      'unit2nd.number',
      'unit2nd.name',
      'secqty',
      'secunit_number',
      'warehouse.number',
      'location.number',
      'location.name',
      'lotnum',
    ],
    targetAliases: {
      material_code: [
        'FMaterialId.FNumber',
        'FMaterialIdFNumber',
        'FMaterialId.Number',
        'material.number',
        'material_number',
        'number',
      ],
      material_name: ['FMaterialName', 'material.name', 'material_name'],
      quantity: ['FBaseQty', 'FQty', 'avbqty', 'qty', 'quantity'],
      base_quantity: ['FBaseQty', 'baseqty', 'avbbaseqty', 'base_qty', 'base_quantity'],
      aux_quantity: [
        'avbqty2nd',
        'qty2nd',
        'secqty',
        'sec_qty',
        'secQty',
        'auxqty',
        'FSecQty',
        'FExtAuxUnitQty',
      ],
      aux_unit: [
        'unit2nd.number',
        'unit2nd.name',
        'unit2nd',
        'secunit_number',
        'secunit.number',
        'secunit_name',
        'secunit.name',
        'secunit',
        'auxunit_number',
      ],
      warehouse_code: [
        'FStockId.FNumber',
        'FStockIdFNumber',
        'FStockId.Number',
        'warehouse.number',
        'warehouse_number',
        'stock.number',
      ],
      warehouse_name: ['FStockName', 'warehouse.name', 'warehouse_name', 'stock.name'],
      batch_no: [
        'FLot.FNumber',
        'FLotFNumber',
        'FLot.Number',
        'lotnum',
        'lot_number',
        'lot.number',
        'batch_no',
      ],
      location_code: ['location.number', 'location_number', 'loc.number', 'FStockLocId.FNumber'],
      location_name: ['location.name', 'location_name', 'FStockLocId.FName'],
      unit: ['unit.number', 'unit_number', 'unit.name', 'inventoryunit_number', 'FUnitId.FNumber'],
    },
  };
}
