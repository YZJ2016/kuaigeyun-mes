/**
 * 工作小组绩效权重：相对比例，分配时按 权重/权重合计。
 * 不要求合计为 1；可填 1:1、2:3:5 等。
 */

/** 与库字段 Decimal(6,4) 对齐的单人上限（非业务比例约束） */
export const WORK_GROUP_PERFORMANCE_WEIGHT_MAX = 9999.9999;
