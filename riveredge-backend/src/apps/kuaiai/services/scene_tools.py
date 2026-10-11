"""KU-AI 场景只读 Tool handler（spec 181 T5，六值闭集）。

Tool 名钉死六值：``query_inventory_balance`` / ``query_delivery_risk`` /
``query_purchase_followup`` / ``query_published_schedule`` /
``query_quality_anomalies`` / ``query_supplier_orders``。

约束（设计 §5.3）：
- 全部只读：仅调 kuaizhizao 既有读 service，禁 SQL、禁裸 ORM 直写；
- 参数白名单＝函数签名闭集，``limit`` 一律 ≤20；
- 业务读权限由 manifest ``ai_tools[*].permission`` 经 tool_bridge RBAC 复核；
- service 不接收 current_user 的（库存报表 / 交期风险 / 滚动排程 / 质量异常）
  在本适配层补 DataScopeService 行级范围，不拿全租户数据返回；
- 返回模型可读的有界摘要文本：只留编码/名称/数量/日期/状态/风险描述，
  不落客户与供应商敏感扩展字段、内部路径、SQL；
- 无数据返回真实空文案；底层异常失败关闭回固定错误文案。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"


def _ct():
    """chat_tools 私有助手延迟借用。

    本模块同时是 manifest ``ai_tools`` handler 目标：``chat_tools`` 底部
    ``_register_manifest_tools`` 经 importlib 反查本模块；若本模块先被导入且
    顶层反向 import chat_tools，会拿到半初始化模块，故改为函数内延迟导入。
    """
    from apps.kuaiai.services import chat_tools

    return chat_tools

# query_quality_anomalies 检验类型闭集（与 FinishedGoodsInspectionService 契约一致）
_INSPECTION_TYPES = frozenset({"incoming", "process", "finished"})
_INSPECTION_TYPE_ZH = {
    "incoming": "来料",
    "process": "过程",
    "finished": "成品",
}

# 只暴露「已发布可读事实」的排程状态（closed 日为已发布排程的关账态）
_PUBLISHED_PLAN_STATUSES = frozenset({"published", "closed"})

# 适配层数据范围资源键：沿用 manifest reference_resources 已声明的
# data_scope_key / 模块权限前缀；无显式策略时按平台「无策略=全部」语义放行，
# 用户角色未授予该资源时 DataScopeService 内部已失败关闭（id=-1）。
_SCOPE_INVENTORY = "kuaizhizao:inventory"
_SCOPE_WORK_ORDER = "kuaizhizao:work-order"
_SCOPE_QUALITY_ANALYSIS = "kuaizhizao:quality-analysis"
_SCOPE_ROLLING_SCHEDULE = "kuaizhizao:plan-management-rolling-scheduling"


def _parse_date(value: Any) -> Optional[date]:
    """YYYY-MM-DD / ISO datetime 字符串 → date；非法返回 None。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


async def _apply_scope(queryset, tenant_id: int, ctx: AiRuntimeContext, resource: str):
    """DataScopeService 统一入口（service 不接收 current_user 的适配层补齐）。"""
    from core.services.authorization.data_scope_service import DataScopeService

    return await DataScopeService.apply(
        queryset,
        tenant_id=tenant_id,
        user=ctx.user,
        resource=resource,
    )


async def _scoped_row_ids(model, ctx: AiRuntimeContext, resource: str, ids: Set[int]) -> Set[int]:
    """对候选 id 集合套资源数据范围，返回可见 id 集合。"""
    if not ids:
        return set()
    qs = model.filter(
        tenant_id=ctx.tenant_id, id__in=list(ids), deleted_at__isnull=True
    )
    qs = await _apply_scope(qs, ctx.tenant_id, ctx, resource)
    return {int(x) for x in await qs.values_list("id", flat=True)}


async def _inventory_visible_pairs(ctx: AiRuntimeContext) -> Set[Tuple[Optional[int], Optional[int]]]:
    """库存余额行可见性：批次/线边两类存量源分别套 ``kuaizhizao:inventory``
    资源范围，取 (material_id, warehouse_id) 可见对，再与报表行做交集。

    无显式数据策略时平台语义为全部可见（pairs 覆盖所有报表行）；配置策略后
    按画像 created_by 收敛，越界仓/料不返回。
    """
    from apps.kuaizhizao.models.line_side_inventory import LineSideInventory
    from apps.master_data.models.material_batch import MaterialBatch

    pairs: Set[Tuple[Optional[int], Optional[int]]] = set()
    for model in (MaterialBatch, LineSideInventory):
        try:
            qs = model.filter(
                tenant_id=ctx.tenant_id, deleted_at__isnull=True
            )
            qs = await _apply_scope(qs, ctx.tenant_id, ctx, _SCOPE_INVENTORY)
            rows = await qs.values("material_id", "warehouse_id")
            for r in rows:
                pairs.add((r.get("material_id"), r.get("warehouse_id")))
        except Exception as exc:
            # 单一存量源范围解析失败 → 失败关闭（宁缺勿滥）
            logger.warning(
                "AI tool query_inventory_balance 数据范围失败 model={} error_type={}",
                getattr(model, "__name__", model),
                type(exc).__name__,
            )
            return set()
    return pairs


async def query_inventory_balance(
    keyword: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """即时库存余额摘要（物料×仓库 结存），跨仓检索。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        from apps.kuaizhizao.services.report_service import ReportService

        report = await ReportService().get_inventory_report(
            ctx.tenant_id,
            "summary",
            warehouse_id=int(warehouse_id) if warehouse_id else None,
            keyword=(str(keyword).strip() or None) if keyword else None,
        )
        rows = list((report or {}).get("data") or [])
    except Exception as exc:
        logger.warning(
            "AI tool query_inventory_balance 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询库存余额失败，请稍后重试"
    if not rows:
        return "未查询到符合条件的库存记录"

    try:
        pairs = await _inventory_visible_pairs(ctx)
    except Exception as exc:
        logger.warning(
            "AI tool query_inventory_balance 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询库存余额失败，请稍后重试"
    rows = [
        r
        for r in rows
        if (r.get("material_id"), r.get("warehouse_id")) in pairs
    ]
    if not rows:
        return "当前用户数据范围内未查询到符合条件的库存记录"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 条库存余额记录（当前用户数据范围内），返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(
            f"物料 {r.get('material_code') or ''}"
            f"（{r.get('material_name') or '未命名'}）"
            f" @ {r.get('warehouse_name') or '未配置仓库'}："
            f"结存 {_ct()._fmt_num(r.get('closing_qty'))}，"
            f"本期入 {_ct()._fmt_num(r.get('inbound_qty'))}，"
            f"本期出 {_ct()._fmt_num(r.get('outbound_qty'))}"
        )
    return "\n".join(lines)


async def query_delivery_risk(
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """工单交期风险摘要（逾期 / MTO 连带风险），按当前用户工单数据范围过滤。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        from apps.kuaizhizao.services.production_control_service import (
            ProductionControlService,
        )

        rows = await ProductionControlService().get_delivery_risk_orders(
            ctx.tenant_id
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_delivery_risk 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询交期风险失败，请稍后重试"
    if not rows:
        return "当前没有识别到交期风险工单"

    try:
        from apps.kuaizhizao.models.work_order import WorkOrder

        candidate_ids = {
            int(r["work_order_id"])
            for r in rows
            if r.get("work_order_id") is not None
        }
        visible_ids = await _scoped_row_ids(
            WorkOrder, ctx, _SCOPE_WORK_ORDER, candidate_ids
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_delivery_risk 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询交期风险失败，请稍后重试"

    rows = [r for r in rows if int(r.get("work_order_id") or 0) in visible_ids]
    if not rows:
        return "当前用户数据范围内没有识别到交期风险工单"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 张交期风险工单（当前用户数据范围内），返回前 {len(top)} 张："
    ]
    for r in top:
        lines.append(
            f"工单 {r.get('work_order_code') or ''}"
            f"（{r.get('work_order_name') or '未命名'}）："
            f"{r.get('risk_desc') or '存在交期风险'}，"
            f"状态 {r.get('status') or '未知'}，"
            f"计划完工 {r.get('planned_end_date') or '未排定'}"
            f"（id={r.get('work_order_id') or ''}）"
        )
    return "\n".join(lines)


def _fmt_purchase_order_row(order: Any) -> str:
    """采购订单模型可读摘要：不含供应商联系人/电话等敏感扩展字段。"""
    overdue = "，到货逾期" if getattr(order, "has_arrival_overdue", False) else ""
    return (
        f"采购单 {getattr(order, 'order_code', '') or ''}："
        f"供应商 {getattr(order, 'supplier_name', '') or '未知'}，"
        f"状态 {getattr(order, 'status', '') or '未知'}"
        f"/{getattr(order, 'review_status', '') or '未审'}，"
        f"要求到货 {getattr(order, 'delivery_date', '') or '未定'}，"
        f"待收货 {_ct()._fmt_num(getattr(order, 'outstanding_total', None))}"
        f"{overdue}"
        f"（id={getattr(order, 'id', '')}）"
    )


async def query_purchase_followup(
    supplier_id: Optional[int] = None,
    buyer_id: Optional[int] = None,
    status: Optional[str] = None,
    delivery_date_from: Optional[str] = None,
    delivery_date_to: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """采购跟单摘要：PurchaseService 已按 current_user 套采购单数据范围。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        from apps.kuaizhizao.schemas.purchase import PurchaseOrderListParams
        from apps.kuaizhizao.services.purchase_service import PurchaseService

        params = PurchaseOrderListParams(
            supplier_id=int(supplier_id) if supplier_id else None,
            buyer_id=int(buyer_id) if buyer_id else None,
            status=(str(status).strip() or None) if status else None,
            delivery_date_from=_parse_date(delivery_date_from),
            delivery_date_to=_parse_date(delivery_date_to),
            skip=0,
            limit=_ct()._clamp_limit(limit),
        )
        result = await PurchaseService().list_purchase_orders(
            ctx.tenant_id, params, current_user=ctx.user
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_purchase_followup 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询采购订单失败，请稍后重试"
    rows = list((result or {}).get("data") or [])
    total = int((result or {}).get("total") or len(rows))
    if not rows:
        return "未查询到符合条件的采购订单"
    lines = [f"共 {total} 张采购订单（当前用户数据范围内），返回前 {len(rows)} 张："]
    lines.extend(_fmt_purchase_order_row(o) for o in rows)
    return "\n".join(lines)


async def query_published_schedule(
    plan_date: str,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """已发布滚动排程摘要：仅 published/closed 日可读，叠排程数据范围。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    day = _parse_date(plan_date)
    if day is None:
        return "plan_date 须为 YYYY-MM-DD 格式的日期"
    try:
        from apps.kuaizhizao.services.rolling_schedule_service import (
            RollingScheduleService,
        )

        plan = await RollingScheduleService().get_plan_by_date(
            ctx.tenant_id, day
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_published_schedule 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询滚动排程失败，请稍后重试"
    if plan is None:
        return f"{day.isoformat()} 无滚动排程计划"
    if str(getattr(plan, "status", "") or "") not in _PUBLISHED_PLAN_STATUSES:
        return f"{day.isoformat()} 排程尚未发布，无已发布可读事实"

    try:
        from apps.kuaizhizao.models.rolling_schedule_plan import (
            RollingSchedulePlan,
        )

        visible = await _scoped_row_ids(
            RollingSchedulePlan,
            ctx,
            _SCOPE_ROLLING_SCHEDULE,
            {int(plan.id)},
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_published_schedule 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询滚动排程失败，请稍后重试"
    if int(plan.id) not in visible:
        return "当前用户数据范围内无该日排程"

    lines_out = list(getattr(plan, "lines", None) or [])
    lines = [
        f"{day.isoformat()} 排程 {getattr(plan, 'plan_code', '') or ''}"
        f"（状态 {getattr(plan, 'status', '')}，共 {len(lines_out)} 行）："
    ]
    for ln in lines_out[:20]:
        diag = ""
        raw_diag = getattr(ln, "scheduling_diagnostics", None) or []
        if raw_diag:
            diag = f"，诊断 {'；'.join(str(d) for d in raw_diag[:3])}"
        lines.append(
            f"{getattr(ln, 'sequence', '')}. "
            f"工单 {getattr(ln, 'work_order_code', '') or ''}"
            f"（{getattr(ln, 'work_order_name', '') or '未命名'}）："
            f"排产 {_ct()._fmt_num(getattr(ln, 'planned_quantity', None))}，"
            f"已完成 {_ct()._fmt_num(getattr(ln, 'completed_quantity', None))}"
            f"{diag}"
        )
    if len(lines_out) > 20:
        lines.append(f"……另有 {len(lines_out) - 20} 行未展开")
    return "\n".join(lines)


async def query_quality_anomalies(
    inspection_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    material_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """质量异常摘要：不合格检验记录，按当前用户质量分析数据范围过滤。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    itype = (str(inspection_type).strip() or None) if inspection_type else None
    if itype is not None and itype not in _INSPECTION_TYPES:
        return "inspection_type 仅支持 incoming/process/finished"
    try:
        from apps.kuaizhizao.services.quality_service import (
            FinishedGoodsInspectionService,
        )

        # inspection_time 为 DatetimeField：start→日初、end→日末，保证当天含界
        start_d = _parse_date(start_date)
        end_d = _parse_date(end_date)
        start_dt = (
            datetime.combine(start_d, datetime.min.time()) if start_d else None
        )
        end_dt = (
            datetime.combine(end_d, datetime.max.time()) if end_d else None
        )

        rows = await FinishedGoodsInspectionService().get_quality_anomalies(
            ctx.tenant_id,
            inspection_type=itype,
            start_date=start_dt,
            end_date=end_dt,
            material_id=int(material_id) if material_id else None,
            supplier_id=int(supplier_id) if supplier_id else None,
            limit=100,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_quality_anomalies 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询质量异常失败，请稍后重试"
    if not rows:
        return "未查询到符合条件的质量异常记录"

    try:
        from apps.kuaizhizao.models.finished_goods_inspection import (
            FinishedGoodsInspection,
        )
        from apps.kuaizhizao.models.incoming_inspection import (
            IncomingInspection,
        )
        from apps.kuaizhizao.models.process_inspection import (
            ProcessInspection,
        )

        model_by_type = {
            "incoming": IncomingInspection,
            "process": ProcessInspection,
            "finished": FinishedGoodsInspection,
        }
        visible: Set[Tuple[str, int]] = set()
        for t, model in model_by_type.items():
            ids = {
                int(r["inspection_id"])
                for r in rows
                if r.get("inspection_type") == t
                and r.get("inspection_id") is not None
            }
            allowed = await _scoped_row_ids(
                model, ctx, _SCOPE_QUALITY_ANALYSIS, ids
            )
            visible |= {(t, i) for i in allowed}
    except Exception as exc:
        logger.warning(
            "AI tool query_quality_anomalies 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询质量异常失败，请稍后重试"

    rows = [
        r
        for r in rows
        if (r.get("inspection_type"), int(r.get("inspection_id") or 0))
        in visible
    ]
    if not rows:
        return "当前用户数据范围内未查询到符合条件的质量异常记录"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 条质量异常记录（当前用户数据范围内），返回前 {len(top)} 条："
    ]
    for r in top:
        zh = _INSPECTION_TYPE_ZH.get(str(r.get("inspection_type") or ""), "检验")
        supplier = (
            f"，供应商 {r.get('supplier_name')}"
            if r.get("supplier_name")
            else ""
        )
        reason = (
            f"，原因 {r.get('nonconformance_reason')}"
            if r.get("nonconformance_reason")
            else ""
        )
        lines.append(
            f"{zh}检验 {r.get('inspection_code') or ''}："
            f"物料 {r.get('material_code') or ''}"
            f"（{r.get('material_name') or '未命名'}）{supplier}，"
            f"不合格 {_ct()._fmt_num(r.get('unqualified_quantity'))}"
            f"/检验 {_ct()._fmt_num(r.get('inspection_quantity'))}"
            f"{reason}，时间 {r.get('inspection_time') or '未知'}"
        )
    return "\n".join(lines)


async def query_supplier_orders(
    supplier_id: int,
    status: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """指定供应商采购订单摘要：沿用采购单数据范围（不直调无范围的协同 service）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        sid = int(supplier_id)
    except (TypeError, ValueError):
        return "supplier_id 无效"
    if sid <= 0:
        return "supplier_id 无效"
    try:
        from apps.kuaizhizao.schemas.purchase import PurchaseOrderListParams
        from apps.kuaizhizao.services.purchase_service import PurchaseService

        params = PurchaseOrderListParams(
            supplier_id=sid,
            status=(str(status).strip() or None) if status else None,
            skip=0,
            limit=_ct()._clamp_limit(limit),
        )
        result = await PurchaseService().list_purchase_orders(
            ctx.tenant_id, params, current_user=ctx.user
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_supplier_orders 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询供应商采购订单失败，请稍后重试"
    rows = list((result or {}).get("data") or [])
    total = int((result or {}).get("total") or len(rows))
    if not rows:
        return f"供应商 {sid} 在当前用户数据范围内无符合条件的采购订单"
    lines = [
        f"供应商 {sid} 共 {total} 张采购订单（当前用户数据范围内），"
        f"返回前 {len(rows)} 张："
    ]
    lines.extend(_fmt_purchase_order_row(o) for o in rows)
    return "\n".join(lines)
