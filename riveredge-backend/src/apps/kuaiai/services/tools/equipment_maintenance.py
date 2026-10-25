"""KU-AI 场景只读 Tool：设备台账、故障维修与保养/校准到期（spec 210）。

Tool 名：``query_equipment`` / ``query_equipment_faults`` /
``query_maintenance_plans`` / ``query_maintenance_reminders`` /
``query_calibration_alerts``。

T1 事实（写 spec §4）：
- 五个底层 service 均不接收 ``current_user``，适配层逐行套
  ``scene_tools._scoped_row_ids`` 行级数据范围；资源键=页面功能码去 ``:read``
  段（沿用 pulse/equipment 与 spec 196 口径）：
  设备台账 ``kuaizhizao:equipment-management-equipment``、
  故障/维修 ``kuaizhizao:equipment-fault``（维修台账页同码）、
  保养计划/执行 ``kuaizhizao:maintenance-plan``（保养执行记录页同码）、
  维护提醒与校准到期提醒 ``kuaizhizao:maintenance-reminder``。
- ``list_equipment_repairs`` 在 ``EquipmentRepairService``（非 spec 表述的
  ``EquipmentFaultService``）；``list_maintenance_executions`` 在
  ``MaintenanceExecutionService``（非 ``MaintenancePlanService``）。
- 过滤键是 ``equipment_uuid``（非 equipment_id）：Tool 收
  ``equipment_uuid`` 直传；``equipment_code`` 经
  ``EquipmentService.get_equipment_by_code`` 解析为 uuid。
- ``list_calibration_alerts`` 对应页面接口 ``GET /equipment/calibration-reminders``
  的权限是 ``maintenance-reminder:read`` 或
  ``measuring-instrument-calibration-reminder:read``（OR），并非 spec 表
  中的 ``equipment-calibration:read``（该校准记录 CRUD 页权限）；
  manifest 只声明单码，取 ``kuaizhizao:maintenance-reminder:read``。
- 日期口径沿用 service（``apply_equipment_document_date_range`` /
  ``list_calibration_alerts`` 内 ``to_site_date``），适配层不做时区换算。
- 不输出维修费用、维护成本等金额字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from core.ai.runtime.context import AiRuntimeContext

_ERR_NO_CONTEXT = "AI 工具缺少租户/用户上下文，无法执行"

# 行级数据范围资源键（页面功能码去 :read；manifest reference_resources 无
# 专属 data_scope_key 的按「无策略=全部」语义放行，有策略按行收敛）
_SCOPE_EQUIPMENT = "kuaizhizao:equipment-management-equipment"
_SCOPE_EQUIPMENT_FAULT = "kuaizhizao:equipment-fault"
_SCOPE_MAINTENANCE_PLAN = "kuaizhizao:maintenance-plan"
_SCOPE_MAINTENANCE_REMINDER = "kuaizhizao:maintenance-reminder"
_SCOPE_MEASURING_CALIBRATION = (
    "kuaizhizao:measuring-instrument-calibration-reminder"
)
# query_calibration_alerts 的 permissions_any 双码 ↔ 行级范围资源键映射：
# 持哪码就用哪码的资源键，避免「持量具码过鉴权但范围恒空」（串联审计 C）
_CALIBRATION_PERM_SCOPES = {
    "kuaizhizao:maintenance-reminder:read": _SCOPE_MAINTENANCE_REMINDER,
    "kuaizhizao:measuring-instrument-calibration-reminder:read": (
        _SCOPE_MEASURING_CALIBRATION
    ),
}

# 视图闭集
_FAULT_VIEWS = frozenset({"faults", "repairs"})
_PLAN_VIEWS = frozenset({"plans", "executions"})

# 状态/枚举闭集（T1 从模型字段注释与 service 常量核实）
# Equipment.status（models/equipment.py:138-141）
_EQUIPMENT_STATUSES = frozenset(
    {"正常", "运行中", "待机", "故障", "维修中", "停用", "校验中", "报废"}
)
# EquipmentFault.status（models/equipment_fault.py:88 注释）
_FAULT_STATUSES = frozenset({"待处理", "处理中", "已修复", "已关闭"})
# EquipmentRepair.status（模型注释：进行中、已完成、已取消）
_REPAIR_STATUSES = frozenset({"进行中", "已完成", "已取消"})
# EquipmentFault.fault_level（轻微、一般、严重、紧急）
_FAULT_LEVELS = frozenset({"轻微", "一般", "严重", "紧急"})
# MaintenancePlan.status（草稿、已发布、执行中、已完成、已取消）
_PLAN_STATUSES = frozenset({"草稿", "已发布", "执行中", "已完成", "已取消"})
# MaintenancePlan.plan_type（预防性维护、定期维护、临时维护）
_PLAN_TYPES = frozenset({"预防性维护", "定期维护", "临时维护"})
# MaintenanceExecution.status（草稿、已确认、已验收）
_EXECUTION_STATUSES = frozenset({"草稿", "已确认", "已验收"})
# MaintenanceExecution.execution_result（正常、异常、待处理）
_EXECUTION_RESULTS = frozenset({"正常", "异常", "待处理"})
# MaintenanceReminder.reminder_type / list_calibration_alerts due_type
_DUE_TYPES = frozenset({"due_soon", "overdue"})
_DUE_TYPE_ZH = {"due_soon": "即将到期", "overdue": "已逾期"}

# 过采样上限：service 先分页后按数据范围收敛，多取减少「范围内行被顶掉」
_OVERSAMPLE_LIMIT = 100
# 故障/维修/提醒描述摘要长度上限
_DESC_MAX = 80


def _ct():
    """chat_tools 私有助手延迟借用（与 scene_tools 同模式，避免循环导入）。"""
    from apps.kuaiai.services import chat_tools

    return chat_tools


def _st():
    from apps.kuaiai.services import scene_tools

    return scene_tools


def _dc():
    """document_chain 的 ``_perm_view`` 延迟借用（permissions_any 多码按
    持有码选 scope 资源键，与 stocktaking 视图级判权同模式）。"""
    from apps.kuaiai.services.tools import document_chain

    return document_chain


def _parse_date(value: Any):
    """YYYY-MM-DD → date；非法返回 None（复用 scene_tools 实现）。"""
    return _st()._parse_date(value)


def _opt_str(value: Any) -> Optional[str]:
    s = str(value or "").strip()
    return s or None


def _opt_bool(value: Any):
    """布尔参数归一：bool/"true"/"false"/1/0 → bool；None/"" → None；
    其他返回 ``False`` 哨兵由调用方判错。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    return _INVALID_BOOL


_INVALID_BOOL = object()


def _fetch_limit(limit: Any) -> int:
    """用户 limit（≤20）放大到过采样上限内，供范围过滤后仍够页。"""
    return min(max(_ct()._clamp_limit(limit) * 5, 50), _OVERSAMPLE_LIMIT)


def _trunc(text: Any, limit: int = _DESC_MAX) -> str:
    s = " ".join(str(text or "").split())
    if len(s) > limit:
        return s[:limit] + "…"
    return s


def _fmt_dt(value: Any) -> str:
    """datetime/date 展示：datetime 经 API 同口径站点时区文本，date 取 ISO 日。"""
    if value is None:
        return "未知"
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
    return s[:19] if s else "未知"


def _fmt_equipment_label(code: Any, name: Any) -> str:
    """设备编码/名称统一标签（spec 210 §2 共用；spec 204 页上下文复用）。

    ``EQ-001（3号注塑机）``；缺一段取有值的一段，全缺回「未命名设备」。
    """
    code_s = str(code or "").strip()
    name_s = str(name or "").strip()
    if code_s and name_s:
        return f"{code_s}（{name_s}）"
    return code_s or name_s or "未命名设备"


def _fmt_equipment_row(eq: Any) -> str:
    """设备台账行摘要（Tool 与页上下文 reader 共用口径，spec 204 预留）。"""
    parts = [
        f"设备 {_fmt_equipment_label(getattr(eq, 'code', None), getattr(eq, 'name', None))}：",
        f"状态 {getattr(eq, 'status', '') or '未知'}",
    ]
    nature = getattr(eq, "equipment_nature", None)
    if nature:
        parts.append(f"性质 {nature}")
    type_text = "/".join(
        p
        for p in (
            str(getattr(eq, "type", "") or "").strip(),
            str(getattr(eq, "category", "") or "").strip(),
        )
        if p
    )
    if type_text:
        parts.append(f"类型 {type_text}")
    site = " / ".join(
        p
        for p in (
            str(getattr(eq, "workshop_name", "") or "").strip(),
            str(getattr(eq, "production_line_name", "") or "").strip(),
            str(getattr(eq, "workstation_name", "") or "").strip(),
        )
        if p
    )
    if site:
        parts.append(f"位置 {site}")
    parts.append("启用" if getattr(eq, "is_active", True) else "已停用")
    return (
        "，".join(parts)
        + f"（uuid={getattr(eq, 'uuid', '')}，id={getattr(eq, 'id', '')}）"
    )


def _fmt_fault_row(f: Any) -> str:
    """设备故障行摘要（与 pulse 同一事实口径：级别/状态/发生时间）。"""
    return (
        f"故障单 {getattr(f, 'fault_no', '') or ''}："
        f"设备 {_fmt_equipment_label(getattr(f, 'equipment_code', None), getattr(f, 'equipment_name', None))}，"
        f"级别 {getattr(f, 'fault_level', '') or '未知'}，"
        f"类型 {getattr(f, 'fault_type', '') or '未知'}，"
        f"状态 {getattr(f, 'status', '') or '未知'}，"
        f"发生 {_fmt_dt(getattr(f, 'fault_date', None))}，"
        f"描述 {_trunc(getattr(f, 'fault_description', None)) or '未填写'}"
        f"（id={getattr(f, 'id', '')}）"
    )


def _fmt_repair_row(r: Any, code_map: Optional[Dict[str, str]] = None) -> str:
    """设备维修行摘要（不含维修费用金额字段）。"""
    code = (code_map or {}).get(str(getattr(r, "equipment_uuid", "") or ""))
    repair_result = getattr(r, "repair_result", None)
    tail = f"，结果 {repair_result}" if repair_result else ""
    duration = getattr(r, "repair_duration", None)
    duration_text = (
        f"，时长 {_ct()._fmt_num(duration)} 小时" if duration is not None else ""
    )
    return (
        f"维修单 {getattr(r, 'repair_no', '') or ''}："
        f"设备 {_fmt_equipment_label(code, getattr(r, 'equipment_name', None))}，"
        f"状态 {getattr(r, 'status', '') or '未知'}，"
        f"维修 {_fmt_dt(getattr(r, 'repair_date', None))}，"
        f"类型 {getattr(r, 'repair_type', '') or '未填'}，"
        f"维修人 {getattr(r, 'repairer_name', '') or '未填'}"
        f"{duration_text}{tail}，"
        f"内容 {_trunc(getattr(r, 'repair_description', None)) or '未填写'}"
        f"（id={getattr(r, 'id', '')}）"
    )


def _fmt_plan_row(p: Any) -> str:
    """维护保养计划行摘要。"""
    items = getattr(p, "equipment_items", None) or []
    count = len(items) if isinstance(items, list) else 0
    if count > 1:
        first = _fmt_equipment_label(
            (items[0] or {}).get("code"), (items[0] or {}).get("name")
        )
        eq_text = f"{first} 等{count}台"
    else:
        eq_text = _fmt_equipment_label(
            (items[0] or {}).get("code") if items else None,
            getattr(p, "equipment_name", None)
            or ((items[0] or {}).get("name") if items else None),
        )
    return (
        f"保养计划 {getattr(p, 'plan_no', '') or ''}"
        f"（{getattr(p, 'plan_name', '') or '未命名'}）："
        f"设备 {eq_text}，"
        f"方案 {getattr(p, 'scheme_name', '') or '未绑定'}，"
        f"类型 {getattr(p, 'plan_type', '') or '未知'}，"
        f"状态 {getattr(p, 'status', '') or '未知'}，"
        f"计划开始 {_fmt_dt(getattr(p, 'planned_start_date', None))}"
        f"（id={getattr(p, 'id', '')}）"
    )


def _fmt_execution_row(e: Any, code_map: Optional[Dict[str, str]] = None) -> str:
    """保养执行记录行摘要（不含维护成本金额字段）。"""
    code = (code_map or {}).get(str(getattr(e, "equipment_uuid", "") or ""))
    return (
        f"执行记录 {getattr(e, 'execution_no', '') or ''}："
        f"设备 {_fmt_equipment_label(code, getattr(e, 'equipment_name', None))}，"
        f"状态 {getattr(e, 'status', '') or '未知'}，"
        f"结果 {getattr(e, 'execution_result', '') or '未评'}，"
        f"执行 {_fmt_dt(getattr(e, 'execution_date', None))}，"
        f"执行人 {getattr(e, 'executor_name', '') or '未填'}"
        f"（id={getattr(e, 'id', '')}）"
    )


def _fmt_reminder_row(r: Any) -> str:
    """维护提醒行摘要。"""
    days = getattr(r, "days_until_due", None)
    try:
        d = int(days)
        due = f"已逾期 {abs(d)} 天" if d < 0 else f"{d} 天后到期"
    except (TypeError, ValueError):
        due = "到期天数未知"
    handled = "已处理" if getattr(r, "is_handled", False) else "未处理"
    read = "已读" if getattr(r, "is_read", False) else "未读"
    rtype = _DUE_TYPE_ZH.get(
        str(getattr(r, "reminder_type", "") or ""),
        str(getattr(r, "reminder_type", "") or "未知"),
    )
    return (
        f"设备 {_fmt_equipment_label(getattr(r, 'equipment_code', None), getattr(r, 'equipment_name', None))}："
        f"{rtype}，计划维护 {_fmt_dt(getattr(r, 'planned_maintenance_date', None))}，"
        f"{due}，{handled}/{read}，"
        f"提醒 {_fmt_dt(getattr(r, 'reminder_date', None))}"
        f"（id={getattr(r, 'id', '')}）"
    )


def _fmt_calibration_alert_row(r: Dict[str, Any]) -> str:
    """设备校准到期提醒行摘要（dict 行，service 已排逾期在前）。"""
    days = r.get("days_until_due")
    try:
        d = int(days)
        due = f"已逾期 {abs(d)} 天" if d < 0 else f"{d} 天后到期"
    except (TypeError, ValueError):
        due = "到期天数未知"
    return (
        f"设备 {_fmt_equipment_label(r.get('equipment_code'), r.get('equipment_name'))}："
        f"{_DUE_TYPE_ZH.get(str(r.get('due_type') or ''), str(r.get('due_type') or '未知'))}，"
        f"校准到期 {_fmt_dt(r.get('due_date'))}，{due}，"
        f"上次校准 {_fmt_dt(r.get('last_calibration_date'))}，"
        f"周期 {_ct()._fmt_num(r.get('calibration_period'))} 天"
    )


async def _resolve_equipment_uuid(
    ctx: AiRuntimeContext, equipment_uuid: Any, equipment_code: Any
):
    """``equipment_uuid`` 直传；``equipment_code`` 经 get_equipment_by_code
    解析。返回 (uuid_str or None, error_text or None)。"""
    eu = _opt_str(equipment_uuid)
    if eu:
        return eu, None
    ec = _opt_str(equipment_code)
    if not ec:
        return None, None
    from apps.kuaizhizao.services.equipment_service import EquipmentService

    eq = await EquipmentService.get_equipment_by_code(ctx.tenant_id, ec)
    if eq is None:
        return None, f"未查询到设备编码 {ec} 对应的设备"
    return str(getattr(eq, "uuid", "") or ""), None


async def _equipment_code_map(ctx: AiRuntimeContext, uuids: Set[str]) -> Dict[str, str]:
    """设备 uuid → 编码（维修/执行记录无 code 快照时补展示用）。"""
    uuids = {u for u in uuids if u}
    if not uuids:
        return {}
    from apps.kuaizhizao.models.equipment import Equipment

    rows = await Equipment.filter(
        tenant_id=ctx.tenant_id,
        uuid__in=list(uuids),
        deleted_at__isnull=True,
    ).values("uuid", "code")
    return {str(r.get("uuid") or ""): str(r.get("code") or "") for r in rows}


async def _equipment_id_map(ctx: AiRuntimeContext, uuids: Set[str]) -> Dict[str, int]:
    """设备 uuid → id（校准提醒 dict 行无 id，行级范围需经 id 收敛）。"""
    uuids = {u for u in uuids if u}
    if not uuids:
        return {}
    from apps.kuaizhizao.models.equipment import Equipment

    rows = await Equipment.filter(
        tenant_id=ctx.tenant_id,
        uuid__in=list(uuids),
        deleted_at__isnull=True,
    ).values("uuid", "id")
    return {
        str(r.get("uuid") or ""): int(r.get("id") or 0)
        for r in rows
        if r.get("id")
    }


async def query_equipment(
    keyword: Optional[str] = None,
    equipment_code: Optional[str] = None,
    status: Optional[str] = None,
    equipment_nature: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """设备台账摘要：编码/名称/状态/性质/车间产线，可按编码精查。

    数据范围：service 不接收 ``current_user``，行 id 套
    ``kuaizhizao:equipment-management-equipment`` 资源收敛。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    status_norm = _opt_str(status)
    if status_norm is not None and status_norm not in _EQUIPMENT_STATUSES:
        return "status 仅支持 正常/运行中/待机/故障/维修中/停用/校验中/报废"
    active = _opt_bool(is_active)
    if active is _INVALID_BOOL:
        return "is_active 仅支持 true/false"
    lim = _ct()._clamp_limit(limit)

    try:
        from apps.kuaizhizao.models.equipment import Equipment
        from apps.kuaizhizao.services.equipment_service import EquipmentService

        rows: List[Any] = []
        code = _opt_str(equipment_code)
        if code:
            eq = await EquipmentService.get_equipment_by_code(ctx.tenant_id, code)
            rows = [eq] if eq is not None else []
        else:
            rows, _total = await EquipmentService.list_equipment(
                ctx.tenant_id,
                skip=0,
                limit=_fetch_limit(limit),
                status=status_norm,
                equipment_nature=_opt_str(equipment_nature),
                is_active=active,
                keyword=_opt_str(keyword),
            )
        ids = {int(getattr(r, "id", 0) or 0) for r in rows if r is not None} - {0}
        visible = await _st()._scoped_row_ids(
            Equipment, ctx, _SCOPE_EQUIPMENT, ids
        )
        rows = [
            r
            for r in rows
            if r is not None and int(getattr(r, "id", 0) or 0) in visible
        ]
    except Exception as exc:
        logger.warning(
            "AI tool query_equipment 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询设备台账失败，请稍后重试"

    if not rows:
        return "当前用户数据范围内未查询到符合条件的设备"

    top = rows[:lim]
    lines = [
        f"共 {len(rows)} 台设备（当前用户数据范围内，上限内计），"
        f"返回前 {len(top)} 台："
    ]
    for eq in top:
        lines.append(_fmt_equipment_row(eq))
    return "\n".join(lines)


async def query_equipment_faults(
    view: str = "faults",
    equipment_uuid: Optional[str] = None,
    equipment_code: Optional[str] = None,
    status: Optional[str] = None,
    fault_level: Optional[str] = None,
    keyword: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """设备故障/维修摘要（view=faults 故障单 / view=repairs 维修台账）。

    两视图同权限码 ``kuaizhizao:equipment-fault:read``；行级范围套
    ``kuaizhizao:equipment-fault`` 资源。不输出维修费用。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    resolved_view = str(view or "faults").strip()
    if resolved_view not in _FAULT_VIEWS:
        return "view 仅支持 faults|repairs"
    status_norm = _opt_str(status)
    allowed_status = (
        _FAULT_STATUSES if resolved_view == "faults" else _REPAIR_STATUSES
    )
    if status_norm is not None and status_norm not in allowed_status:
        if resolved_view == "faults":
            return "status 仅支持 待处理/处理中/已修复/已关闭"
        return "status 仅支持 进行中/已完成/已取消"
    level = _opt_str(fault_level)
    if level is not None and level not in _FAULT_LEVELS:
        return "fault_level 仅支持 轻微/一般/严重/紧急"
    start_d = _parse_date(date_start) if date_start else None
    if date_start and start_d is None:
        return "date_start 须为 YYYY-MM-DD 格式的日期"
    end_d = _parse_date(date_end) if date_end else None
    if date_end and end_d is None:
        return "date_end 须为 YYYY-MM-DD 格式的日期"
    lim = _ct()._clamp_limit(limit)

    try:
        eu, err = await _resolve_equipment_uuid(
            ctx, equipment_uuid, equipment_code
        )
        if err:
            return err
        if resolved_view == "faults":
            from apps.kuaizhizao.models.equipment_fault import EquipmentFault
            from apps.kuaizhizao.services.equipment_fault_service import (
                EquipmentFaultService,
            )

            rows, _total = await EquipmentFaultService.list_equipment_faults(
                ctx.tenant_id,
                skip=0,
                limit=_fetch_limit(limit),
                equipment_uuid=eu,
                status=status_norm,
                fault_type=None,
                keyword=_opt_str(keyword),
                fault_start_date=start_d,
                fault_end_date=end_d,
            )
            if level:
                rows = [
                    r for r in rows if getattr(r, "fault_level", None) == level
                ]
            visible = await _st()._scoped_row_ids(
                EquipmentFault,
                ctx,
                _SCOPE_EQUIPMENT_FAULT,
                {int(getattr(r, "id", 0) or 0) for r in rows} - {0},
            )
            rows = [
                r for r in rows if int(getattr(r, "id", 0) or 0) in visible
            ]
        else:
            from apps.kuaizhizao.models.equipment_fault import EquipmentRepair
            from apps.kuaizhizao.services.equipment_fault_service import (
                EquipmentRepairService,
            )

            rows, _total = await EquipmentRepairService.list_equipment_repairs(
                ctx.tenant_id,
                skip=0,
                limit=_fetch_limit(limit),
                equipment_uuid=eu,
                status=status_norm,
                keyword=_opt_str(keyword),
                repair_start_date=start_d,
                repair_end_date=end_d,
            )
            visible = await _st()._scoped_row_ids(
                EquipmentRepair,
                ctx,
                _SCOPE_EQUIPMENT_FAULT,
                {int(getattr(r, "id", 0) or 0) for r in rows} - {0},
            )
            rows = [
                r for r in rows if int(getattr(r, "id", 0) or 0) in visible
            ]
    except Exception as exc:
        logger.warning(
            "AI tool query_equipment_faults 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询设备故障/维修记录失败，请稍后重试"

    if not rows:
        if resolved_view == "faults":
            return "当前用户数据范围内未查询到符合条件的设备故障记录"
        return "当前用户数据范围内未查询到符合条件的设备维修记录"

    top = rows[:lim]
    if resolved_view == "faults":
        lines = [
            f"共 {len(rows)} 条设备故障记录（当前用户数据范围内，上限内计），"
            f"返回前 {len(top)} 条："
        ]
        for r in top:
            lines.append(_fmt_fault_row(r))
        return "\n".join(lines)

    try:
        code_map = await _equipment_code_map(
            ctx, {str(getattr(r, "equipment_uuid", "") or "") for r in top}
        )
    except Exception:
        code_map = {}
    lines = [
        f"共 {len(rows)} 条设备维修记录（当前用户数据范围内，上限内计），"
        f"返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(_fmt_repair_row(r, code_map))
    return "\n".join(lines)


async def query_maintenance_plans(
    view: str = "plans",
    equipment_uuid: Optional[str] = None,
    equipment_code: Optional[str] = None,
    status: Optional[str] = None,
    plan_type: Optional[str] = None,
    execution_result: Optional[str] = None,
    keyword: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """维护保养计划/执行摘要（view=plans 计划 / view=executions 执行记录）。

    行级范围套 ``kuaizhizao:maintenance-plan`` 资源（保养执行记录页同码）。
    日期口径：plans 按计划开始日期、executions 按执行日期。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    resolved_view = str(view or "plans").strip()
    if resolved_view not in _PLAN_VIEWS:
        return "view 仅支持 plans|executions"
    status_norm = _opt_str(status)
    if resolved_view == "plans":
        if status_norm is not None and status_norm not in _PLAN_STATUSES:
            return "status 仅支持 草稿/已发布/执行中/已完成/已取消"
    else:
        if status_norm is not None and status_norm not in _EXECUTION_STATUSES:
            return "status 仅支持 草稿/已确认/已验收"
    ptype = _opt_str(plan_type)
    if ptype is not None and ptype not in _PLAN_TYPES:
        return "plan_type 仅支持 预防性维护/定期维护/临时维护"
    eresult = _opt_str(execution_result)
    if eresult is not None and eresult not in _EXECUTION_RESULTS:
        return "execution_result 仅支持 正常/异常/待处理"
    start_d = _parse_date(date_start) if date_start else None
    if date_start and start_d is None:
        return "date_start 须为 YYYY-MM-DD 格式的日期"
    end_d = _parse_date(date_end) if date_end else None
    if date_end and end_d is None:
        return "date_end 须为 YYYY-MM-DD 格式的日期"
    lim = _ct()._clamp_limit(limit)

    try:
        eu, err = await _resolve_equipment_uuid(
            ctx, equipment_uuid, equipment_code
        )
        if err:
            return err
        if resolved_view == "plans":
            from apps.kuaizhizao.models.maintenance_plan import MaintenancePlan
            from apps.kuaizhizao.services.maintenance_plan_service import (
                MaintenancePlanService,
            )

            rows, _total = await MaintenancePlanService.list_maintenance_plans(
                ctx.tenant_id,
                skip=0,
                limit=_fetch_limit(limit),
                equipment_uuid=eu,
                status=status_norm,
                plan_type=ptype,
                keyword=_opt_str(keyword),
                planned_start_date=start_d,
                planned_end_date=end_d,
            )
            visible = await _st()._scoped_row_ids(
                MaintenancePlan,
                ctx,
                _SCOPE_MAINTENANCE_PLAN,
                {int(getattr(r, "id", 0) or 0) for r in rows} - {0},
            )
            rows = [
                r for r in rows if int(getattr(r, "id", 0) or 0) in visible
            ]
        else:
            from apps.kuaizhizao.models.maintenance_plan import (
                MaintenanceExecution,
            )
            from apps.kuaizhizao.services.maintenance_plan_service import (
                MaintenanceExecutionService,
            )

            rows, _total = await MaintenanceExecutionService.list_maintenance_executions(
                ctx.tenant_id,
                skip=0,
                limit=_fetch_limit(limit),
                equipment_uuid=eu,
                status=status_norm,
                execution_result=eresult,
                keyword=_opt_str(keyword),
                execution_start_date=start_d,
                execution_end_date=end_d,
            )
            visible = await _st()._scoped_row_ids(
                MaintenanceExecution,
                ctx,
                _SCOPE_MAINTENANCE_PLAN,
                {int(getattr(r, "id", 0) or 0) for r in rows} - {0},
            )
            rows = [
                r for r in rows if int(getattr(r, "id", 0) or 0) in visible
            ]
    except Exception as exc:
        logger.warning(
            "AI tool query_maintenance_plans 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询保养计划/执行记录失败，请稍后重试"

    if not rows:
        if resolved_view == "plans":
            return "当前用户数据范围内未查询到符合条件的保养计划"
        return "当前用户数据范围内未查询到符合条件的保养执行记录"

    top = rows[:lim]
    if resolved_view == "plans":
        lines = [
            f"共 {len(rows)} 条保养计划（当前用户数据范围内，上限内计），"
            f"返回前 {len(top)} 条："
        ]
        for r in top:
            lines.append(_fmt_plan_row(r))
        return "\n".join(lines)

    try:
        code_map = await _equipment_code_map(
            ctx, {str(getattr(r, "equipment_uuid", "") or "") for r in top}
        )
    except Exception:
        code_map = {}
    lines = [
        f"共 {len(rows)} 条保养执行记录（当前用户数据范围内，上限内计），"
        f"返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(_fmt_execution_row(r, code_map))
    return "\n".join(lines)


async def query_maintenance_reminders(
    reminder_type: Optional[str] = None,
    is_handled: Optional[bool] = None,
    is_read: Optional[bool] = None,
    equipment_uuid: Optional[str] = None,
    equipment_code: Optional[str] = None,
    keyword: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """设备维护（保养）到期提醒摘要：设备/类型/计划维护日/逾期天数/处理状态。

    行级范围套 ``kuaizhizao:maintenance-reminder`` 资源。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    rtype = _opt_str(reminder_type)
    if rtype is not None and rtype not in _DUE_TYPES:
        return "reminder_type 仅支持 due_soon/overdue"
    handled = _opt_bool(is_handled)
    if handled is _INVALID_BOOL:
        return "is_handled 仅支持 true/false"
    read = _opt_bool(is_read)
    if read is _INVALID_BOOL:
        return "is_read 仅支持 true/false"
    start_d = _parse_date(date_start) if date_start else None
    if date_start and start_d is None:
        return "date_start 须为 YYYY-MM-DD 格式的日期"
    end_d = _parse_date(date_end) if date_end else None
    if date_end and end_d is None:
        return "date_end 须为 YYYY-MM-DD 格式的日期"
    lim = _ct()._clamp_limit(limit)

    try:
        eu, err = await _resolve_equipment_uuid(
            ctx, equipment_uuid, equipment_code
        )
        if err:
            return err
        from apps.kuaizhizao.models.maintenance_reminder import (
            MaintenanceReminder,
        )
        from apps.kuaizhizao.services.maintenance_reminder_service import (
            MaintenanceReminderService,
        )

        rows, _total = await MaintenanceReminderService().list_reminders(
            ctx.tenant_id,
            skip=0,
            limit=_fetch_limit(limit),
            reminder_type=rtype,
            is_read=read,
            is_handled=handled,
            equipment_uuid=eu,
            keyword=_opt_str(keyword),
            reminder_start_date=start_d,
            reminder_end_date=end_d,
        )
        visible = await _st()._scoped_row_ids(
            MaintenanceReminder,
            ctx,
            _SCOPE_MAINTENANCE_REMINDER,
            {int(getattr(r, "id", 0) or 0) for r in rows} - {0},
        )
        rows = [
            r for r in rows if int(getattr(r, "id", 0) or 0) in visible
        ]
    except Exception as exc:
        logger.warning(
            "AI tool query_maintenance_reminders 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询维护提醒失败，请稍后重试"

    if not rows:
        return "当前用户数据范围内未查询到符合条件的维护提醒"

    top = rows[:lim]
    lines = [
        f"共 {len(rows)} 条维护提醒（当前用户数据范围内，上限内计），"
        f"返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(_fmt_reminder_row(r))
    return "\n".join(lines)


async def query_calibration_alerts(
    due_type: Optional[str] = None,
    equipment_nature: Optional[str] = None,
    equipment_keyword: Optional[str] = None,
    limit: int = 10,
    ctx: Optional[AiRuntimeContext] = None,
) -> str:
    """设备校准（检定）到期提醒摘要：设备/到期类型/到期日/剩余天数/周期。

    数据为 ``EquipmentService.list_calibration_alerts`` 的 dict 行
    （``needs_calibration`` 设备按租户提前天数窗口过滤，逾期在前）；
    行级范围按设备 id 套 ``kuaizhizao:maintenance-reminder`` 资源
    （对应页面接口 /equipment/calibration-reminders 的权限码）。
    """
    ctx = _ct()._resolve_ctx(ctx)
    if not _ct()._ctx_ok(ctx):
        return _ERR_NO_CONTEXT
    dtype = _opt_str(due_type)
    if dtype is not None and dtype not in _DUE_TYPES:
        return "due_type 仅支持 due_soon/overdue"
    kw = _opt_str(equipment_keyword)
    lim = _ct()._clamp_limit(limit)

    try:
        from apps.kuaizhizao.services.equipment_service import EquipmentService

        rows, _total = await EquipmentService.list_calibration_alerts(
            ctx.tenant_id,
            skip=0,
            limit=_OVERSAMPLE_LIMIT,
            due_type=dtype,
            equipment_nature=_opt_str(equipment_nature),
        )
        rows = list(rows or [])
        if kw:
            kw_l = kw.lower()
            rows = [
                r
                for r in rows
                if kw_l
                in (
                    str(r.get("equipment_code") or "")
                    + " "
                    + str(r.get("equipment_name") or "")
                ).lower()
            ]
        # dict 行只有 equipment_uuid：经设备 id 套行级范围
        id_map = await _equipment_id_map(
            ctx,
            {str(r.get("equipment_uuid") or "") for r in rows},
        )
        if rows:
            from apps.kuaizhizao.models.equipment import Equipment

            # permissions_any 双码：按持有码选对应 scope 资源键
            admin, codes = await _dc()._perm_view(ctx)
            scope_key = next(
                (
                    key
                    for code, key in _CALIBRATION_PERM_SCOPES.items()
                    if admin or code in codes
                ),
                _SCOPE_MAINTENANCE_REMINDER,
            )
            visible = await _st()._scoped_row_ids(
                Equipment,
                ctx,
                scope_key,
                {v for v in id_map.values() if v},
            )
            rows = [
                r
                for r in rows
                if id_map.get(str(r.get("equipment_uuid") or "")) in visible
            ]
    except Exception as exc:
        logger.warning(
            "AI tool query_calibration_alerts 失败 error_type={}",
            type(exc).__name__,
        )
        return "查询设备校准到期提醒失败，请稍后重试"

    if not rows:
        return "当前用户数据范围内未查询到设备校准到期提醒"

    top = rows[:lim]
    lines = [
        f"共 {len(rows)} 条设备校准到期提醒（当前用户数据范围内，上限内计），"
        f"返回前 {len(top)} 条："
    ]
    for r in top:
        lines.append(_fmt_calibration_alert_row(r))
    return "\n".join(lines)
