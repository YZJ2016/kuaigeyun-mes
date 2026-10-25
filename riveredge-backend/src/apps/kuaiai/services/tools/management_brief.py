"""KU-AI 场景只读 Tool：管理层日报/周报聚合简报（spec 218）。

Tool 名：``get_management_brief``。

T1 事实（写 §4）：
- 聚合 Tool 只输出各域现有确定性指标（X6=a），不发明跨域指标；域内对
  service 返回值只做计数/求均值这类确定性聚合（与 analyze_defect_pareto
  适配层聚合同款口径）。
- 每域按数据源独立权限校验（``UserPermissionService.has_permission``，
  ctx 管理员标志位与 tool_bridge 同口径先行放行）；域内全部源无权限 →
  该域显示「无 XX 域查看权限」小节不省略；四域全无权限返回固定文案。
- 各域整节调用独立短超时（``asyncio.wait_for``，``_DOMAIN_TIMEOUT_SECONDS``），
  超时域输出「数据获取超时」小节；源内异常降级为小节内文案，不拖垮整体。
- 期间换算（timezone_utils）：``to_site_date(now_utc())`` 取站点「今天」；
  today/yesterday 单日、this_week=本周一至今、last_week=上周一至周日。
  - datetime 参数（FPY / OEE / 报工统计）→ ``site_day_bounds_utc`` 站点
    日界转 naive UTC（与 ORM USE_TZ 口径一致）；
  - 单据日期/日期参数（日报 report_date、质量异常 created_*_date、故障
    fault_date、预警 triggered_*、盘点 stocktaking_date）→ 站点日历日
    直传，由 service 按日含界（与各页面传参口径一致）。
- 数据范围：与各领域 Tool 同源一致——``list_work_orders`` 内部已套
  ``apply_kuaizhizao_list_scope``；日报/FPY/OEE 无用户数据范围（spec
  198/199/211 T1）；质量异常复用 ``kitting_exceptions._scoped_exception_rows``
  双层收敛（keep_wo_less=True）；故障/库存预警/盘点行经
  ``scene_tools._scoped_row_ids`` 套各资源键收敛；采样计数上限
  ``_SAMPLE_MAX``，超出注明按最近 N 条样本统计。
- 只输出汇总计数与比率：不含人员姓名/明细行/金额字段。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"
_ERR_NO_ANY_PERMISSION = (
    "当前用户没有生产/质量/设备/库存任一领域的查看权限，无法生成管理层简报"
)

_PERIODS = frozenset({"today", "yesterday", "this_week", "last_week"})
_FOCI = frozenset(
    {"production", "quality", "equipment", "inventory", "all"}
)

_DOMAIN_ORDER = ("production", "quality", "equipment", "inventory")
_DOMAIN_LABELS = {
    "production": "生产",
    "quality": "质量",
    "equipment": "设备",
    "inventory": "库存",
}

# 各域整节独立超时（spec §2：单域慢不拖垮整体）
_DOMAIN_TIMEOUT_SECONDS = 5.0
# 需行级收敛计数的源：service 先分页后过滤，按最近 N 条样本统计可见数
_SAMPLE_MAX = 100


def _ct():
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


class _Range(NamedTuple):
    """统计期间：站点日历日 + datetime 参数口径的 naive UTC 日界。"""

    start: date
    end: date
    start_dt: datetime  # 站点日初 → naive UTC（__gte）
    end_dt: datetime  # 站点次日日初 -1µs → naive UTC（__lte，含界）
    label: str  # 展示用期间描述


def _period_range(period: str) -> _Range:
    from core.utils.timezone_utils import (
        now_utc,
        site_day_bounds_utc,
        to_naive_utc,
        to_site_date,
    )

    today = to_site_date(now_utc())
    if period == "today":
        start = end = today
        label = f"今日 {today.isoformat()}"
    elif period == "yesterday":
        start = end = today - timedelta(days=1)
        label = f"昨日 {start.isoformat()}"
    elif period == "this_week":
        start = today - timedelta(days=today.weekday())
        end = today
        label = f"本周 {start.isoformat()}~{end.isoformat()}（周一至今）"
    else:  # last_week
        monday = today - timedelta(days=today.weekday())
        start = monday - timedelta(days=7)
        end = monday - timedelta(days=1)
        label = f"上周 {start.isoformat()}~{end.isoformat()}（周一至周日）"
    s_utc, _ = site_day_bounds_utc(start)
    _, e_utc = site_day_bounds_utc(end)
    return _Range(
        start=start,
        end=end,
        start_dt=to_naive_utc(s_utc),
        end_dt=to_naive_utc(e_utc - timedelta(microseconds=1)),
        label=label,
    )


async def _has_permission(ctx: AiRuntimeContext, code: str) -> bool:
    """逐源权限复核：ctx 管理员标志位与 tool_bridge 同口径先行放行；
    has_permission 解析异常失败关闭。"""
    if getattr(ctx, "is_infra_admin", False) or getattr(
        ctx, "is_tenant_admin", False
    ):
        return True
    try:
        from core.services.authorization.user_permission_service import (
            UserPermissionService,
        )

        return bool(
            await UserPermissionService.has_permission(
                int(ctx.user.id), ctx.tenant_id, code
            )
        )
    except Exception as exc:
        logger.warning(
            "get_management_brief 权限判定失败 code={} error_type={}",
            code,
            type(exc).__name__,
        )
        return False


async def _scoped_count(
    model: Any, ctx: AiRuntimeContext, resource: str, rows: List[Any]
) -> int:
    """行 id 套资源数据范围后计数（与领域 Tool 行级收敛同源）。"""
    ids = {int(getattr(r, "id", 0) or 0) for r in rows} - {0}
    visible = await _st()._scoped_row_ids(model, ctx, resource, ids)
    return sum(1 for r in rows if int(getattr(r, "id", 0) or 0) in visible)


def _sample_note(total: Any, fetched: int) -> str:
    """service total 超过取样上限时的口径说明。"""
    try:
        t = int(total or 0)
    except (TypeError, ValueError):
        t = 0
    if t > fetched:
        return f"（服务端共 {t} 条，按最近 {fetched} 条样本统计可见数）"
    return ""


# ============================================================ 生产域


async def _fetch_work_orders(ctx: AiRuntimeContext, dr: _Range) -> List[str]:
    """工单：期间计划完工 / 当前进行中（service 内已套工单数据范围）。

    「进行中」与工单统计 KPI 卡同口径 = released + in_progress；
    status 仅传单值，两次调用求和。
    """
    from apps.kuaizhizao.services.work_order_service import WorkOrderService

    svc = WorkOrderService()
    _rows, planned = await svc.list_work_orders(
        ctx.tenant_id,
        current_user=ctx.user,
        planned_end_from=dr.start.isoformat(),
        planned_end_to=dr.end.isoformat(),
        limit=1,
        include_downstream_push_progress=False,
    )
    in_progress = 0
    for st in ("released", "in_progress"):
        _rows, n = await svc.list_work_orders(
            ctx.tenant_id,
            current_user=ctx.user,
            status=st,
            limit=1,
            include_downstream_push_progress=False,
        )
        in_progress += int(n or 0)
    return [
        f"工单：期间计划完工 {planned} 张，当前进行中 {in_progress} 张"
        "（计划完工日口径；进行中=已下达+进行中，同 KPI 卡）"
    ]


async def _fetch_reporting(ctx: AiRuntimeContext, dr: _Range) -> List[str]:
    """报工统计：与报工统计页同源，只取汇总字段（不取人员/工序明细）。"""
    from apps.kuaizhizao.services.reporting_service import ReportingService

    s = await ReportingService().get_reporting_statistics(
        ctx.tenant_id,
        date_start=dr.start_dt,
        date_end=dr.end_dt,
    )
    s = s or {}
    return [
        f"报工：已审批 {_ct()._fmt_num(s.get('total_count'))} 笔，"
        f"报工数量 {_ct()._fmt_num(s.get('total_reported_quantity'))}，"
        f"合格 {_ct()._fmt_num(s.get('total_qualified_quantity'))}，"
        f"不合格 {_ct()._fmt_num(s.get('total_unqualified_quantity'))}，"
        f"合格率 {s.get('qualification_rate', 0)}%，"
        f"工时 {_ct()._fmt_num(s.get('total_work_hours'))}h"
        "（报工时间口径）"
    ]


async def _fetch_production_daily(
    ctx: AiRuntimeContext, dr: _Range
) -> List[str]:
    """生产日报：期间填报 / 已提交份数（report_date 口径，页无用户范围）。"""
    from apps.kuaizhizao.services.production_daily_service import (
        ProductionDailyReportService,
    )

    svc = ProductionDailyReportService()
    resp = await svc.list_reports(
        ctx.tenant_id,
        date_start=dr.start,
        date_end=dr.end,
        skip=0,
        limit=1,
    )
    total = getattr(resp, "total", 0)
    resp2 = await svc.list_reports(
        ctx.tenant_id,
        status="submitted",
        date_start=dr.start,
        date_end=dr.end,
        skip=0,
        limit=1,
    )
    submitted = getattr(resp2, "total", 0)
    return [
        f"生产日报：期间填报 {total} 份，已提交 {submitted} 份"
        "（填报日期口径）"
    ]


# ============================================================ 质量域


async def _fetch_fpy(ctx: AiRuntimeContext, dr: _Range) -> List[str]:
    """一次合格率：与 analyze_first_pass_yield summary 同源。"""
    from apps.kuaizhizao.services.first_pass_yield_service import (
        FirstPassYieldService,
    )

    s = await FirstPassYieldService().get_summary(
        ctx.tenant_id,
        date_start=dr.start_dt,
        date_end=dr.end_dt,
    )
    s = s or {}
    return [
        f"一次合格率：首次合格 "
        f"{_ct()._fmt_num(s.get('first_pass_qualified_quantity'))}"
        f"/首次报工 {_ct()._fmt_num(s.get('first_pass_reported_quantity'))}"
        f" = {s.get('first_pass_yield_rate', 0)}%；"
        f"综合合格率 {s.get('qualification_rate', 0)}%"
        "（报工时间口径）"
    ]


async def _fetch_quality_exceptions(
    ctx: AiRuntimeContext, dr: _Range
) -> List[str]:
    """质量异常：期间新增（created 口径）/ 当前未闭环，复用 spec 197
    双层数据范围收敛（自身资源键 ∩ 关联工单可见集）。"""
    from apps.kuaiai.services.tools import kitting_exceptions as kt
    from apps.kuaizhizao.models.quality_exception import QualityException
    from apps.kuaizhizao.services.exception_service import ExceptionService

    svc = ExceptionService()
    rows, total = await svc.list_quality_exceptions(
        ctx.tenant_id,
        created_start_date=dr.start,
        created_end_date=dr.end,
        skip=0,
        limit=_SAMPLE_MAX,
    )
    scoped, err = await kt._scoped_exception_rows(
        list(rows or []),
        ctx,
        "",
        model=QualityException,
        own_resource=kt._SCOPE_QUALITY_EXCEPTION,
        keep_wo_less=True,
    )
    if scoped is None:
        raise RuntimeError(err or "quality exception scope failed")
    new_count = len(scoped)

    open_rows, open_total = await svc.list_quality_exceptions(
        ctx.tenant_id,
        statuses="pending,investigating,correcting",
        skip=0,
        limit=_SAMPLE_MAX,
    )
    scoped_open, err = await kt._scoped_exception_rows(
        list(open_rows or []),
        ctx,
        "",
        model=QualityException,
        own_resource=kt._SCOPE_QUALITY_EXCEPTION,
        keep_wo_less=True,
    )
    if scoped_open is None:
        raise RuntimeError(err or "quality exception scope failed")

    note = _sample_note(total, len(rows or []))
    return [
        f"质量异常：期间新增 {new_count} 条{note}，"
        f"当前未闭环 {len(scoped_open)} 条"
        f"{_sample_note(open_total, len(open_rows or []))}"
        "（创建时间口径，当前用户数据范围内）"
    ]


# ============================================================ 设备域


async def _fetch_oee(ctx: AiRuntimeContext, dr: _Range) -> List[str]:
    """设备 OEE：与 query_equipment_oee 同源；平均 OEE 为返回值的
    确定性算术平均（不可用值不参与），台数/不可用台数为计数。"""
    from apps.kuaizhizao.services.equipment_oee_service import (
        EquipmentOEEService,
    )

    rows = await EquipmentOEEService().list_equipment_oee(
        tenant_id=ctx.tenant_id,
        date_start=dr.start_dt,
        date_end=dr.end_dt,
        skip=0,
        # service 无 total：多取 1 台判定是否真超采样上限
        # （恰达 _SAMPLE_MAX 台不算截断）
        limit=_SAMPLE_MAX + 1,
    )
    rows = list(rows or [])
    over_cap = len(rows) > _SAMPLE_MAX
    rows = rows[:_SAMPLE_MAX]
    values: List[float] = []
    unavailable = 0
    for item in rows:
        oee = (item or {}).get("oee") or {}
        v = oee.get("oee_value")
        if v is None:
            unavailable += 1
            continue
        values.append(float(v))
    mean = round(sum(values) / len(values), 1) if values else None
    mean_text = f"平均 OEE {mean}%" if mean is not None else "平均 OEE 不可用"
    cap_note = f"（已达 {_SAMPLE_MAX} 台取样上限）" if over_cap else ""
    na_note = f"，{unavailable} 台指标不可用" if unavailable else ""
    return [
        f"设备 OEE：{len(rows)} 台设备有统计，{mean_text}{na_note}{cap_note}"
        "（期间统计口径）"
    ]


async def _fetch_faults(ctx: AiRuntimeContext, dr: _Range) -> List[str]:
    """设备故障：期间新增（fault_date 口径）/ 当前待处理+处理中，
    行级范围 ``kuaizhizao:equipment-fault``（同 spec 210）。"""
    from apps.kuaizhizao.models.equipment_fault import EquipmentFault
    from apps.kuaizhizao.services.equipment_fault_service import (
        EquipmentFaultService,
    )

    scope = "kuaizhizao:equipment-fault"
    rows, total = await EquipmentFaultService.list_equipment_faults(
        ctx.tenant_id,
        skip=0,
        limit=_SAMPLE_MAX,
        fault_start_date=dr.start.isoformat(),
        fault_end_date=dr.end.isoformat(),
    )
    new_count = await _scoped_count(EquipmentFault, ctx, scope, list(rows or []))

    pending, _t1 = await EquipmentFaultService.list_equipment_faults(
        ctx.tenant_id, skip=0, limit=_SAMPLE_MAX, status="待处理"
    )
    processing, _t2 = await EquipmentFaultService.list_equipment_faults(
        ctx.tenant_id, skip=0, limit=_SAMPLE_MAX, status="处理中"
    )
    open_count = await _scoped_count(
        EquipmentFault, ctx, scope, list(pending or [])
    ) + await _scoped_count(
        EquipmentFault, ctx, scope, list(processing or [])
    )

    note = _sample_note(total, len(rows or []))
    return [
        f"设备故障：期间新增 {new_count} 条{note}，"
        f"当前待处理/处理中 {open_count} 条"
        "（故障日期口径，当前用户数据范围内）"
    ]


# ============================================================ 库存域


async def _fetch_inventory_alerts(
    ctx: AiRuntimeContext, dr: _Range
) -> List[str]:
    """库存预警：期间触发（triggered_at 口径，含 critical 计数）/
    当前待处理，行级范围 ``kuaizhizao:inventory``（同 spec 196）。"""
    from apps.kuaizhizao.models.inventory_alert import InventoryAlert
    from apps.kuaizhizao.services.inventory_alert_service import (
        InventoryAlertService,
    )

    scope = "kuaizhizao:inventory"
    svc = InventoryAlertService()
    rows, total = await svc.get_alerts(
        ctx.tenant_id,
        skip=0,
        limit=_SAMPLE_MAX,
        triggered_start_date=dr.start.isoformat(),
        triggered_end_date=dr.end.isoformat(),
    )
    rows = list(rows or [])
    ids = {int(getattr(r, "id", 0) or 0) for r in rows} - {0}
    visible = await _st()._scoped_row_ids(InventoryAlert, ctx, scope, ids)
    rows = [r for r in rows if int(getattr(r, "id", 0) or 0) in visible]
    critical = sum(
        1 for r in rows if getattr(r, "alert_level", None) == "critical"
    )

    pending, _t = await svc.get_alerts(
        ctx.tenant_id, skip=0, limit=_SAMPLE_MAX, status="pending"
    )
    pending_count = await _scoped_count(
        InventoryAlert, ctx, scope, list(pending or [])
    )

    note = _sample_note(total, len(rows))
    return [
        f"库存预警：期间触发 {len(rows)} 条{note}"
        f"（critical {critical} 条），当前待处理 {pending_count} 条"
        "（触发时间口径，当前用户数据范围内）"
    ]


async def _fetch_stocktakings(ctx: AiRuntimeContext, dr: _Range) -> List[str]:
    """盘点：期间盘点单（stocktaking_date 口径）/ 当前进行中，
    行级范围 ``kuaizhizao:warehouse-management-stocktaking``。"""
    from apps.kuaizhizao.models.stocktaking import Stocktaking
    from apps.kuaizhizao.services.stocktaking_service import StocktakingService

    scope = "kuaizhizao:warehouse-management-stocktaking"
    svc = StocktakingService()
    resp = await svc.list_stocktakings(
        ctx.tenant_id,
        skip=0,
        limit=_SAMPLE_MAX,
        stocktaking_date_start=dr.start.isoformat(),
        stocktaking_date_end=dr.end.isoformat(),
    )
    items = list(getattr(resp, "items", None) or [])
    total = getattr(resp, "total", len(items))
    new_count = await _scoped_count(Stocktaking, ctx, scope, items)

    resp2 = await svc.list_stocktakings(
        ctx.tenant_id, skip=0, limit=_SAMPLE_MAX, status="in_progress"
    )
    doing_items = list(getattr(resp2, "items", None) or [])
    doing = await _scoped_count(Stocktaking, ctx, scope, doing_items)

    note = _sample_note(total, len(items))
    return [
        f"盘点：期间盘点单 {new_count} 张{note}，"
        f"当前进行中 {doing} 张"
        "（盘点日期口径，当前用户数据范围内）"
    ]


# ============================================================ 域编排

# (源标签, 权限码, fetcher)；权限码=该数据所在页面的读权限（T1 §4 表）
_DOMAIN_SOURCES: Dict[str, Tuple[Tuple[str, str, Any], ...]] = {
    "production": (
        ("工单", "kuaizhizao:work-order:read", _fetch_work_orders),
        (
            "报工",
            "kuaizhizao:production-execution-reporting:read",
            _fetch_reporting,
        ),
        ("生产日报", "kuaizhizao:production-daily:read", _fetch_production_daily),
    ),
    "quality": (
        (
            "一次合格率",
            "kuaizhizao:production-execution-reports-first-pass-yield:read",
            _fetch_fpy,
        ),
        (
            "质量异常",
            "kuaizhizao:production-execution-quality-exceptions:read",
            _fetch_quality_exceptions,
        ),
    ),
    "equipment": (
        (
            "设备 OEE",
            "kuaizhizao:equipment-management-equipment:read",
            _fetch_oee,
        ),
        ("设备故障", "kuaizhizao:equipment-fault:read", _fetch_faults),
    ),
    "inventory": (
        (
            "库存预警",
            "kuaizhizao:warehouse-management-inventory-alert:read",
            _fetch_inventory_alerts,
        ),
        (
            "盘点",
            "kuaizhizao:warehouse-management-stocktaking:read",
            _fetch_stocktakings,
        ),
    ),
}


async def _domain_section(
    ctx: AiRuntimeContext, domain: str, dr: _Range
) -> Tuple[str, str]:
    """单域小节：逐源权限 → 逐源取数。返回 (小节文本, state)；
    state=denied 表示该域全部源无权限（占位小节仍返回，不省略）。"""
    label = _DOMAIN_LABELS[domain]
    lines: List[str] = []
    denied: List[str] = []
    permitted = False
    for src_label, code, fetch in _DOMAIN_SOURCES[domain]:
        if not await _has_permission(ctx, code):
            denied.append(src_label)
            continue
        permitted = True
        try:
            lines.extend(await fetch(ctx, dr))
        except Exception as exc:
            # 域内源异常降级为小节文案，不拖垮整体（失败关闭）
            logger.warning(
                "get_management_brief {}:{} 失败 error_type={}",
                domain,
                src_label,
                type(exc).__name__,
            )
            lines.append(f"{src_label}：数据获取失败")
    if not permitted:
        return f"【{label}】无{label}域查看权限", "denied"
    text = f"【{label}】" + "；".join(lines)
    if denied:
        text += f"（另有无权限查看：{'、'.join(denied)}）"
    return text, "data"


async def _guarded_domain(
    ctx: AiRuntimeContext, domain: str, dr: _Range
) -> Tuple[str, str]:
    """域级超时/异常护栏：超时域输出「数据获取超时」，异常同理降级。"""
    label = _DOMAIN_LABELS[domain]
    try:
        return await asyncio.wait_for(
            _domain_section(ctx, domain, dr),
            timeout=_DOMAIN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("get_management_brief 域超时 domain={}", domain)
        return f"【{label}】数据获取超时", "timeout"
    except Exception as exc:
        logger.warning(
            "get_management_brief 域失败 domain={} error_type={}",
            domain,
            type(exc).__name__,
        )
        return f"【{label}】数据获取失败，请稍后重试", "error"


async def get_management_brief(
    period: str = "today",
    focus: Optional[str] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """管理层简报：按期间分域汇总确定性指标小节。

    ``period`` 闭集 today/yesterday/this_week/last_week；
    ``focus`` 闭集 production/quality/equipment/inventory/all（可空=all）。
    各域并行调用、独立超时；无权限域显示占位小节不省略。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    p = str(period or "today").strip().lower()
    if p not in _PERIODS:
        return "period 仅支持 today/yesterday/this_week/last_week"
    f = str(focus).strip().lower() if focus else "all"
    if f not in _FOCI:
        return "focus 仅支持 production/quality/equipment/inventory/all"
    dr = _period_range(p)
    domains = list(_DOMAIN_ORDER) if f == "all" else [f]
    sections = await asyncio.gather(
        *(_guarded_domain(ctx, d, dr) for d in domains)
    )
    if not sections or all(state == "denied" for _t, state in sections):
        if f == "all":
            return _ERR_NO_ANY_PERMISSION
        return (
            f"当前用户没有{_DOMAIN_LABELS[f]}领域的查看权限，"
            "无法生成管理层简报"
        )
    lines = [
        f"管理层简报：统计期间 {dr.start.isoformat()}~{dr.end.isoformat()}"
        f"（{dr.label}；报工/一次合格率/OEE 等 datetime 参数源按站点时区日界"
        f"换算，其余单据日期参数源按日历日含界（service 内 combine）；"
        f"数值与各领域只读服务同源）"
    ]
    lines.extend(text for text, _state in sections)
    return "\n".join(lines)
