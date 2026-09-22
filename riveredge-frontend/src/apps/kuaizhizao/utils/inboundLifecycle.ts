/**
 * 入库管理生命周期：以后端 lifecycle 为唯一真源（各入库类型阶段不同）。
 * stageDefs 仅作类型对齐；展示文案与主轴顺序来自 record.lifecycle.main_stages。
 * 禁止用单据 status 在前端拼装主轴（见 createLifecycleResolver）。
 */

import { createLifecycleResolver } from './createLifecycleResolver';

export const getInboundLifecycle = createLifecycleResolver({
  stageDefs: [
    { key: 'pending_inbound', label: '待入库' },
    { key: 'received', label: '已入库' },
    { key: 'draft', label: '草稿' },
    { key: 'confirmed', label: '已确认' },
    { key: 'completed', label: '已完成' },
    { key: 'pending_return', label: '待退料' },
    { key: 'returned', label: '已退料' },
    { key: 'pending_return_goods', label: '待退货' },
    { key: 'pending_material_return', label: '待归还' },
    { key: 'cancelled', label: '已取消' },
  ],
  statusToKey: {
    待入库: 'pending_inbound',
    已入库: 'received',
    草稿: 'draft',
    draft: 'draft',
    已确认: 'confirmed',
    已完成: 'completed',
    completed: 'completed',
    待退料: 'pending_return',
    已退料: 'returned',
    待退货: 'pending_return_goods',
    已退货: 'completed',
    待归还: 'pending_material_return',
    已归还: 'returned',
    已取消: 'cancelled',
    cancelled: 'cancelled',
  },
  exceptionKeys: ['cancelled'],
  exceptionStageKey: 'cancelled',
  nextStepSuggestionKeys: {},
  successKeys: ['received', 'completed', 'returned'],
});
