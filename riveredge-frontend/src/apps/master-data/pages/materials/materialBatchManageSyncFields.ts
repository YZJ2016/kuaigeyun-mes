import type { SyncTargetField } from '../../../../components/sync-from-source-modal/types';

/**
 * 库存信息 batchQuery 固定列：后端 helper 按 masterid.number + enablelot 解析。
 * 界面不必强制手填映射（与多单位「一点预览/别名即可」同体验）。
 */
export const MATERIAL_BATCH_MANAGE_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  {
    value: 'material_code',
    labelKey: 'app.master-data.materials.batchManageSyncField.materialCode',
  },
  {
    value: 'batch_managed',
    labelKey: 'app.master-data.materials.batchManageSyncField.batchManaged',
  },
];

/** 不设必填：选中库存信息接口后可由 sanitize 注入默认映射 */
export const MATERIAL_BATCH_MANAGE_SYNC_REQUIRED_TARGETS: string[] = [];

/** 苍穹物料库存信息 batchQuery 默认目标→来源（未手填时写入） */
export const MATERIAL_BATCH_MANAGE_DEFAULT_TARGET_TO_SOURCE: Record<string, string> = {
  material_code: 'masterid_number',
  batch_managed: 'enablelot',
};
