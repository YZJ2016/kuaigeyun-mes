"""KU-AI 场景只读 Tool：工单齐套分析与生产异常（spec 197）。

Tool 名：``analyze_kitting`` / ``query_material_shortages`` /
``query_delivery_delays`` / ``query_quality_exceptions``。

- ``analyze_kitting`` 只调 ``WorkOrderService.compute_work_order_kitting_analysis``
  （K1-b 纯计算，不写 ``work_orders.readiness_rate`` 等缓存字段）；by-ID 前
  经 ``chat_tools._work_order_in_scope`` 复核工单行级范围，范围外按不存在回复。
- 三个异常 service（``ExceptionService.list_*``）均不接收 ``current_user``；
  行级收敛 = 异常自身资源键 ``_scoped_row_ids``（页面资源键，与
  ``page_context`` 同一套 ``_SCOPE_*``）∩ 关联工单 ``kuaizhizao:work-order``
  可见集求交，两层都要过。
- 无工单行口径（评审 minor-8，spec 197 §4 补记决策）：与 page_context
  一致——``QualityException.work_order_id`` 可空（检验来源异常无工单），
  无工单行只须过自身资源范围即保留；缺料/延期异常 ``work_order_id`` 为
  必填字段，缺关联一律按不存在剔除，不再无条件保留。
- statuses 为逗号分隔串（``apply_exception_status_filter`` 同口径），逐值校验闭集。
"""

from __future__ import annotations

from typing import Any, List, Optional, Set

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"
_SCOPE_WORK_ORDER = "kuaizhizao:work-order"
# 异常自身资源键（页面功能资源键，与 page_context._SCOPE_* 同口径）
_SCOPE_MATERIAL_SHORTAGE = (
    "kuaizhizao:production-execution-material-shortage-exceptions"
)
_SCOPE_DELIVERY_DELAY = (
    "kuaizhizao:production-execution-delivery-delay-exceptions"
)
_SCOPE_QUALITY_EXCEPTION = (
    "kuaizhizao:production-execution-quality-exceptions"
)

# 闭集参数（T1 核实）
# exception_service.py:_material_shortage_alert_level / schema 描述
_ALERT_LEVELS = frozenset({"low", "medium", "high", "critical"})
# ACTIVE_EXCEPTION_STATUSES + handle 动作落地值（缺料/延期）
_OPEN_EXCEPTION_STATUSES = frozenset(
    {"pending", "processing", "resolved", "cancelled"}
)
# ACTIVE_QUALITY_EXCEPTION_STATUSES + handle 动作落地值（质量）
_QUALITY_STATUSES = frozenset(
    {"pending", "investigating", "correcting", "closed", "cancelled"}
)
# ExceptionService._normalize_severity
_SEVERITIES = frozenset({"minor", "major", "critical"})
# create 校验 allowed_types（exception_service.py:343-347）
_QUALITY_TYPES = frozenset(
    {"inspection_failure", "process_deviation", "customer_complaint"}
)

_OVERSAMPLE_LIMIT = 100


def _ct():
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _fetch_limit(limit: Any) -> int:
    return min(max(_ct()._clamp_limit(limit) * 5, 50), _OVERSAMPLE_LIMIT)


def _check_statuses(statuses: Optional[str], allowed: frozenset) -> Optional[str]:
    """逗号分隔 statuses 逐值校验；合法返回原串，非法返回错误文案。"""
    if not statuses:
        return None
    parts = [p.strip() for p in str(statuses).split(",") if p.strip()]
    bad = [p for p in parts if p not in allowed]
    if bad or not parts:
        return f"statuses 仅支持 {'/'.join(sorted(allowed))}（逗号分隔）"
    return None


async def _visible_wo_ids(ctx: AiRuntimeContext, wo_ids: Set[int]) -> Set[int]:
    from apps.kuaizhizao.models.work_order import WorkOrder

    return await _st()._scoped_row_ids(
        WorkOrder, ctx, _SCOPE_WORK_ORDER, {int(i) for i in wo_ids if i}
    )


async def _scoped_exception_rows(
    rows: List[Any],
    ctx: AiRuntimeContext,
    err_text: str,
    *,
    model: Any,
    own_resource: str,
    keep_wo_less: bool,
):
    """异常行双层范围收敛，返回 (rows 或 None, err_text 或 None)。

    口径与 ``page_context`` 一致（评审 minor-8 / spec 197 §4）：
    1. 异常行先按自身资源键 ``own_resource`` 套 ``_scoped_row_ids``；
    2. 有关联工单的行再按 ``kuaizhizao:work-order`` 可见集求交；
    3. ``work_order_id`` 为空的行：``keep_wo_less=True``（质量异常）
       保留，``False``（缺料/延期，字段必填）按不存在剔除。
    范围解析异常一律失败关闭。
    """
    try:
        ids = {
            int(getattr(r, "id")) for r in rows if getattr(r, "id", None)
        }
        own_visible = await _st()._scoped_row_ids(
            model, ctx, own_resource, ids
        )
        rows = [
            r
            for r in rows
            if int(getattr(r, "id", 0) or 0) in own_visible
        ]
        visible = await _visible_wo_ids(
            ctx,
            {
                int(getattr(r, "work_order_id"))
                for r in rows
                if getattr(r, "work_order_id", None)
            },
        )
    except Exception as exc:
        logger.warning(
            "AI tool 异常列表数据范围失败 error_type={}", type(exc).__name__
        )
        return None, err_text
    out: List[Any] = []
    for r in rows:
        wid = getattr(r, "work_order_id", None)
        if wid is None:
            if keep_wo_less:
                out.append(r)
        elif int(wid) in visible:
            out.append(r)
    return out, None


def _fmt_material_shortage_row(r: Any) -> str:
    """缺料异常行摘要（Tool 与页上下文 reader 共用口径，spec 204 AC4）。"""
    return (
        f"工单 {getattr(r, 'work_order_code', '') or '-'} "
        f"物料 {getattr(r, 'material_code', '') or ''}"
        f"（{getattr(r, 'material_name', '') or '未命名'}）："
        f"需求 {_ct()._fmt_num(getattr(r, 'required_quantity', None))}，"
        f"可用 {_ct()._fmt_num(getattr(r, 'available_quantity', None))}，"
        f"缺口 {_ct()._fmt_num(getattr(r, 'shortage_quantity', None))}，"
        f"级别 {getattr(r, 'alert_level', '') or '未知'}，"
        f"状态 {getattr(r, 'status', '') or '未知'}"
    )


def _fmt_delivery_delay_row(r: Any) -> str:
    """延期异常行摘要。"""
    return (
        f"工单 {getattr(r, 'work_order_code', '') or '-'}："
        f"计划完工 {getattr(r, 'planned_end_date', '') or '未定'}，"
        f"延期 {getattr(r, 'delay_days', '') or 0} 天，"
        f"原因 {getattr(r, 'delay_reason', '') or '未填写'}，"
        f"级别 {getattr(r, 'alert_level', '') or '未知'}，"
        f"状态 {getattr(r, 'status', '') or '未知'}"
    )


def _fmt_quality_exception_row(r: Any) -> str:
    """质量异常行摘要（Tool 与页上下文 reader 共用口径，spec 204 AC4）。"""
    return (
        f"类型 {getattr(r, 'exception_type', '') or '未知'} "
        f"工单 {getattr(r, 'work_order_code', '') or '-'} "
        f"物料 {getattr(r, 'material_code', '') or '-'}"
        f"（{getattr(r, 'material_name', '') or '未命名'}）"
        f"批号 {getattr(r, 'batch_no', '') or '-'}："
        f"严重程度 {getattr(r, 'severity', '') or '未知'}，"
        f"状态 {getattr(r, 'status', '') or '未知'}"
    )


async def analyze_kitting(
    work_order_id: Any = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """单工单齐套分析：齐套率 + 缺料明细（缺口降序前 20，纯计算不写库）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        wid = int(work_order_id)
    except (TypeError, ValueError):
        return "work_order_id 必填且须为整数"
    if wid <= 0:
        return "work_order_id 必填且须为正整数"
    if not await _ct()._work_order_in_scope(ctx, wid):
        return "工单不存在或超出当前用户数据范围"
    try:
        from apps.kuaizhizao.services.work_order_service import WorkOrderService

        resp = await WorkOrderService().compute_work_order_kitting_analysis(
            ctx.tenant_id, wid
        )
    except Exception as exc:
        # NotFoundError 与范围外同文案，不泄露存在性
        logger.warning(
            "AI tool analyze_kitting 失败 wo={} error_type={}",
            wid,
            type(exc).__name__,
        )
        if type(exc).__name__ == "NotFoundError":
            return "工单不存在或超出当前用户数据范围"
        return "查询工单齐套分析失败，请稍后重试"

    status = getattr(resp, "status", "") or "未知"
    lines = [
        f"工单 {getattr(resp, 'work_order_code', '') or wid}："
        f"齐套率 {getattr(resp, 'kitting_rate', '')}%（{status}）"
    ]
    items = [
        i
        for i in (getattr(resp, "items", None) or [])
        if getattr(i, "kitting_applicable", True)
        and (getattr(i, "shortage_quantity", 0) or 0) > 0
    ]
    items.sort(key=lambda i: i.shortage_quantity, reverse=True)
    if not items:
        lines.append("无缺料明细")
    else:
        lines.append(f"缺料明细（按缺口降序，前 {min(len(items), 20)} 条）：")
        for i in items[:20]:
            avail = (i.main_warehouse_available or 0) + (i.line_side_available or 0)
            lines.append(
                f"物料 {i.material_code}（{i.material_name or '未命名'}）："
                f"需求 {_ct()._fmt_num(i.required_quantity)}，"
                f"可用 {_ct()._fmt_num(avail)}，"
                f"缺口 {_ct()._fmt_num(i.shortage_quantity)}，"
                f"状态 {i.status}"
            )
    return "\n".join(lines)


async def query_material_shortages(
    work_order_id: Optional[int] = None,
    statuses: Optional[str] = None,
    alert_level: Optional[str] = None,
    material_code: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """缺料异常摘要（工单/物料/需求/可用/缺口/级别/状态，按工单范围收敛）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    err = _check_statuses(statuses, _OPEN_EXCEPTION_STATUSES)
    if err:
        return err
    a_level = (str(alert_level).strip() or None) if alert_level else None
    if a_level is not None and a_level not in _ALERT_LEVELS:
        return "alert_level 仅支持 low/medium/high/critical"
    try:
        from apps.kuaizhizao.services.exception_service import ExceptionService

        rows, _total = await ExceptionService().list_material_shortage_exceptions(
            ctx.tenant_id,
            work_order_id=int(work_order_id) if work_order_id else None,
            statuses=statuses,
            alert_level=a_level,
            skip=0,
            limit=_fetch_limit(limit),
            material_code=(str(material_code).strip() or None) if material_code else None,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_material_shortages 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询缺料异常失败，请稍后重试"
    rows = list(rows or [])
    if not rows:
        return "未查询到符合条件的缺料异常"
    from apps.kuaizhizao.models.material_shortage_exception import (
        MaterialShortageException,
    )

    rows, err = await _scoped_exception_rows(
        rows,
        ctx,
        "查询缺料异常失败，请稍后重试",
        model=MaterialShortageException,
        own_resource=_SCOPE_MATERIAL_SHORTAGE,
        keep_wo_less=False,
    )
    if rows is None:
        return err
    if not rows:
        return "当前用户数据范围内未查询到符合条件的缺料异常"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 条缺料异常（当前用户数据范围内），返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(_fmt_material_shortage_row(r))
    return "\n".join(lines)


async def query_delivery_delays(
    work_order_id: Optional[int] = None,
    statuses: Optional[str] = None,
    alert_level: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """延期异常摘要（工单/计划完工/延期天数/原因/级别/状态，按工单范围收敛）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    err = _check_statuses(statuses, _OPEN_EXCEPTION_STATUSES)
    if err:
        return err
    a_level = (str(alert_level).strip() or None) if alert_level else None
    if a_level is not None and a_level not in _ALERT_LEVELS:
        return "alert_level 仅支持 low/medium/high/critical"
    try:
        from apps.kuaizhizao.services.exception_service import ExceptionService

        rows, _total = await ExceptionService().list_delivery_delay_exceptions(
            ctx.tenant_id,
            work_order_id=int(work_order_id) if work_order_id else None,
            statuses=statuses,
            alert_level=a_level,
            skip=0,
            limit=_fetch_limit(limit),
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_delivery_delays 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询延期异常失败，请稍后重试"
    rows = list(rows or [])
    if not rows:
        return "未查询到符合条件的延期异常"
    from apps.kuaizhizao.models.delivery_delay_exception import (
        DeliveryDelayException,
    )

    rows, err = await _scoped_exception_rows(
        rows,
        ctx,
        "查询延期异常失败，请稍后重试",
        model=DeliveryDelayException,
        own_resource=_SCOPE_DELIVERY_DELAY,
        keep_wo_less=False,
    )
    if rows is None:
        return err
    if not rows:
        return "当前用户数据范围内未查询到符合条件的延期异常"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 条延期异常（当前用户数据范围内），返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(_fmt_delivery_delay_row(r))
    return "\n".join(lines)


async def query_quality_exceptions(
    exception_type: Optional[str] = None,
    work_order_id: Optional[int] = None,
    statuses: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """质量异常摘要（类型/工单/物料/批号/严重程度/状态，按工单范围收敛）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    e_type = (str(exception_type).strip() or None) if exception_type else None
    if e_type is not None and e_type not in _QUALITY_TYPES:
        return "exception_type 仅支持 inspection_failure/process_deviation/customer_complaint"
    err = _check_statuses(statuses, _QUALITY_STATUSES)
    if err:
        return err
    s_sev = (str(severity).strip() or None) if severity else None
    if s_sev is not None and s_sev not in _SEVERITIES:
        return "severity 仅支持 minor/major/critical"
    try:
        from apps.kuaizhizao.services.exception_service import ExceptionService

        rows, _total = await ExceptionService().list_quality_exceptions(
            ctx.tenant_id,
            exception_type=e_type,
            work_order_id=int(work_order_id) if work_order_id else None,
            statuses=statuses,
            severity=s_sev,
            skip=0,
            limit=_fetch_limit(limit),
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_quality_exceptions 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询质量异常失败，请稍后重试"
    rows = list(rows or [])
    if not rows:
        return "未查询到符合条件的质量异常"
    from apps.kuaizhizao.models.quality_exception import QualityException

    rows, err = await _scoped_exception_rows(
        rows,
        ctx,
        "查询质量异常失败，请稍后重试",
        model=QualityException,
        own_resource=_SCOPE_QUALITY_EXCEPTION,
        keep_wo_less=True,
    )
    if rows is None:
        return err
    if not rows:
        return "当前用户数据范围内未查询到符合条件的质量异常"

    top = rows[: _ct()._clamp_limit(limit)]
    lines = [
        f"共 {len(rows)} 条质量异常（当前用户数据范围内），返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(_fmt_quality_exception_row(r))
    return "\n".join(lines)
