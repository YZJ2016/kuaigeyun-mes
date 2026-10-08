/**
 * 快格轻制造服务入口
 */

export * from './production';
export * from './sales';
export * from './quality';
export * from './reports';
export * from './common';
export * from './purchase';
export type { ActionCapability } from './purchase';
export * from './equipment';

// 导出各个API模块
export {
  workOrderApi,
  reportingApi,
  warehouseApi,
  qualityApi,
  financeApi,
} from './production';

export {
  equipmentApi,
  maintenancePlanApi,
  equipmentFaultApi,
  moldApi,
} from './equipment';

