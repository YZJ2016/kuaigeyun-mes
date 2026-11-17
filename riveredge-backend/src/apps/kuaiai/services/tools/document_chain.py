"""KU-AI 场景只读 Tool：单据关联链追溯与变更影响分析（spec 208，S05）。

Tool 名：``trace_document_chain`` / ``analyze_sales_order_change_impact`` /
``analyze_purchase_order_change_impact`` / ``analyze_demand_change_impact``。

- 底层统一走 ``DocumentRelationNewService``：
  ``trace_document_chain`` / ``get_change_impact_sales_order`` /
  ``get_change_impact_purchase_order`` / ``get_change_impact_demand``
  （与页面 ``GET /document-relations/{type}/{id}/trace`` 及
  ``/{sales_order_id|demand_id}/change-impact`` 接口同数据源）。
- X3=a（spec §1 已选定）：关联链跨模块不原样返回——
  ``trace_document_chain`` 先按 ``_DOC_TYPE_READ_PERMISSION``
  （单据类型 → 读权限码映射表，只存本适配层；取值核对自 kuaizhizao /
  kuaicaiwu manifest ``permissions`` 与
  ``api/_kuaizhizao_route_access.py`` 的 URL→模块映射）判源单类型读权限，
  再对链上每个节点按其单据类型读权限过滤；无权节点只显示计数、不显示
  编号与内容；映射缺项一律按无权处理（失败关闭）。节点判权 = 一次
  ``get_user_permissions`` 取权限码集合后内存判定（同一请求内每个权限码
  只判定一次，不逐节点查库），与 tool_bridge 对 UserPermissionService
  的用法口径一致。
- 源单行级数据范围（spec §1）：销售订单 / 采购订单 / 需求源单 by-ID 先经
  ``scene_tools._scoped_row_ids`` 按对应 service 的 current_user 资源键
  复核（``kuaizhizao:sales-order`` / ``kuaizhizao:purchase-order``；
  需求单 T1 定 ``kuaizhizao:plan-management-demand-management``，与
  ``/demands`` 路由 ``require_kuaizhizao_module_access`` 模块一致），
  范围外按不存在回复。其余单据类型无已登记行级范围口径，由读权限码门控。
- 变更影响 Tool 的受影响条目同样按节点类型读权限过滤，无权条目只计数；
  输出只含单号 / 类型 / 状态 / 影响关系，不落金额等敏感字段。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# direction 闭集（与 DocumentRelationNewService.trace_document_chain 一致）
_TRACE_DIRECTIONS = frozenset({"upstream", "downstream", "both"})

# document_type 闭集（spec §2 T1：与 DocumentRelationService.DOCUMENT_TYPES
# 的 57 种已登记单据类型一致；purchase_requisition 无业务推导策略，但表驱动
# 关联仍可追溯，故保留在闭集内。测试断言两侧集合一致防漂移）
_TRACE_DOCUMENT_TYPES = frozenset(
    {
        "demand",
        "sales_forecast",
        "sales_order",
        "quotation",
        "sales_contract",
        "delivery_project",
        "material_borrow",
        "material_return",
        "demand_computation",
        "work_order",
        "production_picking",
        "production_return",
        "reporting_record",
        "finished_goods_receipt",
        "semi_finished_goods_receipt",
        "sales_delivery",
        "delivery_notice",
        "purchase_order",
        "purchase_requisition",
        "purchase_inquiry",
        "purchase_receipt",
        "purchase_return",
        "payable",
        "receivable",
        "sales_invoice",
        "receipt",
        "payment",
        "purchase_invoice",
        "incoming_inspection",
        "process_inspection",
        "finished_goods_inspection",
        "outsource_order",
        "outsource_work_order",
        "packing_binding",
        "receipt_notice",
        "other_inbound",
        "stocktaking",
        "inventory_transfer",
        "freight_order",
        "after_sales_ticket",
        "install_execution",
        "service_asset",
        "repair_order",
        "service_dispatch",
        "spare_part_requisition",
        "service_settlement",
        "customer_return_visit",
        "sales_return",
        "shipment_notice",
        "equipment",
        "equipment_fault",
        "maintenance_plan",
        "maintenance_reminder",
        "mold",
        "tool",
        "performance_skill",
        "performance_holiday",
        "performance_summary",
    }
)

# 单据类型 → 读权限码映射表（X3=a 节点过滤唯一依据）。
# 取值核对：kuaizhizao manifest permissions + api/_kuaizhizao_route_access.py
# （_PRODUCTIONS_PATH_MODULES / _WAREHOUSE_EXECUTION_PATH_MODULES /
# 各路由 require_kuaizhizao_module_access 模块码）+ kuaicaiwu manifest
# （财务单据归属快财务应用）+ master_data/api/_performance_route_access.py
# （绩效权限码托管于 kuaizhizao manifest）。未登记类型 / 表中缺项按无权处理。
_DOC_TYPE_READ_PERMISSION: Dict[str, str] = {
    "demand": "kuaizhizao:plan-management-demand-management:read",
    "sales_forecast": "kuaizhizao:sales-forecast:read",
    "sales_order": "kuaizhizao:sales-order:read",
    "quotation": "kuaizhizao:quotation:read",
    "sales_contract": "kuaizhizao:sales-contract:read",
    "delivery_project": "kuaizhizao:delivery-project:read",
    "material_borrow": "kuaizhizao:material-borrow:read",
    "material_return": "kuaizhizao:material-return:read",
    "demand_computation": "kuaizhizao:plan-management-demand-computation:read",
    "work_order": "kuaizhizao:work-order:read",
    # 生产领料/退料/入库与采购入库页面统一挂 inbound 模块
    # （_WAREHOUSE_EXECUTION_PATH_MODULES）
    "production_picking": "kuaizhizao:inbound:read",
    "production_return": "kuaizhizao:inbound:read",
    "reporting_record": "kuaizhizao:production-execution-reporting:read",
    # 合并节点：工单下多条报工的合成时间线，权限随报工
    "reporting_timeline": "kuaizhizao:production-execution-reporting:read",
    "finished_goods_receipt": "kuaizhizao:inbound:read",
    "semi_finished_goods_receipt": "kuaizhizao:inbound:read",
    "sales_delivery": "kuaizhizao:outbound:read",
    "delivery_notice": "kuaizhizao:delivery-notice:read",
    "purchase_order": "kuaizhizao:purchase-order:read",
    "purchase_requisition": "kuaizhizao:purchase-requisition:read",
    "purchase_inquiry": "kuaizhizao:purchase-inquiry:read",
    "purchase_receipt": "kuaizhizao:inbound:read",
    "purchase_return": "kuaizhizao:purchase-return:read",
    # 财务单据归属 kuaicaiwu 应用 manifest
    "payable": "kuaicaiwu:payable:read",
    "receivable": "kuaicaiwu:receivable:read",
    "sales_invoice": "kuaicaiwu:sales-invoice:read",
    "receipt": "kuaicaiwu:receipt:read",
    "payment": "kuaicaiwu:payment:read",
    "purchase_invoice": "kuaicaiwu:purchase-invoice:read",
    "incoming_inspection": "kuaizhizao:quality-management-incoming-inspection:read",
    "process_inspection": "kuaizhizao:quality-management-process-inspection:read",
    "finished_goods_inspection": (
        "kuaizhizao:quality-management-finished-goods-inspection:read"
    ),
    "outsource_order": "kuaizhizao:outsource-order:read",
    "outsource_work_order": "kuaizhizao:outsource-work-order:read",
    "packing_binding": "kuaizhizao:production-execution-packing-binding:read",
    "receipt_notice": "kuaizhizao:receipt-notice:read",
    "other_inbound": "kuaizhizao:other-inbound:read",
    "stocktaking": "kuaizhizao:warehouse-management-stocktaking:read",
    "inventory_transfer": "kuaizhizao:warehouse-management-inventory-transfer:read",
    "freight_order": "kuaizhizao:freight-order:read",
    "after_sales_ticket": "kuaizhizao:after-sales-ticket:read",
    "install_execution": "kuaizhizao:after-sales-install:read",
    "service_asset": "kuaizhizao:service-asset:read",
    "repair_order": "kuaizhizao:repair-order:read",
    "service_dispatch": "kuaizhizao:service-dispatch:read",
    "spare_part_requisition": "kuaizhizao:after-sales-spare-part-requisition:read",
    "service_settlement": "kuaizhizao:service-settlement:read",
    "customer_return_visit": "kuaizhizao:customer-return-visit:read",
    "sales_return": "kuaizhizao:sales-return:read",
    "shipment_notice": "kuaizhizao:shipment-notice:read",
    "equipment": "kuaizhizao:equipment-management-equipment:read",
    "equipment_fault": "kuaizhizao:equipment-fault:read",
    "maintenance_plan": "kuaizhizao:maintenance-plan:read",
    "maintenance_reminder": "kuaizhizao:maintenance-reminder:read",
    "mold": "kuaizhizao:equipment-management-molds:read",
    "tool": "kuaizhizao:equipment-management-tool-ledger:read",
    "performance_skill": "kuaizhizao:performance-skills:read",
    "performance_holiday": "kuaizhizao:performance-holidays:read",
    "performance_summary": "kuaizhizao:performance-summaries:read",
}

# 单据类型中文标签（输出可读；缺项回落原始类型串）
_DOC_TYPE_ZH: Dict[str, str] = {
    "demand": "需求",
    "sales_forecast": "销售预测",
    "sales_order": "销售订单",
    "quotation": "报价单",
    "sales_contract": "销售合同",
    "delivery_project": "交付项目",
    "material_borrow": "借料单",
    "material_return": "退料单",
    "demand_computation": "需求计算",
    "work_order": "工单",
    "production_picking": "生产领料单",
    "production_return": "生产退料单",
    "reporting_record": "报工记录",
    "reporting_timeline": "报工汇总",
    "finished_goods_receipt": "成品入库单",
    "semi_finished_goods_receipt": "半成品入库单",
    "sales_delivery": "销售出库单",
    "delivery_notice": "送货通知单",
    "purchase_order": "采购订单",
    "purchase_requisition": "采购申请",
    "purchase_receipt": "采购入库单",
    "purchase_return": "采购退货单",
    "payable": "应付单",
    "receivable": "应收单",
    "sales_invoice": "销售发票",
    "receipt": "收款单",
    "payment": "付款单",
    "purchase_invoice": "采购发票",
    "incoming_inspection": "来料检验单",
    "process_inspection": "过程检验单",
    "finished_goods_inspection": "成品检验单",
    "outsource_order": "委外单",
    "outsource_work_order": "委外工单",
    "packing_binding": "装箱绑定",
    "receipt_notice": "收货通知单",
    "other_inbound": "其他入库单",
    "stocktaking": "盘点单",
    "inventory_transfer": "调拨单",
    "freight_order": "货运单",
    "after_sales_ticket": "售后工单",
    "install_execution": "安装执行单",
    "service_asset": "服务资产",
    "repair_order": "维修单",
    "service_dispatch": "服务派工单",
    "spare_part_requisition": "备件申领单",
    "service_settlement": "服务结算单",
    "customer_return_visit": "客户回访单",
    "sales_return": "销售退货单",
    "shipment_notice": "发货通知单",
    "equipment": "设备",
    "equipment_fault": "设备故障单",
    "maintenance_plan": "保养计划",
    "maintenance_reminder": "保养提醒",
    "mold": "模具",
    "tool": "工装刀具",
    "performance_skill": "技能",
    "performance_holiday": "节假日",
    "performance_summary": "绩效汇总",
}

# 变更影响输出分节：列表键 →（中文节名，条目过滤读权限码）。
# affected_plans 当前恒为空（service 未填），仍按排程模块读权限过滤（失败关闭）。
_IMPACT_SECTIONS: Dict[str, Tuple[str, str]] = {
    "affected_demands": (
        "受影响需求",
        "kuaizhizao:plan-management-demand-management:read",
    ),
    "affected_computations": (
        "受影响需求计算",
        "kuaizhizao:plan-management-demand-computation:read",
    ),
    "affected_plans": (
        "受影响生产计划",
        "kuaizhizao:plan-management-scheduling:read",
    ),
    "affected_work_orders": (
        "受影响工单",
        "kuaizhizao:work-order:read",
    ),
    "affected_receipt_notices": (
        "受影响收货通知单",
        "kuaizhizao:receipt-notice:read",
    ),
    "affected_inbounds": (
        "受影响入库单",
        "kuaizhizao:inbound:read",
    ),
}

_SALES_DEMAND_IMPACT_KEYS = (
    "affected_demands",
    "affected_computations",
    "affected_plans",
    "affected_work_orders",
)
_PURCHASE_IMPACT_KEYS = ("affected_receipt_notices", "affected_inbounds")

# 每个方向最多展开的节点行数（有界摘要）；每类受影响单据最多展开条数
_TRACE_LINE_MAX = 40
_IMPACT_ITEM_MAX = 20
_TRACE_DEPTH_MAX = 10


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _type_zh(document_type: str) -> str:
    return _DOC_TYPE_ZH.get(document_type) or str(document_type)


async def _perm_view(ctx: AiRuntimeContext) -> Tuple[bool, frozenset]:
    """(admin_bypass, 已授权限码集合)。

    同一请求一次加载：管理员走 ctx 标志位（与 tool_bridge 一致）；其余用户
    一次 ``get_user_permissions`` 取并集，节点判权全部内存完成，不逐节点查库。
    """
    if getattr(ctx, "is_infra_admin", False) or getattr(
        ctx, "is_tenant_admin", False
    ):
        return True, frozenset()
    from core.services.authorization.user_permission_service import (
        UserPermissionService,
    )

    try:
        codes = await UserPermissionService.get_user_permissions(
            int(ctx.user.id), ctx.tenant_id
        )
    except Exception as exc:
        # 失败关闭：权限集解析失败一律按无权处理（spec 217 审计项）
        logger.warning(
            "AI tool 权限集解析失败 error_type={}", type(exc).__name__
        )
        return False, frozenset()
    return False, frozenset(codes or ())


def _code_allowed(permission: Optional[str], admin: bool, codes: frozenset) -> bool:
    """权限码判定：映射缺项返回 False（失败关闭）。"""
    if not permission:
        return False
    if admin:
        return True
    return permission.strip().lower() in codes


def _doc_type_allowed(document_type: str, admin: bool, codes: frozenset) -> bool:
    return _code_allowed(
        _DOC_TYPE_READ_PERMISSION.get(str(document_type or "")), admin, codes
    )


def _source_scope(document_type: str):
    """源单行级范围资源（model, 资源键）；未登记类型返回 (None, None)。"""
    if document_type == "sales_order":
        from apps.kuaizhizao.models.sales_order import SalesOrder

        return SalesOrder, "kuaizhizao:sales-order"
    if document_type == "purchase_order":
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder

        return PurchaseOrder, "kuaizhizao:purchase-order"
    if document_type == "demand":
        from apps.kuaizhizao.models.demand import Demand

        return Demand, "kuaizhizao:plan-management-demand-management"
    return None, None


async def _source_doc_visible(
    ctx: AiRuntimeContext, document_type: str, document_id: int
) -> bool:
    """源单 by-ID 行级数据范围复核（spec §1）。

    与对应 service 的 current_user 列表范围同资源键；范围外返回 False，
    调用方按不存在回复。未登记类型不做行级裁剪（由读权限码门控）。
    """
    model, resource = _source_scope(document_type)
    if model is None:
        return True
    try:
        visible = await _st()._scoped_row_ids(
            model, ctx, resource, {int(document_id)}
        )
    except Exception as exc:
        logger.warning(
            "AI tool 单据范围复核失败 type={} error_type={}",
            document_type,
            type(exc).__name__,
        )
        return False
    return int(document_id) in visible


def _count_subtree(node: Any) -> int:
    """节点含自身与子树的节点总数（无权节点整块只计数）。"""
    return 1 + sum(_count_subtree(c) for c in (node.children or []))


def _node_line(node: Any, depth: int) -> str:
    zh = _type_zh(getattr(node, "document_type", ""))
    code = getattr(node, "document_code", None) or "（无编号）"
    name = getattr(node, "document_name", None)
    text = f"{'  ' * min(depth, 6)}- {zh} {code}"
    if name and str(name) != str(code):
        text += f"（{name}）"
    if getattr(node, "is_deleted", False):
        text += "（已删除）"
    return text


def _render_nodes(
    nodes: List[Any],
    admin: bool,
    codes: frozenset,
    depth: int,
    remaining: int,
) -> Tuple[List[str], int, int, int]:
    """按节点类型读权限过滤渲染追溯树。

    返回 (lines, hidden_count, overflow_count, remaining)。无权节点连同其
    子树只计数（用户看不到父节点上下文，子树一并隐藏）；超出展开上限的
    可见节点单独计数为未展开。
    """
    lines: List[str] = []
    hidden = 0
    overflow = 0
    for node in nodes or []:
        if not _doc_type_allowed(
            getattr(node, "document_type", ""), admin, codes
        ):
            hidden += _count_subtree(node)
            continue
        if remaining <= 0:
            overflow += _count_subtree(node)
            continue
        remaining -= 1
        lines.append(_node_line(node, depth))
        child_lines, child_hidden, child_overflow, remaining = _render_nodes(
            list(getattr(node, "children", None) or []),
            admin,
            codes,
            depth + 1,
            remaining,
        )
        lines.extend(child_lines)
        hidden += child_hidden
        overflow += child_overflow
    return lines, hidden, overflow, remaining


def _render_chain_section(
    title: str,
    nodes: List[Any],
    admin: bool,
    codes: frozenset,
) -> List[str]:
    total = sum(_count_subtree(n) for n in (nodes or []))
    if not nodes or total <= 0:
        return [f"{title}：无关联单据"]
    lines, hidden, overflow, _ = _render_nodes(
        list(nodes), admin, codes, 1, _TRACE_LINE_MAX
    )
    out = [f"{title}（共 {total} 个关联节点）："]
    out.extend(lines)
    if hidden:
        out.append(f"  - 另有 {hidden} 个无权查看的关联单据")
    if overflow:
        out.append(f"  - ……另有 {overflow} 个节点未展开")
    return out


def _fmt_impact_item(item: Dict[str, Any]) -> str:
    code = item.get("code") or "（无编号）"
    name = item.get("name")
    status = item.get("status") or "未知"
    text = f"  - {code}"
    if name and str(name) != str(code):
        text += f"（{name}）"
    text += f"，状态 {status}（id={item.get('id')}）"
    return text


def _render_impact(
    impact: Dict[str, Any],
    section_keys: Tuple[str, ...],
    admin: bool,
    codes: frozenset,
) -> Tuple[List[str], int]:
    """渲染受影响单据分节；返回 (lines, hidden_total)。"""
    lines: List[str] = []
    hidden_total = 0
    for key in section_keys:
        title, permission = _IMPACT_SECTIONS[key]
        items = list((impact or {}).get(key) or [])
        visible: List[Dict[str, Any]] = []
        for item in items:
            if _code_allowed(permission, admin, codes):
                visible.append(item)
            else:
                hidden_total += 1
        if not items:
            continue
        lines.append(f"{title}（{len(items)}）：")
        for item in visible[:_IMPACT_ITEM_MAX]:
            lines.append(_fmt_impact_item(item))
        skipped = len(visible) - min(len(visible), _IMPACT_ITEM_MAX)
        hidden_in_section = len(items) - len(visible)
        if hidden_in_section or skipped:
            parts = []
            if hidden_in_section:
                parts.append(f"{hidden_in_section} 个无权查看")
            if skipped:
                parts.append(f"{skipped} 条未展开")
            lines.append("  - 另有 " + "、".join(parts))
    return lines, hidden_total


def _fmt_dt(value: Any) -> str:
    """datetime/date 展示：datetime 经 API 同口径站点时区文本；上游
    ``changed_at`` 已是 ``to_api_isoformat`` 串时原样透传（缺省 ''）。"""
    if value is None:
        return ""
    from core.utils.timezone_utils import to_api_isoformat

    if isinstance(value, (datetime, date)):
        return to_api_isoformat(value) or ""
    s = str(value).strip()
    return s if s else ""


def _impact_head(impact: Dict[str, Any], doc_zh: str) -> str:
    change = (impact or {}).get("upstream_change") or {}
    code = change.get("code") or "（无编号）"
    text = f"变更影响分析：{doc_zh} {code}"
    changed_at = _fmt_dt(change.get("changed_at"))
    if changed_at:
        text += f"（最近变更 {changed_at}）"
    return text


def _impact_tail(impact: Dict[str, Any], shown_any: bool, empty_text: str) -> List[str]:
    actions = [str(a) for a in (impact or {}).get("recommended_actions") or []]
    tail: List[str] = []
    if not shown_any and not actions:
        tail.append(empty_text)
    if actions:
        tail.append("建议操作：" + "；".join(actions))
    return tail


async def trace_document_chain(
    document_type: Optional[str] = None,
    document_id: Optional[int] = None,
    direction: str = "both",
    max_depth: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """追溯单据关联链（X3=a：源单按类型读权限门控，节点按类型读权限过滤）。

    数据范围：源单为销售/采购/需求时按对应 service 的 current_user 行级
    范围复核；链上节点按单据类型读权限过滤（无行级范围口径），无权节点
    只计数不显示编号。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    doc_type = str(document_type or "").strip()
    if doc_type not in _TRACE_DOCUMENT_TYPES:
        return "document_type 不在支持的单据类型闭集内（如 sales_order/work_order/purchase_order/demand 等）"
    resolved_direction = str(direction or "both").strip()
    if resolved_direction not in _TRACE_DIRECTIONS:
        return "direction 仅支持 upstream/downstream/both"
    try:
        doc_id = int(document_id)
    except (TypeError, ValueError):
        return "document_id 须为正整数"
    if doc_id <= 0:
        return "document_id 须为正整数"
    depth = _ct()._clamp_limit(
        max_depth, default=_TRACE_DEPTH_MAX, upper=_TRACE_DEPTH_MAX
    )

    admin, codes = await _perm_view(ctx)
    if not _doc_type_allowed(doc_type, admin, codes):
        return "当前用户无权查看该类型单据的关联链"
    if not await _source_doc_visible(ctx, doc_type, doc_id):
        return "未找到该单据，或不在当前用户数据范围内"

    try:
        from apps.kuaizhizao.services.document_relation_new_service import (
            DocumentRelationNewService,
        )

        trace = await DocumentRelationNewService().trace_document_chain(
            tenant_id=ctx.tenant_id,
            document_type=doc_type,
            document_id=doc_id,
            direction=resolved_direction,
            max_depth=depth,
        )
    except Exception as exc:
        logger.warning(
            "AI tool trace_document_chain 失败 error_type={}",
            type(exc).__name__,
        )
        return "追溯单据关联链失败，请稍后重试"

    root_code = getattr(trace, "document_code", None)
    if not root_code:
        return "未找到该单据，或已被删除"

    out = [f"单据关联链：{_type_zh(doc_type)} {root_code}"]
    shown = False
    if resolved_direction in ("upstream", "both"):
        section = _render_chain_section(
            "上游关联", list(getattr(trace, "upstream_chain", None) or []),
            admin, codes,
        )
        out.extend(section)
        shown = shown or len(section) > 1
    if resolved_direction in ("downstream", "both"):
        section = _render_chain_section(
            "下游关联", list(getattr(trace, "downstream_chain", None) or []),
            admin, codes,
        )
        out.extend(section)
        shown = shown or len(section) > 1
    if not shown:
        out.append("该单据当前没有可展示的关联单据")
    return "\n".join(out)


async def analyze_sales_order_change_impact(
    sales_order_id: Optional[int] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """销售订单变更影响分析（受影响需求/需求计算/生产计划/工单）。

    数据范围：源单按 ``kuaizhizao:sales-order`` 行级范围复核，范围外按
    不存在回复；受影响条目按单据类型读权限过滤，无权条目只计数。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        oid = int(sales_order_id)
    except (TypeError, ValueError):
        return "sales_order_id 须为正整数"
    if oid <= 0:
        return "sales_order_id 须为正整数"
    if not await _source_doc_visible(ctx, "sales_order", oid):
        return "未查询到该销售订单，或不在当前用户数据范围内"
    admin, codes = await _perm_view(ctx)
    try:
        from apps.kuaizhizao.services.document_relation_new_service import (
            DocumentRelationNewService,
        )
        from infra.exceptions.exceptions import NotFoundError

        impact = await DocumentRelationNewService().get_change_impact_sales_order(
            tenant_id=ctx.tenant_id,
            order_id=oid,
        )
    except NotFoundError:
        return "未查询到该销售订单，或不在当前用户数据范围内"
    except Exception as exc:
        logger.warning(
            "AI tool analyze_sales_order_change_impact 失败 error_type={}",
            type(exc).__name__,
        )
        return "分析销售订单变更影响失败，请稍后重试"

    out = [_impact_head(impact, "销售订单")]
    body, hidden = _render_impact(impact, _SALES_DEMAND_IMPACT_KEYS, admin, codes)
    out.extend(body)
    out.extend(
        _impact_tail(impact, bool(body), "该销售订单变更当前未影响任何下游单据")
    )
    if hidden:
        out.append(f"（另有 {hidden} 个无权查看的受影响单据）")
    return "\n".join(out)


async def analyze_purchase_order_change_impact(
    purchase_order_id: Optional[int] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """采购订单变更影响分析（受影响收货通知单/入库单）。

    数据范围：源单按 ``kuaizhizao:purchase-order`` 行级范围复核，范围外按
    不存在回复；受影响条目按单据类型读权限过滤，无权条目只计数。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        oid = int(purchase_order_id)
    except (TypeError, ValueError):
        return "purchase_order_id 须为正整数"
    if oid <= 0:
        return "purchase_order_id 须为正整数"
    if not await _source_doc_visible(ctx, "purchase_order", oid):
        return "未查询到该采购订单，或不在当前用户数据范围内"
    admin, codes = await _perm_view(ctx)
    try:
        from apps.kuaizhizao.services.document_relation_new_service import (
            DocumentRelationNewService,
        )
        from infra.exceptions.exceptions import NotFoundError

        impact = await DocumentRelationNewService().get_change_impact_purchase_order(
            tenant_id=ctx.tenant_id,
            order_id=oid,
        )
    except NotFoundError:
        return "未查询到该采购订单，或不在当前用户数据范围内"
    except Exception as exc:
        logger.warning(
            "AI tool analyze_purchase_order_change_impact 失败 error_type={}",
            type(exc).__name__,
        )
        return "分析采购订单变更影响失败，请稍后重试"

    out = [_impact_head(impact, "采购订单")]
    body, hidden = _render_impact(impact, _PURCHASE_IMPACT_KEYS, admin, codes)
    out.extend(body)
    out.extend(
        _impact_tail(impact, bool(body), "该采购订单变更当前未影响任何下游单据")
    )
    if hidden:
        out.append(f"（另有 {hidden} 个无权查看的受影响单据）")
    return "\n".join(out)


async def analyze_demand_change_impact(
    demand_id: Optional[int] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """需求变更影响分析（受影响需求/需求计算/生产计划/工单）。

    数据范围：源单按 ``kuaizhizao:plan-management-demand-management``
    行级范围复核（T1 定，与 ``/demands`` 路由模块一致），范围外按不存在
    回复；受影响条目按单据类型读权限过滤，无权条目只计数。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        oid = int(demand_id)
    except (TypeError, ValueError):
        return "demand_id 须为正整数"
    if oid <= 0:
        return "demand_id 须为正整数"
    if not await _source_doc_visible(ctx, "demand", oid):
        return "未查询到该需求，或不在当前用户数据范围内"
    admin, codes = await _perm_view(ctx)
    try:
        from apps.kuaizhizao.services.document_relation_new_service import (
            DocumentRelationNewService,
        )
        from infra.exceptions.exceptions import NotFoundError

        impact = await DocumentRelationNewService().get_change_impact_demand(
            tenant_id=ctx.tenant_id,
            demand_id=oid,
        )
    except NotFoundError:
        return "未查询到该需求，或不在当前用户数据范围内"
    except Exception as exc:
        logger.warning(
            "AI tool analyze_demand_change_impact 失败 error_type={}",
            type(exc).__name__,
        )
        return "分析需求变更影响失败，请稍后重试"

    out = [_impact_head(impact, "需求")]
    body, hidden = _render_impact(impact, _SALES_DEMAND_IMPACT_KEYS, admin, codes)
    out.extend(body)
    out.extend(
        _impact_tail(impact, bool(body), "该需求变更当前未影响任何下游单据")
    )
    if hidden:
        out.append(f"（另有 {hidden} 个无权查看的受影响单据）")
    return "\n".join(out)
