"""KU-AI S2 共享常量（目录/档案/授权语义钉死值）。

下游消费方（agent_assembler / model_factory / chat_service 路径 B）统一从这里取，
不要在各自模块里再写字面值。
"""

# 目录行与档案通用状态（KR-D8：status=启用 才参与装配/options）
STATUS_ENABLED = "启用"
STATUS_DISABLED = "停用"
CATALOG_STATUSES = frozenset({STATUS_ENABLED, STATUS_DISABLED})

# llm_models.model_type 闭集（KR-D5：chat|embed|vision|rerank）
MODEL_TYPES = frozenset({"chat", "embed", "vision", "rerank"})
MODEL_TYPE_CHAT = "chat"
MODEL_TYPE_EMBED = "embed"

# KR-D10 受控写 Tool 闭集：保存时校验，未知名 400；写 Tool 默认不勾
# spec 190：11 个存量 Tool 合并改名为 9 个（工单双视图并入
# query_work_orders，两个采购查询并入 query_purchase_orders），
# 不保留旧名运行时别名；存量档案 enabled_tools 由数据迁移改写
# spec 195 起按单元追加场景只读 Tool（manifest ai_tools 与其一一对应）
ENABLED_TOOL_NAMES = frozenset(
    {
        "search_knowledge",
        "query_work_orders",
        "submit_production_feedback",
        "update_workorder_status",
        "query_inventory",
        "analyze_delivery_risk",
        "query_purchase_orders",
        "query_schedule",
        "analyze_quality",
        # spec 195 销售订单与采购到货预警
        "query_sales_orders",
        "query_purchase_arrival_warnings",
        # spec 196 库存预警/补货建议/呆滞料
        "query_inventory_alerts",
        "query_replenishment_suggestions",
        "query_slow_moving_inventory",
        # spec 197 齐套分析与生产异常
        "analyze_kitting",
        "query_material_shortages",
        "query_delivery_delays",
        "query_quality_exceptions",
        # spec 198 一次合格率与缺陷帕累托
        "analyze_first_pass_yield",
        "analyze_defect_pareto",
        # spec 199 生产日报与异常信号
        "query_production_daily",
        "query_pulse_signals",
        # spec 200 工艺路线
        "query_process_routes",
        # spec 205 MRP 例外收件箱
        "query_mrp_exceptions",
        # spec 206 排程看板事实
        "query_scheduling_board",
        # spec 207 批次/序列追溯
        "trace_lineage",
        # spec 208 单据关联链与变更影响
        "trace_document_chain",
        "analyze_sales_order_change_impact",
        "analyze_purchase_order_change_impact",
        "analyze_demand_change_impact",
        # spec 209 检验单与供应商绩效
        "query_incoming_inspections",
        "query_process_inspections",
        "query_finished_inspections",
        "query_oqc_inspections",
        "query_supplier_evaluations",
        # spec 210 设备台账/故障维修/保养校准到期
        "query_equipment",
        "query_equipment_faults",
        "query_maintenance_plans",
        "query_maintenance_reminders",
        "query_calibration_alerts",
        # spec 211 设备 OEE 与损失分析
        "query_equipment_oee",
        "analyze_equipment_losses",
        # spec 212 ECN 影响分析（X4=a 拆 where-used 两个 Tool）
        "query_ecn",
        "analyze_ecn_impact",
        "query_material_where_used",
        "query_drawing_where_used",
        # spec 213 工程 BOM（工艺路线复用 spec 200 Tool）
        "query_engineering_bom",
        # spec 214 异常上报写 Tool（HITL，kind=write）
        "create_material_shortage_exception",
        "create_delivery_delay_exception",
        "create_quality_exception",
        # spec 215 客诉/8D 辅助
        "query_complaints",
        "query_8d_reports",
        # spec 216 模具寿命与工装状态
        "query_molds",
        "query_tooling",
        # spec 217 盘点差异解读
        "query_stocktakings",
        "analyze_stocktaking_variance",
        # spec 218 管理层日报/周报聚合简报
        "get_management_brief",
    }
)

# 场景预置档案只读 Tool 闭集（禁止包含写 Tool；预置档案
# enabled_tools 只能取这里面的值）。= ENABLED_TOOL_NAMES − 写 Tool
# {submit_production_feedback, update_workorder_status} +
# spec 214 三个 create_*_exception。
# spec 190 改名后曾钉死五值；spec 201 起 P1 模板纳入全部只读 Tool。
# spec 214 exception-report 模板 Y6=a 破例含写 Tool，由
# agent_scene_service.SceneTemplate.__post_init__ 单独放行。
SCENE_READONLY_TOOL_NAMES = ENABLED_TOOL_NAMES - frozenset(
    {
        "submit_production_feedback",
        "update_workorder_status",
        "create_material_shortage_exception",
        "create_delivery_delay_exception",
        "create_quality_exception",
    }
)

# KR-D9 授权模式（档案列，大写互斥）；grant 行 target_type 用小写 role|user
GRANT_MODE_ROLE = "ROLE"
GRANT_MODE_USER = "USER"
GRANT_MODES = frozenset({GRANT_MODE_ROLE, GRANT_MODE_USER})
GRANT_TARGET_TYPE_ROLE = "role"
GRANT_TARGET_TYPE_USER = "user"

# 知识检索片段拼接总长上限（字符）：search_knowledge Tool 返回与路径 A
# SystemMessage 注入同口径（S3 review m8），防超长塞爆上下文
KNOWLEDGE_RESULT_MAX_CHARS = 2000

# KR-D11 MCP 工具调用超时（秒）：mcp_client_service interceptor 层
# asyncio.wait_for 上限（AC5）
MCP_TOOL_TIMEOUT_SECONDS = 30

# KR-D8 租户默认档案：对齐 ktg-ai A31（``AiAgentProfileServiceImpl.DEFAULT_NAME``）。
# 仅按名称解析；不强制种子。若租户自行建同名档案，enabled_tools 约定仅
# ``search_knowledge``（种子非强制，本仓不自动插入）。
DEFAULT_AGENT_PROFILE_NAME = "默认助手"
