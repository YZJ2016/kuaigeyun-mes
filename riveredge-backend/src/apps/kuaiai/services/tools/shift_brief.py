"""KU-AI 场景只读 Tool：生产日报与异常信号（spec 199）。

Tool 名：``query_production_daily`` / ``query_pulse_signals``。

T1 事实（写 §4）：
- ``run_pulse(tenant_id, user, *, domains, severity, page, page_size)``
  → ``PulseOut{summary, groups, errors, complete}``（registry.py:142-219）；
  Tool 直接用 ``pulse_registry.parse_domains`` 复用 REST 同口径逗号分隔
  闭集（production/inventory/sales/quality/equipment），severity 闭集
  ``info/warning/error/critical``（SEVERITIES :56）。errors[]/complete 透传：
  失败或未接入领域明确列出，不写成“无异常”。
- ``GET /production-daily/reports`` 路由（production_daily.py:142-168）不传
  ``current_user`` → 日报页无用户数据范围，Tool 不额外收紧；权限码
  ``kuaizhizao:production-daily:read`` 与列表路由一致。
- ``ProductionDailyReportService.list_reports`` 返回 ``(items, total)``；
  ``summarize`` 返回 ``{items, total, summary}``，items 展开 ``f_{key}``
  field_values → 摘要每行只取前 3 个数值型 ``f_*`` 字段。
- 不调用 ``list_templates``（``ensure_seed=True`` 默认会写预置模板，只读
  Tool 不得触达）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, List, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"
_VIEWS = frozenset({"reports", "summary"})
_SEVERITIES = frozenset({"info", "warning", "error", "critical"})
_DOMAIN_LABELS = {
    "production": "生产",
    "inventory": "库存",
    "sales": "销售",
    "quality": "质量",
    "equipment": "设备",
}
# summarize 行 f_* 数值字段最多取数
_SUMMARY_FIELD_CAP = 3


def _ct():
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _day_or_err(value: Optional[str], name: str):
    if not value:
        return None, None
    d = _st()._parse_date(value)
    if d is None:
        return None, f"{name} 须为 YYYY-MM-DD"
    return d, None


def _domain_label(domain: str) -> str:
    return _DOMAIN_LABELS.get(domain, domain)


def _numeric_summary_fields(item: dict) -> List[str]:
    """summarize 行的 f_* 数值字段（int/float/Decimal），前 N 个。"""
    out: List[str] = []
    for k, v in item.items():
        if not str(k).startswith("f_"):
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float, Decimal)):
            continue
        out.append(f"{k[2:]}={_ct()._fmt_num(v)}")
        if len(out) >= _SUMMARY_FIELD_CAP:
            break
    return out


async def query_pulse_signals(
    domain: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """Pulse 异常信号：与 GET /operations/pulse 同口径，透传 errors/complete。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    sev = (str(severity).strip() or None) if severity else None
    if sev is not None and sev not in _SEVERITIES:
        return "severity 仅支持 info/warning/error/critical"
    try:
        from apps.kuaiai.services.pulse import registry as pulse_registry

        domains = pulse_registry.parse_domains(domain)
    except ValueError:
        return (
            "domain 仅支持 production,inventory,sales,quality,equipment"
            "（逗号分隔）"
        )
    try:
        out = await pulse_registry.run_pulse(
            ctx.tenant_id,
            ctx.user,
            domains=domains,
            severity=sev,
            page=1,
            page_size=_ct()._clamp_limit(limit),
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_pulse_signals 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询异常信号失败，请稍后重试"

    summary = getattr(out, "summary", None)
    groups = list(getattr(out, "groups", None) or [])
    errors = list(getattr(out, "errors", None) or [])
    complete = getattr(out, "complete", True)

    lines: List[str] = []
    if summary and getattr(summary, "total", 0):
        shown = sum(len(getattr(g, "items", None) or []) for g in groups)
        lines.append(
            f"异常信号共 {summary.total} 条"
            f"（高优先级 {summary.high_priority}、严重 {summary.critical}、"
            f"预警/错误 {summary.warning_or_error}），返回前 {shown} 条："
        )
        for g in groups:
            for i in g.items:
                lines.append(
                    f"[{_domain_label(i.domain)}·{i.severity}] {i.title} — "
                    f"{i.fact}；建议：{i.suggestion}"
                )
    else:
        lines.append("当前无异常信号")

    if errors:
        parts = [f"{_domain_label(e.domain)}：{e.message}" for e in errors]
        prefix = "部分领域检测未完成" if not complete else "部分领域未接入检测器"
        lines.append(f"{prefix}：" + "；".join(parts))
    return "\n".join(lines)


async def query_production_daily(
    view: str = "reports",
    team_name: Optional[str] = None,
    template_code: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """生产日报：reports 列表视图 / summary 汇总视图（展开数值字段）。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    v = (str(view).strip() or "reports").lower()
    if v not in _VIEWS:
        return "view 仅支持 reports/summary"
    d_start, err = _day_or_err(date_start, "date_start")
    if err:
        return err
    d_end, err = _day_or_err(date_end, "date_end")
    if err:
        return err
    t_name = (str(team_name).strip() or None) if team_name else None
    t_code = (str(template_code).strip() or None) if template_code else None
    lim = _ct()._clamp_limit(limit)
    try:
        from apps.kuaizhizao.services.production_daily_service import (
            ProductionDailyReportService,
        )

        svc = ProductionDailyReportService()
        if v == "reports":
            resp = await svc.list_reports(
                ctx.tenant_id,
                template_code=t_code,
                team_name=t_name,
                date_start=d_start,
                date_end=d_end,
                skip=0,
                limit=lim,
            )
            items = list(getattr(resp, "items", None) or [])
            total = getattr(resp, "total", len(items))
        else:
            resp = await svc.summarize(
                ctx.tenant_id,
                template_code=t_code,
                team_name=t_name,
                date_start=d_start,
                date_end=d_end,
                skip=0,
                limit=lim,
            )
            items = list((resp or {}).get("items") or [])
            total = (resp or {}).get("total", len(items))
    except Exception as exc:
        logger.warning(
            "AI tool query_production_daily 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询生产日报失败，请稍后重试"

    if not items:
        return "未查询到符合条件的生产日报"
    lines = [
        f"共 {total} 条生产日报，返回前 {len(items)} 条（按日期倒序）："
    ]
    for r in items:
        get = r.get if isinstance(r, dict) else lambda k, d=None: getattr(r, k, d)
        seg = (
            f"日报 {get('code') or '-'}：{get('report_date') or '日期未定'}，"
            f"班组 {get('team_name') or '未填'}，"
            f"模板 {get('template_name') or get('template_code') or '-'}，"
            f"状态 {get('status') or '未知'}"
        )
        if v == "summary" and isinstance(r, dict):
            fields = _numeric_summary_fields(r)
            if fields:
                seg += "，" + "、".join(fields)
        lines.append(seg)
    return "\n".join(lines)
