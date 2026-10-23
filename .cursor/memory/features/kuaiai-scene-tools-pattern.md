---
title: KU-AI 业务只读 Tool 模式（spec 195–200）
slug: kuaiai-scene-tools-pattern
status: delivered
domain: kuaiai
when: 新增/修改 KU-AI Tool、manifest ai_tools、SOP 知识同步或工艺路线 AI 查询
keywords:
  - kuaiai
  - Tool
  - ai_tools
  - ENABLED_TOOL_NAMES
  - sop_sync
  - query_process_routes
  - data scope
standard: Tool handler 放 apps/kuaiai/services/tools/<领域>.py；注册 constants.ENABLED_TOOL_NAMES + manifest ai_tools + 两份基线测试；只读、闭集参数、limit≤20、固定错误文案
---

# KU-AI 业务只读 Tool 模式（spec 195–200）

## 目标

AI 问答直接读「当前用户可见的真实单据」：sales/采购到货/库存预警/补货/呆滞料/齐套/生产异常/FPY/帕累托/日报/Pulse/工艺路线。

## 何时读 / 禁止另起

- 何时读：新增任何 `query_*`/`analyze_*` AI Tool，或改 Tool 权限/数据范围/输出格式
- 禁止：另写 Tool 注册路径（必须走 `core/ai/tool_registry.py` + `tool_bridge`）；在 Tool 里重写业务计算（必须复用 service/report 结果）；返回原始 service payload 不截断；把失败/未接入领域写成「无异常」

## 标准入口

| 层 | 标准 |
|----|------|
| handler | `apps/kuaiai/services/tools/<领域>.py`：`async def handler(..., ctx=None) -> str` |
| 注册 | `constants.ENABLED_TOOL_NAMES` + `manifest.json ai_tools`（label/kind=read/permission/handler/闭集参数） |
| 基线测试 | `test_s2_tools.py`（权限映射）、`test_spec190_tool_rename.py`（闭集）同步 +1 |
| 数据范围 | service 不接 current_user → `_scoped_row_ids(model, ctx, "<资源键>", ids)` 后置过滤；service 接受则直传 |
| 约定 | limit≤20（`_clamp_limit`）、闭集校验先于调用、空结果真实文案、异常固定中文文案、无敏感商业字段 |

## 关键文件

| 角色 | 路径 |
|------|------|
| Tool handlers | `riveredge-backend/src/apps/kuaiai/services/tools/`（sales_purchase/inventory_alerts/kitting_exceptions/quality_analytics/shift_brief/process_routes） |
| scope helpers | `apps/kuaiai/services/scene_tools.py`（`_scoped_row_ids`/`_apply_scope`/`_inventory_visible_pairs`） |
| SOP 同步 | `apps/kuaiai/services/sop_sync_service.py` + `core/tasks/ai_tasks.run_sop_knowledge_sync` + `sop_control_service._enqueue_sop_knowledge_sync` |
| S1 配置 | `core/utils/integration_settings.py`（read/validate_sop_sync）+ `settings_service` + FE `pages/settings` |
| 迁移 | `20261024120000_kuaiai_knowledge_document_source_ref.py`（source_ref 部分唯一索引） |

## 扩展点 / 踩坑

1. 新增 Tool：handler + ENABLED_TOOL_NAMES + manifest + 两份基线测试，缺一会被闭集测试挡住。
2. `request_parse` 是 AiJob 二次排队路径；已在 Taskiq worker 内的任务直接 `index_document`。
3. `run_pulse` 已实现 detector 仅 production/sales；未接入领域 `errors[].code=not_connected` 且不计 complete=false——Tool 必须透传。
4. `list_templates(ensure_seed=True)`、模板 seed 类接口会写库，只读 Tool 一律不触达。
5. SOP 同步幂等按 `(source_ref_type="sop", source_ref_id)` 定位；任务乱序以 SOP 当前 `control_status` 为准。
6. spec 197 K1-b：`compute_work_order_kitting_analysis` 为纯计算入口，原方法 = 计算 + 持久化；AI Tool 只调纯计算，不得动 `readiness_rate`。
