import type { TFunction } from 'i18next';
import type { SyncFromSourceConfig } from '../../../../../components/sync-from-source-modal/types';
import { loadSyncCustomTargetFields } from '../../../../../components/sync-from-source-modal/loadSyncCustomTargetFields';
import {
  getMaterialSyncBinding,
  syncMaterialsFromSource,
} from '../../../../master-data/services/material';
import {
  getMaterialUnitSyncBinding,
  syncMaterialUnitsFromSource,
} from '../../../../master-data/services/material-unit';
import {
  getCustomerSyncBinding,
  syncCustomersFromSource,
} from '../../../../master-data/services/supply-chain';
import {
  getSalesOrderSyncBinding,
  syncSalesOrdersFromSource,
} from '../../../services/sales-order';
import {
  SALES_ORDER_SYNC_CUSTOM_FIELD_TABLE,
  SALES_ORDER_SYNC_MAPPING_EXPORT_FILENAME,
  SALES_ORDER_SYNC_REQUIRED_TARGETS,
  SALES_ORDER_SYNC_TARGET_ALIASES,
  SALES_ORDER_SYNC_TARGET_FIELDS,
} from './salesOrderSyncFields';

export function createSalesOrderSyncConfig(): SyncFromSourceConfig {
  return {
    titleKey: 'app.kuaizhizao.salesOrder.syncFromSource',
    hintKey: 'app.kuaizhizao.salesOrder.syncMasterDataFirstHint',
    apiRealtimeHintKey: 'app.kuaizhizao.salesOrder.syncApiHint',
    datasetBatchHintKey: 'app.kuaizhizao.salesOrder.syncDatasetHint',
    mainStepTitleKey: 'app.kuaizhizao.salesOrder.syncStep.salesOrder',
    // 销售订单前置不同步物料分组（bd_materialgroup）；物料页/采购单等仍保留分组前置
    prerequisiteSteps: [
      {
        id: 'customer',
        titleKey: 'app.kuaizhizao.salesOrder.syncStep.customer',
        getBinding: getCustomerSyncBinding,
        syncFromSource: syncCustomersFromSource,
      },
      {
        id: 'unit',
        titleKey: 'app.master-data.materials.syncStep.unit',
        getBinding: getMaterialUnitSyncBinding,
        syncFromSource: syncMaterialUnitsFromSource,
      },
      {
        id: 'material',
        titleKey: 'app.kuaizhizao.salesOrder.syncStep.material',
        getBinding: getMaterialSyncBinding,
        syncFromSource: (payload, onProgress) =>
          syncMaterialsFromSource({ ...payload, skip_prerequisite_syncs: true }, onProgress),
      },
    ],
    skipBackendPrerequisites: true,
    // 苍穹销售订单查询预置 code_suffix=sm_query（租户码如 sanyitest_sm_query）
    preferredApiCodeSuffixes: ['sm_query'],
    targetAliases: SALES_ORDER_SYNC_TARGET_ALIASES,
    mappingExportFileName: SALES_ORDER_SYNC_MAPPING_EXPORT_FILENAME,
    targetFields: SALES_ORDER_SYNC_TARGET_FIELDS,
    loadAvailableTargetFields: () => loadSyncCustomTargetFields(SALES_ORDER_SYNC_CUSTOM_FIELD_TABLE),
    customFieldTableName: SALES_ORDER_SYNC_CUSTOM_FIELD_TABLE,
    requiredTargets: SALES_ORDER_SYNC_REQUIRED_TARGETS,
    /**
     * 旧绑定曾把 order_date 与 delivery_date 都映到 bizdate，一对一保存后只剩交货日期。
     * 加载/校验时若缺订单日期且交货日期占着 bizdate，自动补回 order_date。
     */
    sanitizeMapping: (targetToSource) => {
      const next = { ...targetToSource };
      // 入站只按客户编码对齐，丢弃历史绑定里的 customer_id
      delete next.customer_id;
      if (!String(next.order_date || '').trim()) {
        const delivery = String(next.delivery_date || '').trim();
        if (/^(bizdate|fdate)$/i.test(delivery)) {
          next.order_date = delivery;
        }
      }
      return next;
    },
    validateMapping: (targetToSource, t: TFunction) => {
      for (const required of SALES_ORDER_SYNC_REQUIRED_TARGETS) {
        if (!targetToSource[required]) {
          const label = SALES_ORDER_SYNC_TARGET_FIELDS.find((field) => field.value === required)?.labelKey;
          return t('components.syncFromSource.mappingRequired', {
            field: label ? t(label) : required,
          });
        }
      }
      // 表头交期可选：有 delivery_date / 明细交期 / 仅订单日期（后端兜底）均可
      // 入站按客户编码比对；名称可作展示兜底，禁止只靠对方 customer_id
      if (!targetToSource.customer_code) {
        return t('components.syncFromSource.customerCodeMappingRequired');
      }
      if (!targetToSource['item.material_code'] || !targetToSource['item.required_quantity']) {
        return t('components.syncFromSource.itemMappingRequired');
      }
      return null;
    },
    getBinding: getSalesOrderSyncBinding,
    syncFromSource: syncSalesOrdersFromSource,
    completeSuccessKey: 'app.kuaizhizao.salesOrder.syncComplete',
    completePartialKey: 'app.kuaizhizao.salesOrder.syncPartial',
    failedKey: 'app.kuaizhizao.salesOrder.syncFailed',
    historySourceType: 'sales_order',
  };
}
