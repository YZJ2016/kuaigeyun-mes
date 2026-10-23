"""KU-AI 场景只读 Tool：一次合格率与缺陷帕累托（spec 198）。

Tool 名：``analyze_first_pass_yield`` / ``analyze_defect_pareto``。

T1 事实（写 §4）：
- ``/production``、``/quality`` 报表路由均不向 service 传 ``current_user``
  （reports.py:699-756 / :517-564），``get_production_report`` /
  ``get_quality_report`` / ``FirstPassYieldService`` 签名亦无该参——报表页
  未做用户数据范围，按 spec §1 Tool 不额外收紧也不放宽。
- FPY 三方法签名：`get_summary(tenant_id, *, date_start, date_end, …)` → dict；
  `get_operation_breakdown(tenant_id, *, date_start, date_end, approved_only,
  limit=10)` → 行（operation_name + 量/率字段，按 count 降序）；
  `get_daily_trend(tenant_id, *, days=7, end_at, …)` → 每日
  {date, qualification_rate, first_pass_yield_rate}。
- 帕累托 `get_quality_report("defect-pareto-analysis")` 返回**明细**
  （最近 100 条 DefectRecord，-created_at），非聚合：适配层按 defect_type
  聚合数量/占比/累计占比（确定性，AC2 允许），摘要注明样本范围。
- `get_worker_breakdown` 不接入（不输出员工绩效排名，spec §1）。
- 日期口径同既有 Tool：start→日初、end→日末（`scene_tools` 410-417 行模式），
  与路由裸 `%Y-%m-%d` 零点解析不同（路由口径更窄），§4 记录。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"
_VIEWS = frozenset({"summary", "operations", "trend"})
_DAYS_MIN, _DAYS_MAX = 1, 31
# 与 service 内 .limit(100) 一致的样本边界
_PARETO_SAMPLE = 100


def _ct():
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _day_bounds(
    date_start: Optional[str], date_end: Optional[str]
):
    """start→日初、end→日末（含界）；非法返回 (None, None, err)。"""
    st = _st()
    start_d = st._parse_date(date_start)
    end_d = st._parse_date(date_end)
    if date_start and start_d is None:
        return None, None, "date_start 须为 YYYY-MM-DD"
    if date_end and end_d is None:
        return None, None, "date_end 须为 YYYY-MM-DD"
    start_dt = (
        datetime.combine(start_d, datetime.min.time()) if start_d else None
    )
    end_dt = datetime.combine(end_d, datetime.max.time()) if end_d else None
    return start_dt, end_dt, None


async def analyze_first_pass_yield(
    view: str = "summary",
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    days: Optional[int] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """一次合格率三视图：summary 总览 / operations 工序明细 / trend 每日趋势。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    v = (str(view).strip() or "summary").lower()
    if v not in _VIEWS:
        return "view 仅支持 summary/operations/trend"
    start_dt, end_dt, err = _day_bounds(date_start, date_end)
    if err:
        return err
    try:
        from apps.kuaizhizao.services.first_pass_yield_service import (
            FirstPassYieldService,
        )

        svc = FirstPassYieldService()
        if v == "summary":
            s = await svc.get_summary(
                ctx.tenant_id, date_start=start_dt, date_end=end_dt
            )
            rng = ""
            if start_dt or end_dt:
                rng = (
                    f"（{start_dt.date() if start_dt else '始'} 至 "
                    f"{end_dt.date() if end_dt else '今'}）"
                )
            return (
                f"一次合格率{rng}：首次合格 "
                f"{_ct()._fmt_num(s.get('first_pass_qualified_quantity'))}"
                f"/首次报工 {_ct()._fmt_num(s.get('first_pass_reported_quantity'))}"
                f" = {s.get('first_pass_yield_rate', 0)}%；"
                f"综合合格率 {s.get('qualification_rate', 0)}%（含返工后合格）"
            )
        if v == "operations":
            rows = await svc.get_operation_breakdown(
                ctx.tenant_id,
                date_start=start_dt,
                date_end=end_dt,
                limit=500,
            )
            rows = list(rows or [])
            if not rows:
                return "未查询到该期间的工序报工记录"
            # 报表页默认按 first_pass_yield_rate 降序；业务问「最差工序」
            # → 升序展示最差在前，数值与 service/报表页同口径
            rows.sort(
                key=lambda r: r.get("first_pass_yield_rate") or 0
            )
            top = rows[: _ct()._clamp_limit(limit)]
            lines = [
                f"共 {len(rows)} 道工序有报工（按一次合格率升序，最差在前），"
                f"返回前 {len(top)} 条："
            ]
            for r in top:
                lines.append(
                    f"工序 {r.get('operation_name') or '-'}："
                    f"直通率 {r.get('first_pass_yield_rate', 0)}%，"
                    f"报工 {_ct()._fmt_num(r.get('reported_quantity'))}，"
                    f"首次合格 {_ct()._fmt_num(r.get('first_pass_qualified_quantity'))}，"
                    f"综合合格率 {r.get('qualification_rate', 0)}%"
                )
            return "\n".join(lines)
        # trend
        try:
            d = 7 if days is None else int(days)
        except (TypeError, ValueError):
            return f"days 仅支持 {_DAYS_MIN}-{_DAYS_MAX}"
        if d < _DAYS_MIN or d > _DAYS_MAX:
            return f"days 仅支持 {_DAYS_MIN}-{_DAYS_MAX}"
        trend = await svc.get_daily_trend(ctx.tenant_id, days=d)
        trend = list(trend or [])
        if not trend:
            return "未查询到该期间的直通率趋势数据"
        lines = [f"近 {d} 天一次合格率趋势："]
        for r in trend:
            lines.append(
                f"{r.get('date')}: 直通率 {r.get('first_pass_yield_rate', 0)}%，"
                f"综合合格率 {r.get('qualification_rate', 0)}%"
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.warning(
            "AI tool analyze_first_pass_yield 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询一次合格率失败，请稍后重试"


async def analyze_defect_pareto(
    material_id: Optional[int] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """缺陷帕累托：按缺陷类型聚合最近样本，输出数量/占比/累计占比。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    start_dt, end_dt, err = _day_bounds(date_start, date_end)
    if err:
        return err
    try:
        from apps.kuaizhizao.services.report_service import ReportService

        report = await ReportService().get_quality_report(
            ctx.tenant_id,
            "defect-pareto-analysis",
            date_start=start_dt,
            date_end=end_dt,
            material_id=int(material_id) if material_id else None,
        )
        items = list((report or {}).get("data") or [])
    except Exception as exc:
        logger.warning(
            "AI tool analyze_defect_pareto 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询缺陷帕累托失败，请稍后重试"
    if not items:
        return "未查询到符合条件的缺陷记录"

    # service 返回明细（最近 _PARETO_SAMPLE 条）：适配层按缺陷类型聚合
    agg: Dict[str, float] = {}
    total_qty = 0.0
    for it in items:
        key = str(it.get("defect_type") or "未分类")
        qty = float(it.get("defect_quantity") or 0)
        agg[key] = agg.get(key, 0.0) + qty
        total_qty += qty
    ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)

    top = ranked[: _ct()._clamp_limit(limit)]
    lines = [
        f"缺陷帕累托（基于最近 {len(items)} 条缺陷记录，按缺陷类型聚合"
        f"{'，样本达上限 ' + str(_PARETO_SAMPLE) + ' 条，非全量' if len(items) >= _PARETO_SAMPLE else ''}）："
    ]
    cumulative = 0.0
    for name, qty in top:
        share = round(qty / total_qty * 100, 1) if total_qty else 0.0
        cumulative += share
        lines.append(
            f"{name}：{qty:g} 件，占比 {share}%，累计 {round(cumulative, 1)}%"
        )
    return "\n".join(lines)
