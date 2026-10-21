---
title: 生产领料 BOM 外物料
slug: non-bom-production-picking
status: delivered
domain: kuaizhizao-warehouse
when: 工单取单领料需手工加非 BOM 料、配置「生产领料允许 BOM 外物料」、确认防超发与 BOM 外行
keywords:
  - allow_non_bom_production_issue
  - skip_work_order_pick_limit_for_non_bom_extra
  - OutboundWorkOrderPullEntryPage
  - create_production_picking_from_work_order_pull
standard: 组织参数 parameters.warehouse.allow_non_bom_production_issue（默认 false）
---

# 生产领料 BOM 外物料

## 目标

组织开关开启后，从生产工单取单开领料时可手工添加主数据 BOM 外物料；创建/确认放行，仍拒倒冲/不发料。

## 何时读 / 禁止另起

- 何时读：改领料取单页加料、防超发确认、配置中心仓储参数。
- 禁止：在页面或 API 旁路硬开全租户；不要用补料单冒充 BOM 外手工加料（补料路径仍独立）。

## 标准入口

| 层 | 标准 |
|----|------|
| 配置 | `BusinessConfigService.get_allow_non_bom_production_issue`；`configTree` `warehouse.allow_non_bom_production_issue` |
| BE 创建 | `create_production_picking_from_work_order_pull`：`max_by_material` 无键 + 开关 → 主数据补全；`non_pick_bom_material_ids` 仍拒 |
| BE 确认 | `skip_work_order_pick_limit_for_non_bom_extra`（`picking_posting.py`） |
| FE | `OutboundWorkOrderPullEntryPage`：开关且非补料下推时「添加物料」；`isNonBomExtra` 行无待领上限 |

## 关键文件

| 角色 | 路径 |
|------|------|
| 参数 | `riveredge-backend/src/infra/services/business_config_service.py` |
| 领料服务 | `riveredge-backend/src/apps/kuaizhizao/services/warehouse_service.py` |
| 口径 | `riveredge-backend/src/apps/kuaizhizao/utils/picking_posting.py` |
| 取单页 | `riveredge-frontend/src/apps/kuaizhizao/pages/warehouse-management/outbound/OutboundWorkOrderPullEntryPage.tsx` |

## 扩展点

1. 新门禁须读同一开关，不得第二套 boolean。
2. 委外批量下推仍只选预览行；BOM 外仅取单录入页手工加。

## 踩坑

- 倒冲料在 kitting 中但不在 `max_by_material`：创建时必须用 `non_pick_bom_material_ids` 拦截，不能当 BOM 外放行。
- 确认时 `limit_map` 含 BOM 毛需求：仅 `allowed_bom==0` 且 `call_extra==0` 且开关开才跳过防超发。
