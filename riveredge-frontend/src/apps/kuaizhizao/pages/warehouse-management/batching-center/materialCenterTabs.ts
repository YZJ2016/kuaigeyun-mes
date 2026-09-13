/**
 * 物料中心 Tab 配置（线边备料 + 产线补料）
 */

import type { TFunction } from 'i18next';

/** 列表请求 / Tab 键；含历史拆分键以便 URL 映射与行级标签 */
export type BatchingTaskTabKey =
  | 'line_side_prep'
  | 'material_call'
  | 'batching_draft'
  | 'proactive_prep';

export type MaterialCenterTabKey = BatchingTaskTabKey;

export type MaterialCenterTabMeta = {
  key: MaterialCenterTabKey;
  label: string;
  hint: string;
};

/** 旧 URL ?tab= 映射到合并后的线边备料 */
export const LEGACY_MATERIAL_CENTER_TAB_ALIAS: Record<string, MaterialCenterTabKey> = {
  proactive_prep: 'line_side_prep',
  batching_draft: 'line_side_prep',
};

/** 已迁往委外管理模块的旧 Tab，用于深链重定向 */
export const LEGACY_OUTSOURCE_MATERIAL_CENTER_TABS: Record<string, string> = {
  outsource_issue: '/apps/kuaizhizao/outsource-management/outsource-issue',
  outsource_receipt: '/apps/kuaizhizao/outsource-management/outsource-receipt',
  outsource_material_return: '/apps/kuaizhizao/outsource-management/outsource-material-return',
  outsource_product_return: '/apps/kuaizhizao/outsource-management/outsource-product-return',
};

export function resolveMaterialCenterTabKey(raw: string | null | undefined): MaterialCenterTabKey | null {
  if (!raw) return null;
  if (raw in LEGACY_MATERIAL_CENTER_TAB_ALIAS) {
    return LEGACY_MATERIAL_CENTER_TAB_ALIAS[raw];
  }
  return null;
}

export function resolveLegacyOutsourceMaterialCenterPath(raw: string | null | undefined): string | null {
  if (!raw) return null;
  return LEGACY_OUTSOURCE_MATERIAL_CENTER_TABS[raw] ?? null;
}

export function getMaterialCenterTabs(t: TFunction): MaterialCenterTabMeta[] {
  return [
    {
      key: 'line_side_prep',
      label: t('app.kuaizhizao.batchingCenter.tab.lineSidePrep'),
      hint: t('app.kuaizhizao.batchingCenter.tab.lineSidePrepHint'),
    },
    {
      key: 'material_call',
      label: t('app.kuaizhizao.batchingCenter.tab.materialCall'),
      hint: t('app.kuaizhizao.batchingCenter.tab.materialCallHint'),
    },
  ];
}

/** 行级 task_type 展示文案（含合并列表内的建议/备料单） */
export function getBatchingTaskTypeLabel(t: TFunction): Record<
  Exclude<BatchingTaskTabKey, 'line_side_prep'>,
  string
> {
  return {
    batching_draft: t('app.kuaizhizao.batchingCenter.taskType.batchingDraft'),
    material_call: t('app.kuaizhizao.batchingCenter.taskType.materialCall'),
    proactive_prep: t('app.kuaizhizao.batchingCenter.taskType.proactivePrep'),
  };
}

/** @deprecated 使用 getBatchingTaskTypeLabel(t) */
export const BATCHING_TASK_TYPE_LABEL: Record<Exclude<BatchingTaskTabKey, 'line_side_prep'>, string> = {
  batching_draft: '',
  material_call: '',
  proactive_prep: '',
};

export const DEFAULT_MATERIAL_CENTER_TAB: MaterialCenterTabKey = 'line_side_prep';

/** @deprecated 使用 DEFAULT_MATERIAL_CENTER_TAB */
export const DEFAULT_BATCHING_CENTER_TAB = DEFAULT_MATERIAL_CENTER_TAB as BatchingTaskTabKey;

export function isBatchingTaskTab(key: MaterialCenterTabKey): key is 'material_call' {
  return key === 'material_call';
}
