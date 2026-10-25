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
import shiftLead from './shift-lead.svg';
import orderDelivery from './order-delivery.svg';
import workInstruction from './work-instruction.svg';
import mrpExceptions from './mrp-exceptions.svg';
import schedulingBoard from './scheduling-board.svg';
import traceLineage from './trace-lineage.svg';
import changeImpact from './change-impact.svg';
import inspectionSupplier from './inspection-supplier.svg';
import equipmentOps from './equipment-ops.svg';
import ecnImpact from './ecn-impact.svg';
import bomProcess from './bom-process.svg';
import exceptionReport from './exception-report.svg';
import complaint8d from './complaint-8d.svg';
import moldTooling from './mold-tooling.svg';
import stocktaking from './stocktaking.svg';
import managementBrief from './management-brief.svg';
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
  'shift-lead': shiftLead,
  'order-delivery': orderDelivery,
  'work-instruction': workInstruction,
  'mrp-exceptions': mrpExceptions,
  'scheduling-board': schedulingBoard,
  'trace-lineage': traceLineage,
  'change-impact': changeImpact,
  'inspection-supplier': inspectionSupplier,
  'equipment-ops': equipmentOps,
  'ecn-impact': ecnImpact,
  'bom-process': bomProcess,
  'exception-report': exceptionReport,
  'complaint-8d': complaint8d,
  'mold-tooling': moldTooling,
  'stocktaking': stocktaking,
  'management-brief': managementBrief,
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
