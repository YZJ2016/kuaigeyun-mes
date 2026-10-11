/**
 * 智能体库场景插画（spec 181 T8；项目内原创 SVG，key 与后端
 * SCENE_IMAGE_KEYS 白名单一一对应，不得用 emoji/CSS 图形/空白占位）。
 *
 * 复制实例的 image_key 只能在白名单内；未知/空 key 回落默认插画。
 */

import inventoryInsight from './inventory-insight.svg';
import plannerAdvisor from './planner-advisor.svg';
import purchaseFollowup from './purchase-followup.svg';
import scheduleExplainer from './schedule-explainer.svg';
import qualityAnalysis from './quality-analysis.svg';
import supplierCollaboration from './supplier-collaboration.svg';
import defaultScene from './_default.svg';
import brandVisual from './brand-visual.svg';

/** 后端 image_key 白名单 → 插画资源（与 SCENE_IMAGE_KEYS 同步） */
export const SCENE_IMAGE_URLS: Record<string, string> = {
  'inventory-insight': inventoryInsight,
  'planner-advisor': plannerAdvisor,
  'purchase-followup': purchaseFollowup,
  'schedule-explainer': scheduleExplainer,
  'quality-analysis': qualityAnalysis,
  'supplier-collaboration': supplierCollaboration,
};

/** 管理表单可选插画 key（与服务端白名单同序） */
export const SCENE_IMAGE_KEYS = Object.keys(SCENE_IMAGE_URLS);

/** image_key → 资源 URL；未知/空 key 回落默认插画，绝不渲染空白 */
export function getSceneImageUrl(imageKey?: string | null): string {
  const key = String(imageKey || '').trim();
  return SCENE_IMAGE_URLS[key] ?? defaultScene;
}

/** hub 品牌视觉卡插画 */
export const HUB_BRAND_VISUAL_URL = brandVisual;
