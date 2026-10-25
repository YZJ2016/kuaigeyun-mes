"""KU-AI 场景只读 Tool：设备 OEE 与损失分解（spec 211）。

Tool 名：``query_equipment_oee`` / ``analyze_equipment_losses``。

T1 事实（写 spec §4）：
- ``EquipmentOEEService.calculate_equipment_oee(tenant_id, equipment_id,
  date_start=None, date_end=None)`` → dict：
  ``equipment{id,uuid,code,name}`` / ``period{start,end}`` /
  ``metrics{planned_runtime,actual_runtime,actual_quantity,
  qualified_quantity,unqualified_quantity}``（小时/数量或 None）/
  ``oee{availability_rate,performance_rate,quality_rate,oee_value}``
  （百分数或 None）/ ``coverage_rate`` / ``unavailable_reasons``（list[str]）/
  ``record_count``；设备不存在抛 NotFoundError；未传日期默认最近 30 天。
- ``list_equipment_oee(tenant_id, date_start, date_end, equipment_ids=None,
  skip=0, limit=100)`` → 同构 dict 列表；传 equipment_ids 时忽略
  skip/limit 且不套 is_active，否则对启用设备分页。
- ``get_equipment_oee_trend(tenant_id, equipment_id, date_start, date_end,
  period="day")`` → ``{trend_data:[{period,oee,metrics}]}``；逐日循环调
  calculate_equipment_oee（重查询），适配层对采样天数设内部上限。
- OEE 路由（api/equipment/equipment.py:861-986）仅
  ``soil_get_current_user`` + ``get_current_tenant``，**无权限码**；
  kuaizhizao manifest 无 ``equipment-oee`` 权限——登记 Tool 权限取
  ``kuaizhizao:equipment-management-equipment:read``（设备台账页，
  OEE 展示同属设备管理域，较路由口径收紧不放宽）。
- ``reference_resources.equipment.data_scope_key = null`` → 设备无行级
  数据范围，与设备页面一致；service 均不接收 ``current_user``，
  适配层不额外补范围（spec §1「不额外收紧也不放宽」同 spec 198 口径）。
- 损失分解数据源：``EquipmentStatusMonitorService.list_equipment_status(
  tenant_id, skip, limit, equipment_uuid=, status=, is_online=,
  date_start=, date_end=)`` → ``(rows, total)``，``-monitored_at`` 序。
  行 ``status`` ∈ {正常,运行中,待机,故障,维修中,停用,校验中,报废}，
  OEE service 仅取 ``data_source="sensor"`` 明细。适配层按
  ``oee_calculator`` 同款口径（每行延伸至 min(end, at+5min, 下一行 at)，
  与设备 technical_parameters.oee.planned_windows 求交）聚合非「运行中」
  秒数 → 停机/故障类别损失工时，确定性可复算，LLM 不参与。
- 日期口径同既有 Tool：start→日初、end→日末（含界）。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# 损失 TopN（spec §2：N=5，其余合并为「其他」）
_LOSS_TOP_N = 5
# 状态监控明细内部上限；超出时输出注明按最近 N 条统计
_MONITOR_DETAIL_MAX = 500
# get_equipment_oee_trend 逐日循环计算，样本天数内部上限
_TREND_SAMPLE_DAYS_MAX = 92
# workshop_id → 设备 id 解析的台账行上限
_WORKSHOP_EQUIPMENT_MAX = 200

# 与 oee_calculator.calculate_oee 同一有效状态集与运行态口径
_MONITOR_VALID_STATUSES = frozenset(
    {"正常", "运行中", "待机", "故障", "维修中", "停用", "校验中", "报废"}
)
_MONITOR_RUNNING = "运行中"


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


def _pct(value: Any) -> str:
    """service 返回的百分数原样输出；None → 不可用（不由 LLM 估算）。"""
    return "不可用" if value is None else f"{value}%"


def _hours(value: Any) -> str:
    return "不可用" if value is None else f"{value}h"


def _loss_breakdown(
    rows: List[Any], start_dt: datetime, end_dt: datetime, config: Any
) -> Tuple[Dict[str, float], bool]:
    """按计划窗口内非运行秒数分状态聚合（与 ``calculate_oee`` 同口径）。

    返回 ``{status: seconds}`` 与是否使用了计划窗口（未配置窗口时按整个
    查询时段统计，输出中注明，与 OEE 页面口径差异写明）。
    """
    from apps.kuaizhizao.services.oee_calculator import (
        _aware,
        validate_oee_config,
    )

    start, end = _aware(start_dt), _aware(end_dt)
    cfg = config if isinstance(config, dict) else {}
    try:
        validate_oee_config(cfg)
    except ValueError:
        cfg = {}
    intervals = [
        (
            max(start, _aware(datetime.fromisoformat(w["start"]))),
            min(end, _aware(datetime.fromisoformat(w["end"]))),
        )
        for w in cfg.get("planned_windows") or []
    ]
    intervals = [(a, b) for a, b in intervals if a < b]
    used_windows = bool(intervals)
    if not intervals:
        intervals = [(start, end)]

    ordered = sorted(rows, key=lambda r: (_aware(r.monitored_at), r.id))
    loss: Dict[str, float] = {}
    for i, row in enumerate(ordered):
        at = _aware(row.monitored_at)
        if at >= end:
            continue
        until = min(
            end,
            at + timedelta(minutes=5),
            (
                _aware(ordered[i + 1].monitored_at)
                if i + 1 < len(ordered)
                else end
            ),
        )
        status = str(getattr(row, "status", "") or "")
        if status not in _MONITOR_VALID_STATUSES or status == _MONITOR_RUNNING:
            continue
        for left, right in intervals:
            seconds = max(
                0.0, (min(right, until) - max(left, at)).total_seconds()
            )
            if seconds:
                loss[status] = loss.get(status, 0.0) + seconds
    return loss, used_windows


async def query_equipment_oee(
    equipment_id: Optional[int] = None,
    workshop_id: Optional[int] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """设备 OEE 列表：期间 OEE 与三分量，与 OEE 页面列表同源一致。"""
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    start_dt, end_dt, err = _day_bounds(date_start, date_end)
    if err:
        return err
    eid = None
    if equipment_id is not None and str(equipment_id).strip() != "":
        try:
            eid = int(equipment_id)
        except (TypeError, ValueError):
            return "equipment_id 须为整数"
        if eid <= 0:
            return "equipment_id 须为正整数"
    wid = None
    if workshop_id is not None and str(workshop_id).strip() != "":
        try:
            wid = int(workshop_id)
        except (TypeError, ValueError):
            return "workshop_id 须为整数"
        if wid <= 0:
            return "workshop_id 须为正整数"
    cap = _ct()._clamp_limit(limit)
    try:
        from apps.kuaizhizao.services.equipment_oee_service import (
            EquipmentOEEService,
        )

        equipment_ids = [eid] if eid is not None else None
        if wid is not None:
            from apps.kuaizhizao.services.equipment_service import (
                EquipmentService,
            )

            ws_rows, _ = await EquipmentService.list_equipment(
                ctx.tenant_id,
                skip=0,
                limit=_WORKSHOP_EQUIPMENT_MAX,
                workshop_id=wid,
                is_active=True,
            )
            ws_ids = [int(r.id) for r in (ws_rows or [])]
            equipment_ids = (
                [i for i in ws_ids if i == eid] if eid is not None else ws_ids
            )
            if not equipment_ids:
                return "未查询到符合条件的设备 OEE 数据"
        oee_list = await EquipmentOEEService().list_equipment_oee(
            tenant_id=ctx.tenant_id,
            date_start=start_dt,
            date_end=end_dt,
            equipment_ids=equipment_ids,
            skip=0,
            limit=cap,
        )
    except Exception as exc:
        logger.warning(
            "AI tool query_equipment_oee 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询设备 OEE 失败，请稍后重试"

    # equipment_ids 路径下 service 不套 limit，适配层截断
    rows = list(oee_list or [])[:cap]
    if not rows:
        return "未查询到符合条件的设备 OEE 数据"

    rng = ""
    if start_dt or end_dt:
        rng = (
            f"（{start_dt.date() if start_dt else '始'} 至 "
            f"{end_dt.date() if end_dt else '今'}）"
        )
    lines = [f"共 {len(rows)} 台设备 OEE 统计{rng}："]
    for item in rows:
        eq = item.get("equipment") or {}
        oee = item.get("oee") or {}
        metrics = item.get("metrics") or {}
        reasons = item.get("unavailable_reasons") or []
        note = f"，注意：{reasons[0]}" if reasons else ""
        if item.get("error"):
            note = f"，注意：{item.get('error')}"
        lines.append(
            f"设备 {eq.get('code') or '-'}（{eq.get('name') or '未命名'}）："
            f"OEE {_pct(oee.get('oee_value'))}，"
            f"时间开动率 {_pct(oee.get('availability_rate'))}，"
            f"性能开动率 {_pct(oee.get('performance_rate'))}，"
            f"良品率 {_pct(oee.get('quality_rate'))}；"
            f"计划 {_hours(metrics.get('planned_runtime'))}"
            f"/实际运行 {_hours(metrics.get('actual_runtime'))}，"
            f"报工 {item.get('record_count', 0)} 条"
            f"（id={eq.get('id') or ''}）{note}"
        )
    return "\n".join(lines)


async def analyze_equipment_losses(
    equipment_id: Optional[int] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """设备 OEE 损失分解：三分量 + 按监控状态聚合的损失工时 TopN + 样本天数。

    聚合全部为适配层确定性计算（SC-D5）：状态明细来自
    ``list_equipment_status``（sensor 明细，与 OEE 同源），时长延伸与
    计划窗口求交口 径同 ``calculate_oee``。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    try:
        eid = int(equipment_id)
    except (TypeError, ValueError):
        return "equipment_id 必填且须为整数"
    if eid <= 0:
        return "equipment_id 必填且须为正整数"
    start_dt, end_dt, err = _day_bounds(date_start, date_end)
    if err:
        return err

    try:
        from apps.kuaizhizao.models.equipment import Equipment
        from apps.kuaizhizao.services.equipment_oee_service import (
            EquipmentOEEService,
        )
        from apps.kuaizhizao.services.equipment_status_monitor_service import (
            EquipmentStatusMonitorService,
        )
        from core.utils.timezone_utils import (
            resolve_business_datetime,
            to_naive_utc,
        )

        equipment = await Equipment.filter(
            tenant_id=ctx.tenant_id, id=eid, deleted_at__isnull=True
        ).first()
        if equipment is None:
            return "未查询到指定设备"

        # service 缺省口径：end=当前、start=end-30 天；监控明细拉取需显式界。
        # _day_bounds 与既有 OEE 调用同口径产 naive（service/ORM 按 UTC 解释），
        # 缺省 end 同样取 naive UTC，保证 start/end 作差、比较口径一致
        end_eff = end_dt or to_naive_utc(resolve_business_datetime())
        start_eff = start_dt or (end_eff - timedelta(days=30))

        oee_svc = EquipmentOEEService()
        overall = await oee_svc.calculate_equipment_oee(
            tenant_id=ctx.tenant_id,
            equipment_id=eid,
            date_start=start_eff,
            date_end=end_eff,
        )

        # 趋势逐日循环计算：采样窗口设上限，超出取最近 N 天并注明
        trend_start, trend_end = start_eff, end_eff
        trend_clipped = False
        if (trend_end - trend_start).days > _TREND_SAMPLE_DAYS_MAX:
            trend_start = trend_end - timedelta(days=_TREND_SAMPLE_DAYS_MAX)
            trend_clipped = True
        trend = await oee_svc.get_equipment_oee_trend(
            tenant_id=ctx.tenant_id,
            equipment_id=eid,
            date_start=trend_start,
            date_end=trend_end,
            period="day",
        )
        sample_days = len((trend or {}).get("trend_data") or [])

        mon_rows, mon_total = await EquipmentStatusMonitorService().list_equipment_status(
            ctx.tenant_id,
            skip=0,
            limit=_MONITOR_DETAIL_MAX,
            equipment_uuid=equipment.uuid,
            date_start=start_eff,
            date_end=end_eff,
        )
        # 与 OEE service 同源：仅 sensor 采集明细参与状态时长聚合
        sensor_rows = [
            r for r in (mon_rows or []) if r.data_source == "sensor"
        ]
        config = (equipment.technical_parameters or {}).get("oee", {})
        loss, used_windows = _loss_breakdown(
            sensor_rows, start_eff, end_eff, config
        )
    except Exception as exc:
        logger.warning(
            "AI tool analyze_equipment_losses 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询设备损失分析失败，请稍后重试"

    eq = (overall or {}).get("equipment") or {}
    oee = (overall or {}).get("oee") or {}
    reasons = (overall or {}).get("unavailable_reasons") or []
    lines = [
        f"设备 {eq.get('code') or '-'}（{eq.get('name') or '未命名'}）"
        f"{start_eff.date()}~{end_eff.date()} OEE 损失分析：",
        f"OEE {_pct(oee.get('oee_value'))} = "
        f"时间开动率 {_pct(oee.get('availability_rate'))} × "
        f"性能开动率 {_pct(oee.get('performance_rate'))} × "
        f"良品率 {_pct(oee.get('quality_rate'))}"
        f"（样本 {sample_days} 天"
        f"{'，趋势采样取最近 ' + str(_TREND_SAMPLE_DAYS_MAX) + ' 天' if trend_clipped else ''}，"
        f"报工 {(overall or {}).get('record_count', 0)} 条）",
    ]
    if reasons:
        lines.append("数据说明：" + "；".join(str(r) for r in reasons[:3]))

    if not loss:
        lines.append("期间内无损失记录")
        if mon_total > len(mon_rows or []):
            lines.append(
                f"（监控明细共 {mon_total} 条，"
                f"按最近 {len(mon_rows or [])} 条统计）"
            )
        return "\n".join(lines)

    total_seconds = sum(loss.values())
    total_hours = round(total_seconds / 3600, 1)
    scope_note = (
        "计划窗口内非运行时长" if used_windows else "期间内非运行时长（未配置计划窗口）"
    )
    header = f"损失工时（{scope_note}，合计 {total_hours} 小时）Top{_LOSS_TOP_N}"
    if mon_total > len(mon_rows or []):
        header += (
            f"；监控明细共 {mon_total} 条，按最近 {len(mon_rows)} 条统计"
        )
    lines.append(header + "：")

    ranked = sorted(loss.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[:_LOSS_TOP_N]
    rest_seconds = sum(v for _, v in ranked[_LOSS_TOP_N:])
    for i, (status, seconds) in enumerate(top, 1):
        hours = round(seconds / 3600, 1)
        share = (
            round(seconds / total_seconds * 100, 1) if total_seconds else 0.0
        )
        lines.append(f"{i}. {status}：{hours} 小时（占比 {share}%）")
    if rest_seconds > 0:
        lines.append(f"其他（合并 {len(ranked) - _LOSS_TOP_N} 类）："
                     f"{round(rest_seconds / 3600, 1)} 小时")
    return "\n".join(lines)
