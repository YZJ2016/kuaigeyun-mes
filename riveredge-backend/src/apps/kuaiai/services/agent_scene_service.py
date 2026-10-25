"""KU-AI 租户场景实例服务（spec 181 / 201）

职责：
- 后端出厂场景模板（稳定 key / 卡片元数据 / 场景提示词 / 只读 Tool / 业务分类）；
- ``seed_kuaiai_agent_scenes_on_lifecycle``：install/enable/扫描同步幂等预置
  停用、空授权档案 + 绑定实例（缺几补几，同事务，失败全回滚，不写 grant）；
- 智能体库聚合视图：模板元数据 + 实例覆盖字段合并、总/单项开关、档案/使用权/
  chat 就绪计算状态与 disabled_reason、档案 ID 脱敏、路由白名单可用性；
- 实例定制/改绑/按需克隆（本租户校验 + 白名单 + 同事务原子提交）；
- ``guard_scene_agent_key``：chat 请求携带 ``extra.agent_key`` 时的场景守卫。

安全约定：模板 key / 插画 key / 业务路由 / 覆盖字段一律服务端闭集白名单；
所有查询带 tenant_id；跨租户/软删档案按不存在处理；生命周期种子行审计字段
写 ``created_by=0, created_by_name="系统"``，不冒名任一用户。
"""

from __future__ import annotations

import uuid as uuid_module
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger
from tortoise.transactions import in_transaction

from apps.kuaiai.constants import (
    GRANT_MODE_ROLE,
    SCENE_READONLY_TOOL_NAMES,
    STATUS_DISABLED,
    STATUS_ENABLED,
)
from apps.kuaiai.models.agent import KuaiaiAgentProfile
from apps.kuaiai.models.agent_scene import (
    SCENE_ORIGIN_COPY,
    SCENE_ORIGIN_SYSTEM_SEED,
    KuaiaiAgentScene,
)
from apps.kuaiai.schemas.agent import AgentProfileCreate
from apps.kuaiai.services import agent_service, grant_service
from infra.exceptions.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    NotFoundError,
    ValidationError,
)
from infra.models.user import User


# 场景业务分类闭集（spec 222 Z1=a）：模板按业务域分组，与 capability_tags
#（能力族标签 KU-Ask/KU-Pulse 等）不同轴；hub 分组渲染在 spec 222 落地。
SCENE_CATEGORIES: frozenset = frozenset(
    {
        "plan",
        "production",
        "quality",
        "inventory",
        "purchase",
        "equipment",
        "engineering",
        "management",
        "general",
    }
)

# spec 214 Y6=a：exception-report 场景模板破例允许的写 Tool 闭集
#（异常上报场景的全部价值即写 Tool，确认闸保证逐人确认，spec 193；
# 其余场景模板仍只能用 SCENE_READONLY_TOOL_NAMES）
_EXCEPTION_REPORT_WRITE_TOOLS = frozenset(
    {
        "create_material_shortage_exception",
        "create_delivery_delay_exception",
        "create_quality_exception",
    }
)


@dataclass(frozen=True)
class SceneTemplate:
    """后端出厂场景模板（不可变定义；key 稳定，实例可扩）。"""

    key: str
    name: str
    description: str
    image_key: str
    capability_tags: tuple
    sample_prompt: str
    scene_route: Optional[str]
    system_prompt: str
    readonly_tools: tuple
    category: str = "general"

    def __post_init__(self) -> None:
        if self.category not in SCENE_CATEGORIES:
            raise ValueError(f"场景模板 {self.key} 的 category 不在闭集内")
        allowed = SCENE_READONLY_TOOL_NAMES
        if self.key == "exception-report":
            # spec 214 Y6=a 破例：仅此模板 readonly_tools 允许含写 Tool
            allowed = allowed | _EXCEPTION_REPORT_WRITE_TOOLS
        unknown = set(self.readonly_tools) - allowed
        if unknown:
            raise ValueError(
                f"场景模板 {self.key} 的 readonly_tools 含非只读 Tool: "
                f"{sorted(unknown)}"
            )


# ============================================================ 出厂模板
# 只读 Tool / 业务路由 / 权限锚点逐一对照设计 §5.3 与当前业务 manifest，
# 路由不可用即 scene_available=false，不凭文案猜测。

SCENE_TEMPLATES: tuple = (
    SceneTemplate(
        key="inventory-insight",
        name="库存洞察助手",
        description="查询缺料与即时库存余额，支持跨仓检索",
        image_key="inventory-insight",
        capability_tags=("KU-Ask",),
        sample_prompt="查询缺料相关的物料即时库存",
        scene_route="/apps/kuaizhizao/warehouse-management/inventory",
        system_prompt=(
            "你是库存洞察助手，回答本租户即时库存、库存预警、补货建议与呆滞库存相关问题。"
            "库存事实一律来自 query_inventory、query_inventory_alerts、"
            "query_replenishment_suggestions、query_slow_moving_inventory "
            "工具返回的真实数据；查不到数据就如实说明，"
            "不要编造库存数量、仓位、批次或补货建议信息。"
        ),
        readonly_tools=(
            "query_inventory",
            "query_inventory_alerts",
            "query_replenishment_suggestions",
            "query_slow_moving_inventory",
        ),
        category="inventory",
    ),
    SceneTemplate(
        key="planner-advisor",
        name="计划员顾问",
        description="分析近期工单延期风险并给出处理顺序",
        image_key="planner-advisor",
        capability_tags=("KU-Ask", "KU-Pulse"),
        sample_prompt="分析近期工单延期风险并给出处理顺序",
        scene_route="/apps/kuaizhizao/production-execution/work-orders",
        system_prompt=(
            "你是计划员顾问，解读工单交期风险与排产冲突，给出可执行的处理顺序建议。"
            "工单与延期事实一律来自 query_work_orders、"
            "analyze_delivery_risk 工具返回的真实数据；查不到就如实说明，不要编造工单或日期。"
        ),
        readonly_tools=(
            "query_work_orders",
            "analyze_delivery_risk",
        ),
        category="plan",
    ),
    SceneTemplate(
        key="purchase-followup",
        name="采购跟单助手",
        description="跟进采购交期与供应商回复，汇总近期采购交期风险",
        image_key="purchase-followup",
        capability_tags=("KU-Draft", "KU-Act"),
        sample_prompt="汇总近期采购交期风险",
        scene_route="/apps/kuaizhizao/purchase-management/purchase-orders",
        system_prompt=(
            "你是采购跟单助手，汇总采购订单的交期与到货预警风险，辅助跟单说明。"
            "采购事实一律来自 query_purchase_orders、"
            "query_purchase_arrival_warnings 工具返回的真实数据；"
            "查不到就如实说明，不要编造订单、供应商或交期。"
        ),
        readonly_tools=(
            "query_purchase_orders",
            "query_purchase_arrival_warnings",
        ),
        category="purchase",
    ),
    SceneTemplate(
        key="schedule-explainer",
        name="排程解读助手",
        description="解释当前排程冲突与调整依据",
        image_key="schedule-explainer",
        capability_tags=("KU-Suggest",),
        sample_prompt="解释当前排程冲突与调整依据",
        scene_route="/apps/kuaizhizao/plan-management/rolling-scheduling",
        system_prompt=(
            "你是排程解读助手，解释已发布滚动排程的冲突与调整依据。"
            "排程事实一律来自 query_schedule 工具返回的真实数据；"
            "查不到已发布计划就如实说明，不要编造排程结果或产能数据。"
        ),
        readonly_tools=("query_schedule",),
        category="plan",
    ),
    SceneTemplate(
        key="quality-analysis",
        name="质量异常分析",
        description="汇总近期质量异常并分析可能原因",
        image_key="quality-analysis",
        capability_tags=("KU-Pulse", "KU-Know"),
        sample_prompt="汇总近期质量异常并分析可能原因",
        scene_route="/apps/kuaizhizao/production-execution/quality-exceptions",
        system_prompt=(
            "你是质量异常分析助手，汇总近期不合格检验记录与质量异常单，"
            "分析缺陷分布与一次合格率。"
            "质量事实一律来自 analyze_quality、query_quality_exceptions、"
            "analyze_first_pass_yield、analyze_defect_pareto 工具返回的真实数据；"
            "查不到异常就如实说明，不要编造不合格原因、检验数据或缺陷分布。"
        ),
        readonly_tools=(
            "analyze_quality",
            "query_quality_exceptions",
            "analyze_first_pass_yield",
            "analyze_defect_pareto",
        ),
        category="quality",
    ),
    SceneTemplate(
        key="supplier-collaboration",
        name="供应商协同 Agent",
        description="汇总待协同供应商事项，辅助跟进说明",
        image_key="supplier-collaboration",
        capability_tags=("KU-Act",),
        sample_prompt="汇总待协同供应商事项",
        scene_route="/apps/kuaizhizao/purchase-management/reports/supplier-delivery-summary",
        system_prompt=(
            "你是供应商协同助手，汇总指定供应商的采购订单与待协同事项，辅助跟进说明。"
            "供应商与订单事实一律来自 query_purchase_orders 工具返回的真实数据；"
            "查不到就如实说明，不要编造供应商或订单信息。"
        ),
        readonly_tools=("query_purchase_orders",),
        category="purchase",
    ),
    # ==================================================== spec 201 新增（P1）
    SceneTemplate(
        key="shift-lead",
        name="班组长助手",
        description="汇总开班生产日报、缺料异常与工单进度",
        image_key="shift-lead",
        capability_tags=("KU-Ask", "KU-Pulse"),
        sample_prompt="汇总昨天的生产日报与当前缺料异常",
        scene_route="/apps/kuaizhizao/production-execution/reports/production-daily",
        system_prompt=(
            "你是班组长助手，面向车间班组长汇总生产日报、工单进度与缺料等生产异常。"
            "事实一律来自 query_work_orders、analyze_kitting、"
            "query_material_shortages、query_production_daily、"
            "query_pulse_signals 工具返回的真实数据；"
            "查不到就如实说明，不要编造产量、工单状态或异常信息。"
        ),
        readonly_tools=(
            "query_work_orders",
            "analyze_kitting",
            "query_material_shortages",
            "query_production_daily",
            "query_pulse_signals",
        ),
        category="production",
    ),
    SceneTemplate(
        key="order-delivery",
        name="订单交期助手",
        description="答复销售订单交付进度，分析延期风险与齐套情况",
        image_key="order-delivery",
        capability_tags=("KU-Ask", "KU-Pulse"),
        sample_prompt="分析近期销售订单的交期风险",
        scene_route="/apps/kuaizhizao/sales-management/sales-orders",
        system_prompt=(
            "你是订单交期助手，答复销售订单的交付进度与延期风险。"
            "事实一律来自 query_sales_orders、query_work_orders、"
            "analyze_delivery_risk、analyze_kitting 工具返回的真实数据；"
            "查不到就如实说明，不要编造订单、工单或交期。"
        ),
        readonly_tools=(
            "query_sales_orders",
            "query_work_orders",
            "analyze_delivery_risk",
            "analyze_kitting",
        ),
        category="plan",
    ),
    SceneTemplate(
        key="work-instruction",
        name="作业指导助手",
        description="检索 SOP 与工艺路线，回答现场作业要求",
        image_key="work-instruction",
        capability_tags=("KU-Know",),
        sample_prompt="查询这张工单当前工序的作业要求",
        scene_route="/apps/master-data/process/sop",
        system_prompt=(
            "你是作业指导助手，回答现场作业的 SOP 与工艺要求问题。"
            "事实一律来自 search_knowledge、query_process_routes、"
            "query_work_orders 工具返回的真实数据；"
            "查不到 SOP 或工艺内容就如实说明，不要编造作业步骤或参数。"
        ),
        readonly_tools=(
            "search_knowledge",
            "query_process_routes",
            "query_work_orders",
        ),
        category="production",
    ),
    # ==================================================== spec 205-214 新增（P2）
    SceneTemplate(
        key="mrp-exceptions",
        name="MRP 例外助手",
        description="解读 MRP 例外收件箱，给出错误级例外的分组与处理顺序建议",
        image_key="mrp-exceptions",
        capability_tags=("KU-Ask", "KU-Pulse"),
        sample_prompt="最近一次 MRP 有哪些错误级例外，先处理哪些",
        scene_route="/apps/kuaizhizao/plan-management/demand-computation",
        system_prompt=(
            "你是 MRP 例外助手，解读需求计算产生的 MRP 例外并给出处理顺序建议。"
            "例外事实一律来自 query_mrp_exceptions 工具返回的真实数据；"
            "查不到就如实说明，不要编造例外、物料或计算结果。"
        ),
        readonly_tools=("query_mrp_exceptions",),
        category="plan",
    ),
    SceneTemplate(
        key="scheduling-board",
        name="排程看板解读助手",
        description="解读可视排产看板的冲突、未排产与缺配置事实，辅助调整",
        image_key="scheduling-board",
        capability_tags=("KU-Suggest",),
        sample_prompt="解释今天排程看板上的冲突与排不进来的工单",
        scene_route="/apps/kuaizhizao/plan-management/scheduling",
        system_prompt=(
            "你是排程看板解读助手，解释可视排产看板上的冲突、未排产工单、"
            "缺配置项与物料齐套问题，并给出可执行的调整方向。"
            "排程事实一律来自 query_scheduling_board 工具返回的真实数据；"
            "查不到就如实说明，不要编造工单、工位、冲突或产能数据；"
            "只给调整建议，不承诺已改排程。"
        ),
        readonly_tools=("query_scheduling_board",),
        category="plan",
    ),
    SceneTemplate(
        key="trace-lineage",
        name="批次追溯助手",
        description="按序列号/批号/工单号做正反向追溯，辅助评估召回范围",
        image_key="trace-lineage",
        capability_tags=("KU-Ask",),
        sample_prompt="批次 B2410-07 用在了哪些成品、发给了哪些客户",
        scene_route="/apps/kuaizhizao/quality-management/traceability",
        system_prompt=(
            "你是批次追溯助手，按序列号/批号/工单号解读正反向追溯链路，"
            "辅助质量工程师评估召回范围。"
            "追溯事实一律来自 trace_lineage 工具返回的真实数据；"
            "查不到就如实说明，不要编造批次、工单、客户或数量；"
            "召回范围由用户判断，你只罗列链路，不做召回或冻结建议。"
        ),
        readonly_tools=("trace_lineage",),
        category="quality",
    ),
    SceneTemplate(
        key="change-impact",
        name="变更影响助手",
        description="追溯单据关联链，分析需求/订单变更的下游影响范围",
        image_key="change-impact",
        capability_tags=("KU-Ask", "KU-Pulse"),
        sample_prompt="分析这张销售订单变更会影响哪些工单和采购单",
        scene_route="/apps/kuaizhizao/plan-management/demand-change",
        system_prompt=(
            "你是变更影响助手，追溯单据上下游关联链，分析销售订单/采购订单/需求"
            "变更对下游需求计算、工单、收货通知与入库单的影响。"
            "事实一律来自 trace_document_chain、analyze_sales_order_change_impact、"
            "analyze_purchase_order_change_impact、analyze_demand_change_impact "
            "工具返回的真实数据；查不到就如实说明，"
            "不要编造单据编号、关联关系或影响范围。"
        ),
        readonly_tools=(
            "trace_document_chain",
            "analyze_sales_order_change_impact",
            "analyze_purchase_order_change_impact",
            "analyze_demand_change_impact",
        ),
        category="plan",
    ),
    SceneTemplate(
        key="inspection-supplier",
        name="检验与供应商助手",
        description="查询来料/过程/成品/出货检验单与供应商评价绩效",
        image_key="inspection-supplier",
        capability_tags=("KU-Ask",),
        sample_prompt="供应商甲近一个月来料检验合格率怎样，不合格的是哪些批次",
        scene_route="/apps/kuaizhizao/quality-management/incoming-inspection",
        system_prompt=(
            "你是检验与供应商助手，回答来料、过程、成品与出货检验单查询，"
            "以及供应商评价得分与周期绩效问题。"
            "检验与评价事实一律来自 query_incoming_inspections、"
            "query_process_inspections、query_finished_inspections、"
            "query_oqc_inspections、query_supplier_evaluations "
            "工具返回的真实数据；查不到就如实说明，"
            "不要编造检验数量、结论、得分或供应商绩效信息。"
        ),
        readonly_tools=(
            "query_incoming_inspections",
            "query_process_inspections",
            "query_finished_inspections",
            "query_oqc_inspections",
            "query_supplier_evaluations",
        ),
        category="quality",
    ),
    SceneTemplate(
        key="equipment-ops",
        name="设备运维助手",
        description="答复设备台账、故障维修、保养到期与 OEE 损失分析",
        image_key="equipment-ops",
        capability_tags=("KU-Ask", "KU-Pulse"),
        sample_prompt="分析 3 号注塑机上月的 OEE 损失",
        scene_route="/apps/kuaizhizao/equipment-management/equipment",
        system_prompt=(
            "你是设备运维助手，答复设备台账、故障维修、保养/校准到期与 OEE 损失分析。"
            "事实一律来自 query_equipment、query_equipment_faults、"
            "query_maintenance_plans、query_maintenance_reminders、"
            "query_calibration_alerts、query_equipment_oee、"
            "analyze_equipment_losses 工具返回的真实数据；"
            "OEE 指标与损失工时以工具返回值为准，不要估算；"
            "查不到就如实说明，不要编造设备、故障或指标数据；"
            "故障原因推测须标注为推测并引用历史记录。"
        ),
        readonly_tools=(
            "query_equipment",
            "query_equipment_faults",
            "query_maintenance_plans",
            "query_maintenance_reminders",
            "query_calibration_alerts",
            "query_equipment_oee",
            "analyze_equipment_losses",
        ),
        category="equipment",
    ),
    SceneTemplate(
        key="ecn-impact",
        name="工程变更助手",
        description="查询 ECN 单及其对在制工单、库存批次、BOM/工艺引用的影响面",
        image_key="ecn-impact",
        capability_tags=("KU-Ask",),
        sample_prompt="ECN-2024-058 影响哪些在制工单和库存物料",
        scene_route="/apps/kuaiplm/change-management",
        system_prompt=(
            "你是工程变更助手，回答 ECN 变更单及其影响面相关问题。"
            "ECN 与影响事实一律来自 query_ecn、analyze_ecn_impact、"
            "query_material_where_used、query_drawing_where_used "
            "工具返回的真实数据；PLM 未启用或查不到数据就如实说明，"
            "不要编造变更内容、工单、批次或引用关系。"
        ),
        readonly_tools=(
            "query_ecn",
            "analyze_ecn_impact",
            "query_material_where_used",
            "query_drawing_where_used",
        ),
        category="engineering",
    ),
    SceneTemplate(
        key="bom-process",
        name="BOM 工艺助手",
        description="查询工程 BOM 层级、替代料组与物料工序参数",
        image_key="bom-process",
        capability_tags=("KU-Ask",),
        sample_prompt="产品 P-3301 的 BOM 有哪些层级和替代料",
        scene_route="/apps/master-data/process/engineering-bom",
        system_prompt=(
            "你是 BOM 工艺助手，回答工程 BOM 结构与工艺参数相关问题。"
            "BOM 结构、替代料与工序参数一律来自 query_engineering_bom、"
            "query_material_where_used、query_process_routes "
            "工具返回的真实数据；查不到物料或无替代关系就如实说明，"
            "不要编造用量、损耗率、层级或工艺参数。"
        ),
        readonly_tools=(
            "query_engineering_bom",
            "query_material_where_used",
            "query_process_routes",
        ),
        category="engineering",
    ),
    SceneTemplate(
        key="exception-report",
        name="异常上报助手",
        description="对话收集关键字段，确认后创建缺料/延期/质量异常单",
        image_key="exception-report",
        capability_tags=("KU-Act",),
        sample_prompt="WO-1023 缺料要停线了，帮我登记缺料异常",
        scene_route="/apps/kuaizhizao/production-execution/exception-process",
        system_prompt=(
            "你是异常上报助手，帮用户登记生产异常单。"
            "调用写 Tool 前先收齐关键字段：缺料异常须工单、物料与缺口数量；"
            "延期异常须工单与延期原因；质量异常须问题描述。"
            "severity/exception_type/alert_level 拿不准时追问用户，不要编造；"
            "提交前说明确认后将创建异常单。"
            "事实一律来自 create_material_shortage_exception、"
            "create_delivery_delay_exception、create_quality_exception "
            "工具返回的真实数据；工具报错或查不到数据就如实说明，不要编造单号或状态。"
        ),
        # Y6=a 破例：readonly_tools 字段填本单元三个写 Tool（__post_init__ 放行）；
        # 档案仍停用 + 空授权（Y4=a）
        readonly_tools=(
            "create_material_shortage_exception",
            "create_delivery_delay_exception",
            "create_quality_exception",
        ),
        category="production",
    ),
    # spec 215-218 P3 新增模板
    SceneTemplate(
        key="complaint-8d",
        name="客诉 8D 助手",
        description="查询质量投诉与 8D 报告进度，辅助起草 D0–D8 各段草稿",
        image_key="complaint-8d",
        capability_tags=("KU-Ask", "KU-Draft"),
        sample_prompt="投诉单 QC-2026-001 处理到哪步了，帮我起草 8D",
        scene_route="/apps/kuaizhizao/quality-management/eight-d-reports",
        system_prompt=(
            "你是客诉 8D 助手，查询质量投诉单与 8D 报告进度，辅助起草 8D 各阶段内容。"
            "事实一律来自 query_complaints、query_8d_reports 工具返回的真实数据；"
            "查不到就如实说明，不要编造单号、状态或阶段内容；"
            "起草的 8D 内容一律标注「草稿待人工确认，AI 生成」，只供复制到 8D 单，"
            "不直接创建或修改单据。"
        ),
        readonly_tools=(
            "query_complaints",
            "query_8d_reports",
        ),
        category="quality",
    ),
    SceneTemplate(
        key="mold-tooling",
        name="模具工装助手",
        description="答复模具寿命、模次与工装库位、领用状态",
        image_key="mold-tooling",
        capability_tags=("KU-Ask", "KU-Pulse"),
        sample_prompt="模具 M-078 打了多少模次，还能用多久",
        scene_route="/apps/kuaizhizao/equipment-management/molds",
        system_prompt=(
            "你是模具工装助手，答复模具寿命、模次、保养与工装库位、领用状态问题。"
            "事实一律来自 query_molds、query_tooling 工具返回的真实数据；"
            "寿命百分比与预警以工具返回值为准，不要估算；"
            "查不到就如实说明，不要编造模具、工装或寿命数据。"
        ),
        readonly_tools=(
            "query_molds",
            "query_tooling",
        ),
        category="equipment",
    ),
    SceneTemplate(
        key="stocktaking",
        name="盘点分析助手",
        description="解读盘点单差异构成与历史盘点差异趋势",
        image_key="stocktaking",
        capability_tags=("KU-Ask",),
        sample_prompt="这次盘点差异主要是哪些物料",
        scene_route="/apps/kuaizhizao/warehouse-management/stocktaking",
        system_prompt=(
            "你是盘点分析助手，解读盘点单差异构成与历史盘点趋势。"
            "事实一律来自 query_stocktakings、analyze_stocktaking_variance "
            "工具返回的真实数据；差异数值以工具返回为准，不要估算；"
            "查不到就如实说明，不要编造盘点单、差异或库位数据。"
        ),
        readonly_tools=(
            "query_stocktakings",
            "analyze_stocktaking_variance",
        ),
        category="inventory",
    ),
    SceneTemplate(
        key="management-brief",
        name="管理层助手",
        description="按日/周汇总生产、质量、设备、库存关键指标，输出分域简报",
        image_key="management-brief",
        capability_tags=("KU-Ask", "KU-Pulse"),
        sample_prompt="汇总昨天生产、质量、设备、库存的日报",
        scene_route="/apps/kuaizhizao/production-execution/reports/production-daily",
        system_prompt=(
            "你是管理层助手，为厂长/管理层汇总生产、质量、设备、库存关键指标，"
            "输出日报周报式分域简报。事实一律来自 get_management_brief、"
            "query_production_daily、analyze_first_pass_yield、"
            "query_equipment_oee、query_inventory_alerts、query_pulse_signals "
            "工具返回的真实数据；无权限、超时或查不到数据的小节如实说明数据不全，"
            "不要编造产量、合格率、OEE、异常或库存数字；只解读与建议，不发明指标。"
        ),
        readonly_tools=(
            "get_management_brief",
            "query_production_daily",
            "analyze_first_pass_yield",
            "query_equipment",
            "query_equipment_oee",
            "query_inventory",
            "query_inventory_alerts",
            "query_pulse_signals",
        ),
        category="management",
    ),
)

_TEMPLATE_MAP: Dict[str, SceneTemplate] = {t.key: t for t in SCENE_TEMPLATES}
_TEMPLATE_ORDER: Dict[str, int] = {t.key: i for i, t in enumerate(SCENE_TEMPLATES)}
TEMPLATE_KEYS: frozenset = frozenset(_TEMPLATE_MAP.keys())

# ============================================================ 服务端白名单
# 「查看场景」目标路由 → 页面读权限码。值取自当前业务 manifest 已注册菜单，
# 找不到/无权限即 scene_available=false；实例自定义路由也只能从这里选。

SCENE_ROUTE_PERMISSIONS: Dict[str, str] = {
    "/apps/kuaizhizao/warehouse-management/inventory": (
        "kuaizhizao:warehouse-management-inventory:read"
    ),
    "/apps/kuaizhizao/production-execution/work-orders": (
        "kuaizhizao:work-order:read"
    ),
    "/apps/kuaizhizao/purchase-management/purchase-orders": (
        "kuaizhizao:purchase-order:read"
    ),
    "/apps/kuaizhizao/plan-management/rolling-scheduling": (
        "kuaizhizao:plan-management-rolling-scheduling:read"
    ),
    "/apps/kuaizhizao/production-execution/quality-exceptions": (
        "kuaizhizao:production-execution-quality-exceptions:read"
    ),
    "/apps/kuaizhizao/warehouse-management/inventory-alert": (
        "kuaizhizao:warehouse-management-inventory-alert:read"
    ),
    "/apps/kuaizhizao/equipment-management/equipment-faults": (
        "kuaizhizao:equipment-fault:read"
    ),
    "/apps/kuaizhizao/purchase-management/reports/supplier-delivery-summary": (
        "kuaizhizao:purchase-management-reports-supplier-delivery-summary:read"
    ),
    # spec 201 新增模板场景路由（路径/权限码取自 kuaizhizao、master_data manifest）
    "/apps/kuaizhizao/production-execution/reports/production-daily": (
        "kuaizhizao:production-execution-reports-production-daily:read"
    ),
    "/apps/kuaizhizao/sales-management/sales-orders": (
        "kuaizhizao:sales-order:read"
    ),
    "/apps/master-data/process/sop": (
        "master-data:process:sop:read"
    ),
    # spec 205-214 新增模板场景路由（路径/权限码取自对应业务 manifest）
    "/apps/kuaizhizao/plan-management/demand-computation": (
        "kuaizhizao:plan-management-demand-computation:read"
    ),
    "/apps/kuaizhizao/plan-management/scheduling": (
        "kuaizhizao:plan-management-scheduling:read"
    ),
    "/apps/kuaizhizao/quality-management/traceability": (
        "kuaizhizao:quality-management-traceability:read"
    ),
    "/apps/kuaizhizao/plan-management/demand-change": (
        "kuaizhizao:plan-management-demand-change:read"
    ),
    "/apps/kuaizhizao/quality-management/incoming-inspection": (
        "kuaizhizao:quality-management-incoming-inspection:read"
    ),
    "/apps/kuaizhizao/equipment-management/equipment": (
        "kuaizhizao:equipment-management-equipment:read"
    ),
    "/apps/kuaiplm/change-management": "kuaiplm:change:read",
    "/apps/master-data/process/engineering-bom": (
        "master-data:process:engineering-bom:read"
    ),
    "/apps/kuaizhizao/production-execution/exception-process": (
        "kuaizhizao:production-execution-exception-process:read"
    ),
    # spec 215-218 新增模板场景路由（路径/权限码取自对应业务 manifest）
    "/apps/kuaizhizao/quality-management/eight-d-reports": (
        "kuaizhizao:quality-management-eight-d-reports:read"
    ),
    "/apps/kuaizhizao/equipment-management/molds": (
        "kuaizhizao:equipment-management-molds:read"
    ),
    "/apps/kuaizhizao/equipment-management/tool-ledger": (
        "kuaizhizao:equipment-management-tool-ledger:read"
    ),
    "/apps/kuaizhizao/warehouse-management/stocktaking": (
        "kuaizhizao:warehouse-management-stocktaking:read"
    ),
}

SCENE_IMAGE_KEYS: frozenset = frozenset(t.image_key for t in SCENE_TEMPLATES)

SCENE_CAPABILITY_TAGS: frozenset = frozenset(
    tag for t in SCENE_TEMPLATES for tag in t.capability_tags
)

# overrides JSON 允许写入的字段闭集（agent_profile_id/enabled 走实例列，不进 overrides）
SCENE_OVERRIDE_KEYS: frozenset = frozenset(
    {
        "name",
        "description",
        "image_key",
        "sample_prompt",
        "capability_tags",
        "scene_route",
        "category",
    }
)

_SEED_AUDIT = {
    "created_by": 0,
    "created_by_name": "系统",
    "updated_by": 0,
    "updated_by_name": "系统",
}

# ============================================================ 开关与就绪


def _audit_update(user: Optional[User]) -> Dict[str, Any]:
    if user is None or getattr(user, "id", None) is None:
        return {}
    name = getattr(user, "full_name", None) or getattr(user, "username", None)
    return {"updated_by": user.id, "updated_by_name": name}


async def _site_kuaiai_integration(
    tenant_id: int, *, fail_closed: bool = False
) -> Dict[str, Any]:
    """读取站点设置 integrations.kuaiai。

    默认失败返回空 dict（展示类调用方按「未配置」回落）；
    ``fail_closed=True``（开关守卫/卡片构建等放行判定路径）读取异常
    原样抛出，由调用方失败关闭——区分「键不存在→默认启用」与
    「读取异常→不得放行」（评审 minor-9）。
    """
    try:
        from core.services.system.site_setting_service import SiteSettingService
        from core.utils.integration_settings import get_kuaiai_integration

        site = await SiteSettingService.get_settings(tenant_id)
        return get_kuaiai_integration(site.settings or {})
    except Exception as exc:
        logger.warning(
            "读取站点 KU-AI 集成设置失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        if fail_closed:
            raise
        return {}


async def agent_switches(
    tenant_id: int, *, fail_closed: bool = False
) -> Dict[str, bool]:
    """模板总开关：``integrations.kuaiai.agent_switches``，缺键默认 True。

    ``fail_closed=True`` 时集成设置读取异常 → 全部模板视为停用
    （守卫拒绝/卡片 not_ready），与「键缺失默认启用」严格区分。
    """
    from core.utils.integration_settings import read_agent_switches

    try:
        kuaiai = await _site_kuaiai_integration(
            tenant_id, fail_closed=fail_closed
        )
    except Exception:
        # 守卫路径失败关闭：读不出开关不得按默认放行
        return {key: False for key in _TEMPLATE_MAP}
    return read_agent_switches(kuaiai, _TEMPLATE_MAP.keys())


async def _capabilities(tenant_id: int) -> Dict[str, Any]:
    """tools_enabled / rag_enabled 等站点能力开关（供 hub 能力矩阵）。"""
    kuaiai = await _site_kuaiai_integration(tenant_id)
    return kuaiai


async def is_chat_ready(tenant_id: int) -> bool:
    """chat 就绪只认当前应用连接运行时；目录行不是执行真源。"""
    try:
        from core.ai.runtime_config import AiRuntimeConfig

        status = await AiRuntimeConfig.public_status(tenant_id)
        return bool(status.get("configured") and status.get("enabled"))
    except Exception as exc:
        logger.warning(
            "chat 连接器就绪检查失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return False


async def _has_permission(user: Optional[User], tenant_id: int, code: str) -> bool:
    """当前用户权限判定：管理员身份由 has_permission 内部处理，失败关闭。"""
    uid = getattr(user, "id", None)
    if not uid or not tenant_id:
        return False
    try:
        from core.services.authorization.user_permission_service import (
            UserPermissionService,
        )

        return bool(
            await UserPermissionService.has_permission(uid, tenant_id, code)
        )
    except Exception as exc:
        logger.warning(
            "权限判定失败 tenant_id={} code={} error_type={}",
            tenant_id,
            code,
            type(exc).__name__,
        )
        return False


async def _require_permission(user: Optional[User], tenant_id: int, code: str) -> None:
    if not await _has_permission(user, tenant_id, code):
        raise AuthorizationError("权限不足")


# ============================================================ 生命周期种子


async def _unique_seed_profile_name(tenant_id: int, base: str) -> str:
    """种子档案名：模板中文名；重名追加（预置）及递增序号，绝不覆盖。"""
    name = base.strip()[:100]
    for suffix in ("", "（预置）") + tuple(f"（预置{i}）" for i in range(2, 50)):
        candidate = name if not suffix else f"{name[:100 - len(suffix)]}{suffix}"
        dup = await KuaiaiAgentProfile.get_or_none(
            tenant_id=tenant_id, name=candidate, deleted_at__isnull=True
        )
        if dup is None:
            return candidate
    raise BusinessLogicError(f"无法为预置档案 {base} 分配唯一名称")


async def _create_seed_profile(
    tenant_id: int, template: SceneTemplate
) -> KuaiaiAgentProfile:
    """按模板建档：停用 / grant_mode=ROLE / 空名单 / 空模型 / 只读 Tool。

    复用 agent_service.create_profile 的闭集/重名校验链；生命周期无用户
    上下文，审计字段按系统创建约定补写 created_by=0「系统」。
    """
    name = await _unique_seed_profile_name(tenant_id, template.name)
    payload = AgentProfileCreate(
        name=name,
        description=template.description,
        system_prompt=template.system_prompt,
        default_model_id=None,
        knowledge_ids=[],
        enabled_tools=list(template.readonly_tools),
        mcp_server_ids=[],
        status=STATUS_DISABLED,
        grant_mode=GRANT_MODE_ROLE,
    )
    profile = await agent_service.create_profile(tenant_id, None, payload)
    profile.created_by = 0
    profile.created_by_name = "系统"
    profile.updated_by = 0
    profile.updated_by_name = "系统"
    await profile.save(
        update_fields=[
            "created_by",
            "created_by_name",
            "updated_by",
            "updated_by_name",
        ]
    )
    return profile


async def seed_kuaiai_agent_scenes_on_lifecycle(tenant_id: int) -> Dict[str, Any]:
    """install/enable/扫描同步幂等预置：缺几补几，同事务提交。

    - 只为 instance_key=template_key 完全缺失的模板建档+建行；已存在实例
      （含手动解绑/改绑/停用/定制）与已软删痕迹一律尊重，不重建不覆盖；
    - 缺失组创建在同一 Tortoise 事务内提交，任一失败全部回滚，可安全重试；
    - 不写任何 grant 行、不启用档案；返回 created/complete 供调用方与
      provisioning 判定。
    """
    result = {"created": 0, "profiles": 0, "complete": False}
    if not tenant_id:
        return result

    existing_keys = set(
        await KuaiaiAgentScene.filter(
            tenant_id=tenant_id, instance_key__in=list(TEMPLATE_KEYS)
        ).values_list("instance_key", flat=True)
    )
    missing = [t for t in SCENE_TEMPLATES if t.key not in existing_keys]
    if not missing:
        result["complete"] = True
        return result

    async with in_transaction():
        for template in missing:
            # 事务内复核一次（并发 seed 下另一事务可能已建行）
            row = await KuaiaiAgentScene.get_or_none(
                tenant_id=tenant_id, instance_key=template.key
            )
            if row is not None:
                continue
            profile = await _create_seed_profile(tenant_id, template)
            await KuaiaiAgentScene.create(
                tenant_id=tenant_id,
                instance_key=template.key,
                template_key=template.key,
                origin=SCENE_ORIGIN_SYSTEM_SEED,
                agent_profile_id=profile.id,
                overrides={},
                enabled=True,
                **_SEED_AUDIT,
            )
            result["profiles"] += 1

    result["created"] = result["profiles"]
    remaining = await KuaiaiAgentScene.filter(
        tenant_id=tenant_id,
        instance_key__in=list(TEMPLATE_KEYS),
        deleted_at__isnull=True,
    ).count()
    result["complete"] = remaining == len(SCENE_TEMPLATES)
    logger.info(
        "KU-AI 场景预置完成 tenant_id={} created={} complete={}",
        tenant_id,
        result["created"],
        result["complete"],
    )
    return result


# ============================================================ 聚合视图


def _merged_fields(scene: Optional[KuaiaiAgentScene], template: SceneTemplate) -> Dict[str, Any]:
    """模板元数据 + overrides 白名单合并（未知覆盖键忽略）。"""
    overrides = (scene.overrides or {}) if scene is not None else {}
    if not isinstance(overrides, dict):
        overrides = {}
    out = {
        "name": template.name,
        "description": template.description,
        "image_key": template.image_key,
        "sample_prompt": template.sample_prompt,
        "capability_tags": list(template.capability_tags),
        "scene_route": template.scene_route,
        "category": template.category,
    }
    for key in SCENE_OVERRIDE_KEYS:
        value = overrides.get(key)
        if value is None:
            continue
        if key == "capability_tags":
            if isinstance(value, list) and all(
                str(v) in SCENE_CAPABILITY_TAGS for v in value
            ):
                out[key] = [str(v) for v in value]
            continue
        if key == "category":
            # spec 222：实例覆盖 category 也须落在闭集内，非法值回落模板值
            if isinstance(value, str) and value.strip() in SCENE_CATEGORIES:
                out[key] = value.strip()
            continue
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def _route_available(
    route: Optional[str], granted: Dict[str, bool]
) -> bool:
    """路由白名单内 + 当前用户持有页面读权限。"""
    if not route:
        return False
    permission = SCENE_ROUTE_PERMISSIONS.get(route)
    if not permission:
        return False
    return bool(granted.get(permission))


async def _route_permissions_for_user(
    tenant_id: int, user: Optional[User]
) -> Dict[str, bool]:
    """白名单内全部路由权限一次取回本地交集（替代逐条 has_permission 往返）。

    与 ``_has_permission`` 同一判定语义：管理员标志（DB 行复核）→ 全放行；
    其余按 ``get_user_permissions`` 多角色并集 ∩ 规范化权限码；任一环节
    异常失败关闭（全部 False）。
    """
    codes = list(dict.fromkeys(SCENE_ROUTE_PERMISSIONS.values()))
    out: Dict[str, bool] = {code: False for code in codes}
    uid = getattr(user, "id", None)
    if not uid or not tenant_id:
        return out
    try:
        from core.services.authorization.user_permission_service import (
            UserPermissionService,
        )

        db_user = await User.get_or_none(id=int(uid))
        if db_user is not None and (
            db_user.is_tenant_admin or db_user.is_infra_admin
        ):
            return {code: True for code in codes}
        granted = await UserPermissionService.get_user_permissions(
            int(uid), tenant_id
        )
        normalize = UserPermissionService._normalize_permission_code
        return {code: normalize(code) in granted for code in codes}
    except Exception as exc:
        logger.warning(
            "路由权限批量判定失败 tenant_id={} error_type={}",
            tenant_id,
            type(exc).__name__,
        )
        return out


async def _build_item(
    tenant_id: int,
    user: Optional[User],
    template: SceneTemplate,
    scene: Optional[KuaiaiAgentScene],
    *,
    switches: Dict[str, bool],
    usable_profile_ids: set,
    has_agent_read: bool,
    chat_ready: bool,
    route_grants: Dict[str, bool],
    profiles_by_id: Dict[int, KuaiaiAgentProfile],
) -> Dict[str, Any]:
    merged = _merged_fields(scene, template)
    route = merged["scene_route"]
    scene_available = _route_available(route, route_grants)

    if scene is None:
        # 预置缺失占位卡：明确 not_ready，可重试，不伪装已绑定
        return {
            "key": template.key,
            "template_key": template.key,
            "name": merged["name"],
            "description": merged["description"],
            "image_key": merged["image_key"],
            "enabled": False,
            "status": "not_ready",
            "capability_tags": merged["capability_tags"],
            "sample_prompt": merged["sample_prompt"],
            "agent_profile_id": None,
            "scene_route": route,
            "scene_available": scene_available,
            "disabled_reason": "场景预置未完成，请重新同步应用后重试",
            "category": merged["category"],
        }

    profile = profiles_by_id.get(scene.agent_profile_id)
    bound = profile is not None
    profile_enabled = bool(bound and profile.status == STATUS_ENABLED)
    has_use = bool(bound and int(profile.id) in usable_profile_ids)

    status = "ready"
    reason: Optional[str] = None
    if not switches.get(scene.template_key, True):
        status, reason = "not_ready", "场景总开关已停用"
    elif not scene.enabled:
        status, reason = "not_ready", "场景实例已停用"
    elif scene.agent_profile_id is None:
        status, reason = "not_ready", "未绑定 Agent 档案"
    elif not bound:
        status, reason = "not_ready", "绑定的 Agent 档案不存在或已删除"
    elif not profile_enabled:
        status, reason = "not_ready", "Agent 档案未启用"
    elif not chat_ready:
        status, reason = "partial", "未配置可用的对话模型连接"
    elif not has_use:
        status, reason = "partial", "当前用户无该 Agent 档案使用权"

    # 档案 ID 脱敏：无使用权且无管理读权限的用户不下发真实 id
    profile_id_out: Optional[int] = None
    if bound and (has_use or has_agent_read):
        profile_id_out = int(profile.id)

    return {
        "key": scene.instance_key,
        "template_key": scene.template_key,
        "name": merged["name"],
        "description": merged["description"],
        "image_key": merged["image_key"],
        "enabled": bool(scene.enabled),
        "status": status,
        "capability_tags": merged["capability_tags"],
        "sample_prompt": merged["sample_prompt"],
        "agent_profile_id": profile_id_out,
        "scene_route": route,
        "scene_available": scene_available,
        "disabled_reason": reason,
        "category": merged["category"],
    }


async def list_agent_library(tenant_id: int, user: Optional[User]) -> Dict[str, Any]:
    """智能体库聚合：预置项 + 租户复制项 + provisioning 状态。"""
    scenes = await KuaiaiAgentScene.filter(
        tenant_id=tenant_id, deleted_at__isnull=True
    ).order_by("id").all()
    scene_by_key = {s.instance_key: s for s in scenes}

    profile_ids = [s.agent_profile_id for s in scenes if s.agent_profile_id]
    profiles_by_id: Dict[int, KuaiaiAgentProfile] = {}
    if profile_ids:
        rows = await KuaiaiAgentProfile.filter(
            tenant_id=tenant_id,
            id__in=profile_ids,
            deleted_at__isnull=True,
        ).all()
        profiles_by_id = {p.id: p for p in rows}

    # 卡片构建属放行判定路径：开关读取异常失败关闭（全部 not_ready）
    switches = await agent_switches(tenant_id, fail_closed=True)
    usable = await grant_service.usable_profile_ids(tenant_id, user)
    has_agent_read = await _has_permission(user, tenant_id, "kuaiai:agent:read")
    chat_ready = await is_chat_ready(tenant_id)
    route_grants = await _route_permissions_for_user(tenant_id, user)

    common = dict(
        switches=switches,
        usable_profile_ids=usable,
        has_agent_read=has_agent_read,
        chat_ready=chat_ready,
        route_grants=route_grants,
        profiles_by_id=profiles_by_id,
    )

    items: List[Dict[str, Any]] = []
    for template in SCENE_TEMPLATES:
        scene = scene_by_key.get(template.key)
        items.append(
            await _build_item(tenant_id, user, template, scene, **common)
        )

    # 租户复制实例：非预置 instance_key，按创建顺序稳定排序
    copies = [s for s in scenes if s.instance_key not in TEMPLATE_KEYS]
    copies.sort(key=lambda s: (_TEMPLATE_ORDER.get(s.template_key, 999), s.id))
    for scene in copies:
        template = _TEMPLATE_MAP.get(scene.template_key)
        if template is None:
            # 孤儿复制项（模板已下线）：仍以最小模板视图返回，key/template_key 保留
            template = SceneTemplate(
                key=scene.template_key,
                name=scene.instance_key,
                description="",
                image_key="",
                capability_tags=(),
                sample_prompt="",
                scene_route=None,
                system_prompt="",
                readonly_tools=(),
            )
        items.append(
            await _build_item(tenant_id, user, template, scene, **common)
        )

    missing_keys = [t.key for t in SCENE_TEMPLATES if t.key not in scene_by_key]
    return {
        "provisioning": {
            "complete": not missing_keys,
            "missing_template_keys": missing_keys,
            "retryable": True,
        },
        "items": items,
    }


# ============================================================ 定制/改绑/克隆


def _validate_override_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """PUT/克隆的覆盖字段白名单校验：返回归一后的 overrides 增量。

    显式传 None 表示清除该覆盖（回落模板值）；未知键由 schema extra=forbid
    拦截，这里再做一层防御性白名单。
    """
    out: Dict[str, Any] = {}
    if "name" in data:
        value = data["name"]
        if value is not None:
            name = str(value).strip()
            if not name or len(name) > 100:
                raise BusinessLogicError("name 长度须为 1-100 字符")
            out["name"] = name
        else:
            out["name"] = None
    if "description" in data:
        value = data["description"]
        if value is not None:
            desc = str(value).strip()
            if len(desc) > 2000:
                raise BusinessLogicError("description 长度不得超过 2000")
            out["description"] = desc or None
        else:
            out["description"] = None
    if "image_key" in data:
        value = data["image_key"]
        if value is not None:
            key = str(value).strip()
            if key not in SCENE_IMAGE_KEYS:
                raise BusinessLogicError("image_key 不在已登记资源白名单")
            out["image_key"] = key
        else:
            out["image_key"] = None
    if "sample_prompt" in data:
        value = data["sample_prompt"]
        if value is not None:
            prompt = str(value).strip()
            if len(prompt) > 500:
                raise BusinessLogicError("sample_prompt 长度不得超过 500")
            out["sample_prompt"] = prompt or None
        else:
            out["sample_prompt"] = None
    if "capability_tags" in data:
        value = data["capability_tags"]
        if value is not None:
            if not isinstance(value, list):
                raise BusinessLogicError("capability_tags 必须为字符串列表")
            tags = [str(v).strip() for v in value if str(v).strip()]
            unknown = [t for t in tags if t not in SCENE_CAPABILITY_TAGS]
            if unknown:
                raise BusinessLogicError(
                    f"capability_tags 含未登记标签: {', '.join(unknown)}"
                )
            out["capability_tags"] = tags
        else:
            out["capability_tags"] = None
    if "scene_route" in data:
        value = data["scene_route"]
        if value is not None:
            route = str(value).strip()
            if route not in SCENE_ROUTE_PERMISSIONS:
                raise BusinessLogicError("scene_route 不在服务端路由白名单")
            out["scene_route"] = route
        else:
            out["scene_route"] = None
    if "category" in data:
        value = data["category"]
        if value is not None:
            cat = str(value).strip()
            if cat not in SCENE_CATEGORIES:
                raise BusinessLogicError("category 不在业务分类闭集")
            out["category"] = cat
        else:
            out["category"] = None
    return out


async def update_instance(
    tenant_id: int,
    user: Optional[User],
    instance_key: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """实例定制/改绑/单项开关：仅本租户实例，覆盖字段白名单，同事务写。"""
    key = (instance_key or "").strip()
    if not key or len(key) > 80:
        raise NotFoundError("场景实例", instance_key)
    scene = await KuaiaiAgentScene.get_or_none(
        tenant_id=tenant_id, instance_key=key, deleted_at__isnull=True
    )
    if scene is None and key in TEMPLATE_KEYS:
        # 预置实例缺失：先走幂等补齐，仍缺则显式报错（不造匿名虚拟实例）
        await seed_kuaiai_agent_scenes_on_lifecycle(tenant_id)
        scene = await KuaiaiAgentScene.get_or_none(
            tenant_id=tenant_id, instance_key=key, deleted_at__isnull=True
        )
    if scene is None:
        raise NotFoundError("场景实例", instance_key)

    profile: Optional[KuaiaiAgentProfile] = None
    if "agent_profile_id" in data:
        # 改绑需要档案管理读权限（路由层已校验 entry+display+manage）
        await _require_permission(user, tenant_id, "kuaiai:agent:read")
        pid = data["agent_profile_id"]
        if pid is not None:
            profile = await agent_service.get_profile(tenant_id, int(pid))

    override_patch = _validate_override_fields(data)

    async with in_transaction():
        locked = await KuaiaiAgentScene.filter(
            tenant_id=tenant_id, id=scene.id, deleted_at__isnull=True
        ).select_for_update().first()
        if locked is None:
            raise NotFoundError("场景实例", instance_key)
        if "agent_profile_id" in data:
            locked.agent_profile_id = profile.id if profile else None
        # enabled 显式 null 视为未传（不解绑语义不适用布尔开关，防止 null 误停用）
        if "enabled" in data and data["enabled"] is not None:
            locked.enabled = bool(data["enabled"])
        if override_patch:
            overrides = dict(locked.overrides or {})
            for field, value in override_patch.items():
                if value is None:
                    overrides.pop(field, None)
                else:
                    overrides[field] = value
            locked.overrides = overrides
        locked.update_from_dict(_audit_update(user))
        await locked.save()
        scene = locked

    view = await list_agent_library(tenant_id, user)
    for item in view["items"]:
        if item["key"] == scene.instance_key:
            return item
    raise NotFoundError("场景实例", instance_key)


async def _unique_clone_profile_name(tenant_id: int, source_name: str) -> str:
    """克隆档案名：源名截断 +（副本）后缀，冲突递增序号（仅名称重试）。"""
    base = source_name.strip()[:96]
    for i in range(1, 50):
        suffix = "（副本）" if i == 1 else f"（副本{i}）"
        candidate = f"{base[:100 - len(suffix)]}{suffix}"
        dup = await KuaiaiAgentProfile.get_or_none(
            tenant_id=tenant_id, name=candidate, deleted_at__isnull=True
        )
        if dup is None:
            return candidate
    raise BusinessLogicError("无法为克隆档案分配唯一名称")


async def _new_copy_instance_key(tenant_id: int, template_key: str) -> str:
    """复制实例 key：服务端生成，不与既有/软删 key 冲突。"""
    for _ in range(10):
        candidate = f"{template_key}-copy-{uuid_module.uuid4().hex[:8]}"
        exists = await KuaiaiAgentScene.filter(
            tenant_id=tenant_id, instance_key=candidate
        ).exists()
        if not exists:
            return candidate
    raise BusinessLogicError("无法为复制场景分配唯一 key")


async def clone_instance(
    tenant_id: int,
    user: User,
    template_key: str,
    source_agent_id: int,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按需克隆：本租户源档案 → 新停用无授权档案 + 复制实例（同事务原子）。

    - 源档案跨租户/不存在 → 404；不复制 grants/密钥/租户身份；
    - 源档案 default_model_id 存在时按本租户启用 chat 目录行复核后在事务内
      写入；复核失败整个克隆回滚（不静默复制/丢弃）；
    - 新实例 key 服务端生成，不触碰预置实例。
    """
    template = _TEMPLATE_MAP.get((template_key or "").strip())
    if template is None:
        raise ValidationError("未知场景模板 key")
    source = await agent_service.get_profile(tenant_id, int(source_agent_id))
    source_model_id = getattr(source, "default_model_id", None)

    override_values: Dict[str, Any] = {}
    if overrides:
        override_values = {
            k: v
            for k, v in _validate_override_fields(dict(overrides)).items()
            if v is not None
        }

    audit = {
        "created_by": user.id,
        "created_by_name": getattr(user, "full_name", None)
        or getattr(user, "username", None),
        "updated_by": user.id,
        "updated_by_name": getattr(user, "full_name", None)
        or getattr(user, "username", None),
    }

    async with in_transaction():
        if source_model_id is not None:
            # spec 181：default_model_id 沿用 agent_service 同租户 chat 模型复核，
            # 校验与档案写入同事务——非法（停用/删除/非 chat/跨租户）即整体回滚
            await agent_service._require_chat_model(
                tenant_id, int(source_model_id)
            )
        name = await _unique_clone_profile_name(tenant_id, source.name)
        payload = AgentProfileCreate(
            name=name,
            description=source.description,
            system_prompt=source.system_prompt,
            default_model_id=None,
            knowledge_ids=list(source.knowledge_ids or []),
            enabled_tools=list(source.enabled_tools or []),
            mcp_server_ids=list(source.mcp_server_ids or []),
            status=STATUS_DISABLED,
            grant_mode=(source.grant_mode or GRANT_MODE_ROLE),
        )
        profile = await agent_service.create_profile(tenant_id, user, payload)
        if source_model_id is not None:
            profile.default_model_id = int(source_model_id)
            await profile.save(update_fields=["default_model_id"])

        instance_key = await _new_copy_instance_key(tenant_id, template.key)
        scene = await KuaiaiAgentScene.create(
            tenant_id=tenant_id,
            instance_key=instance_key,
            template_key=template.key,
            origin=SCENE_ORIGIN_COPY,
            agent_profile_id=profile.id,
            overrides=override_values,
            enabled=True,
            **audit,
        )

    view = await list_agent_library(tenant_id, user)
    for item in view["items"]:
        if item["key"] == scene.instance_key:
            return item
    raise NotFoundError("场景实例", scene.instance_key)


# ============================================================ chat 场景守卫


async def guard_scene_agent_key(
    tenant_id: int,
    agent_key: str,
    agent_id: Optional[int],
    user: Optional[User],
) -> None:
    """``extra.agent_key`` 场景守卫（T9）：拒绝先于档案装配与落库。

    校验链：同租户实例存在 → 模板总开关 → 实例 enabled → 请求 agent_id
    与绑定一致 → 档案存在/启用 → 当前用户使用权 → chat 就绪。
    不携带 agent_key 的普通对话不进入本守卫。
    """
    key = (agent_key or "").strip()
    if not key:
        raise ValidationError("agent_key 不能为空")
    scene = await KuaiaiAgentScene.get_or_none(
        tenant_id=tenant_id, instance_key=key, deleted_at__isnull=True
    )
    if scene is None:
        raise NotFoundError("场景", key)

    # 守卫路径失败关闭：开关读取异常视为停用，不放行
    switches = await agent_switches(tenant_id, fail_closed=True)
    if not switches.get(scene.template_key, True):
        raise BusinessLogicError("该场景已被总开关停用")
    if not scene.enabled:
        raise BusinessLogicError("该场景实例已停用")
    if scene.agent_profile_id is None:
        raise BusinessLogicError("该场景未绑定 Agent 档案")
    if agent_id is None or int(agent_id) != int(scene.agent_profile_id):
        raise BusinessLogicError("agent_id 与场景绑定档案不一致")

    profile = await KuaiaiAgentProfile.get_or_none(
        tenant_id=tenant_id,
        id=scene.agent_profile_id,
        deleted_at__isnull=True,
    )
    if profile is None:
        raise NotFoundError("Agent 档案", str(scene.agent_profile_id))
    if profile.status != STATUS_ENABLED:
        raise AuthorizationError("该 Agent 档案已停用")
    if not await grant_service.check_use_grant(tenant_id, profile, user):
        raise AuthorizationError("无该 Agent 档案使用权")
    if not await is_chat_ready(tenant_id):
        raise BusinessLogicError("未配置可用的对话模型，请先完成 AI 连接器设置")
