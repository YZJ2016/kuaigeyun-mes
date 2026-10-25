"""KU-AI 场景只读 Tool：可视排产看板事实（spec 206）。

Tool 名：``query_scheduling_board``。

- 事实来源复用 ``apps.kuaizhizao.services.scheduling_ai_service`` 拆出的
  纯事实函数：``_load_board_work_orders``（看板候选工单）与
  ``scan_scheduling_board_facts``（``VisualSchedulingService.scan_board``
  诊断 + 排产约束），与看板路由 ``GET /scheduling/board-scan`` /
  ``POST /ai-assist/explain`` 同口径（status∈draft/released/in_progress；
  ``plan_date`` 过滤 planned_start_date 当日，缺省为近 14 天窗）。
- 本 Tool 只取确定性事实，不调用任何大模型，亦不调用
  ``SchedulingAiService`` 的模型方法（``_chat_json`` / ``explain`` /
  ``suggest_*``，X1=a：避免「模型调 Tool 再调模型」双层调用）；解释与
  调整建议由外层 Agent 基于事实完成。
- 看板路由仅 tenant + 权限放行（service 不接收 current_user）；适配层
  对候选工单补 ``kuaizhizao:plan-management-scheduling`` 资源行级范围
  （data_scope_setup 已注册，无显式策略=全部，与路由同口径；有策略按
  工单 created_by 收敛），scan 仅跑可见工单集合。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# 适配层数据范围资源键：manifest 已注册的排产看板资源
# （data_scope_setup.py ``kuaizhizao:plan-management-scheduling``，
# 工单画像 applicant=created_by）
_SCOPE_SCHEDULING_BOARD = "kuaizhizao:plan-management-scheduling"


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _parse_date(value: Any):
    """YYYY-MM-DD → date；非法返回 None（复用 scene_tools 实现）。"""
    from apps.kuaiai.services import scene_tools

    return scene_tools._parse_date(value)


def _fmt_dt(value: Any) -> str:
    """计划起止：datetime 经 API 同口径站点时区文本；缺省「未定」。"""
    if value is None:
        return "未定"
    try:
        from core.utils.timezone_utils import to_api_isoformat

        out = to_api_isoformat(value)
        if out:
            return out
    except Exception:
        pass
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    s = str(value).strip()
    return s or "未定"


def _fmt_board_order_row(wo: Any, now: Any) -> str:
    """看板工单事实行：编号/名称/状态/工作中心/计划起止/冻结/齐套/逾期。"""
    from apps.kuaizhizao.services.scheduling_ai_service import _is_overdue

    marks = []
    if getattr(wo, "is_frozen", False):
        marks.append("已冻结")
    rate = getattr(wo, "readiness_rate", None)
    if rate is not None:
        try:
            marks.append(f"齐套率 {float(rate):.0f}%")
        except (TypeError, ValueError):
            pass
    if _is_overdue(wo, now):
        marks.append("已逾期")
    mark_txt = f"，{'/'.join(marks)}" if marks else ""
    return (
        f"工单 {getattr(wo, 'code', '') or getattr(wo, 'id', '')}"
        f"（{getattr(wo, 'name', None) or '未命名'}）："
        f"状态 {_ct()._fmt_status(getattr(wo, 'status', None))}，"
        f"工作中心 {getattr(wo, 'work_center_name', None) or '未分配'}，"
        f"计划 {_fmt_dt(getattr(wo, 'planned_start_date', None))}"
        f" → {_fmt_dt(getattr(wo, 'planned_end_date', None))}"
        f"{mark_txt}（id={getattr(wo, 'id', '')}）"
    )


async def query_scheduling_board(
    ctx: Optional[AiRuntimeContext] = None,
    plan_date: Optional[str] = None,
    work_center_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """可视排产看板事实摘要：看板工单/计划时段 + 冲突/未排产/缺配置/
    物料齐套/工位超载/排产约束。

    纯事实返回（无模型生成文字）；数据范围在适配层补
    ``kuaizhizao:plan-management-scheduling`` 行级范围。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    day = _parse_date(plan_date) if plan_date else None
    if plan_date and day is None:
        return "plan_date 须为 YYYY-MM-DD 格式的日期"
    try:
        wc_id = int(work_center_id) if work_center_id else None
    except (TypeError, ValueError):
        return "work_center_id 须为整数"

    try:
        from apps.kuaizhizao.models.work_order import WorkOrder
        from apps.kuaizhizao.services.scheduling_ai_service import (
            _load_board_work_orders,
        )
        from core.utils.timezone_utils import now_utc

        candidates = await _load_board_work_orders(
            ctx.tenant_id, None, day, work_center_id=wc_id
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_scheduling_board 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询排程看板失败，请稍后重试"
    if not candidates:
        return "当前用户数据范围内未查询到看板工单"

    try:
        from apps.kuaiai.services.scene_tools import _scoped_row_ids

        visible = await _scoped_row_ids(
            WorkOrder,
            ctx,
            _SCOPE_SCHEDULING_BOARD,
            {int(wo.id) for wo in candidates},
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_scheduling_board 数据范围失败 error_type={}",
            type(exc).__name__,
        )
        return "查询排程看板失败，请稍后重试"
    work_orders = [wo for wo in candidates if int(wo.id) in visible]
    if not work_orders:
        return "当前用户数据范围内未查询到看板工单"

    try:
        from apps.kuaizhizao.services.scheduling_ai_service import (
            scan_scheduling_board_facts,
        )

        scan_raw, constraints = await scan_scheduling_board_facts(
            ctx.tenant_id,
            work_order_ids=[int(wo.id) for wo in work_orders],
            work_center_id=wc_id,
            plan_date=day,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_scheduling_board scan 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询排程看板失败，请稍后重试"

    max_rows = _ct()._clamp_limit(limit)
    scope_label = day.isoformat() if day else "近 14 天"
    lines = [f"排产看板事实（{scope_label}，当前用户数据范围内）："]

    shown = work_orders[:max_rows]
    lines.append(f"一、看板工单 {len(work_orders)} 张，返回前 {len(shown)} 张：")
    for wo in shown:
        lines.append(_fmt_board_order_row(wo, now_utc()))
    if len(work_orders) > max_rows:
        lines.append(f"……另有 {len(work_orders) - max_rows} 张未展开")

    conflicts = list(scan_raw.get("conflicts") or [])
    conflict_total = int(scan_raw.get("conflict_count") or len(conflicts))
    lines.append(f"二、排程冲突 {conflict_total} 项：")
    if not conflicts:
        lines.append("无")
    for c in conflicts[:max_rows]:
        refs = []
        if c.get("operation_id"):
            refs.append(f"工序id={c['operation_id']}")
        if c.get("station_id"):
            refs.append(f"工位id={c['station_id']}")
        ref_txt = f"（{'，'.join(refs)}）" if refs else ""
        lines.append(
            f"[{c.get('type') or 'unknown'}] {c.get('message') or ''}{ref_txt}"
        )
    if conflict_total > max_rows:
        lines.append(f"……另有 {conflict_total - max_rows} 项未展开")

    unscheduled = list(scan_raw.get("unscheduled_orders") or [])
    lines.append(f"三、未排产工单 {len(unscheduled)} 张：")
    if not unscheduled:
        lines.append("无")
    for u in unscheduled[:max_rows]:
        lines.append(
            f"工单 {u.get('work_order_code') or u.get('work_order_id') or ''}："
            f"{u.get('reason') or '未排产'}"
            f"（id={u.get('work_order_id') or ''}）"
        )

    missing = list(scan_raw.get("missing_settings") or [])
    lines.append(f"四、缺排产配置 {len(missing)} 项：")
    if not missing:
        lines.append("无")
    for m in missing[:max_rows]:
        lines.append(
            f"工单 {m.get('work_order_code') or m.get('work_order_id') or ''} "
            f"工序 {m.get('operation_name') or m.get('operation_id') or ''}："
            f"缺 {m.get('label') or m.get('field') or ''}"
            f"（operation_id={m.get('operation_id') or ''}）"
        )

    material = list(scan_raw.get("material_issues") or [])
    lines.append(f"五、物料齐套问题 {len(material)} 项：")
    if not material:
        lines.append("无")
    for mi in material[:max_rows]:
        lines.append(
            f"工单 {mi.get('work_order_code') or mi.get('work_order_id') or ''}："
            f"{mi.get('message') or '齐套率不足'}"
        )

    overloaded = [
        r
        for r in (scan_raw.get("load_by_station") or [])
        if r.get("overloaded")
    ]
    lines.append(f"六、超载工位 {len(overloaded)} 个工位日：")
    if not overloaded:
        lines.append("无")
    for r in overloaded[:max_rows]:
        lines.append(
            f"工位 {r.get('station_name') or r.get('station_id') or ''} "
            f"{r.get('day') or ''}：负荷 {r.get('hours')}h，"
            f"负荷率 {r.get('rate')}%"
        )

    freeze = constraints.get("freeze_horizon_days")
    rolling = constraints.get("rolling_horizon_days")
    if freeze is not None or rolling is not None:
        lines.append(
            f"排产约束：冻结窗 {freeze if freeze is not None else '未配置'} 天，"
            f"滚动窗 {rolling if rolling is not None else '未配置'} 天"
        )
    return "\n".join(lines)
