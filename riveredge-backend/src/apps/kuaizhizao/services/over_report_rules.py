"""
超报规则：多层级合并后得到允许的最大累计完成数量（相对工单计划数量）。

合并顺序（后者在非 none 时覆盖前者；工艺路线序列项、工单工序行若显式传键则始终覆盖）：
物料 → 工序档案 → 路线默认 → 路线序列项 → 工单头 → 工单工序行
"""

from decimal import Decimal
from typing import Any, Optional, Tuple

OVER_REPORT_NONE = "none"
OVER_REPORT_FIXED = "fixed"
OVER_REPORT_PERCENT = "percent"


def normalize_over_report_mode(mode: Optional[str]) -> str:
    if not mode:
        return OVER_REPORT_NONE
    m = str(mode).lower().strip()
    if m in (OVER_REPORT_NONE, OVER_REPORT_FIXED, OVER_REPORT_PERCENT):
        return m
    return OVER_REPORT_NONE


def to_decimal(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def tuple_from_model(obj: Any, mode_attr: str = "over_report_mode", value_attr: str = "over_report_value") -> Tuple[str, Decimal]:
    if obj is None:
        return OVER_REPORT_NONE, Decimal("0")
    m = normalize_over_report_mode(getattr(obj, mode_attr, None) or OVER_REPORT_NONE)
    v = to_decimal(getattr(obj, value_attr, None))
    return m, v


def is_line_over_report_explicit(fields_set: Any, mode: Any, value: Any) -> bool:
    """
    工序行是否「显式覆盖」上层超报。

    前端常把默认 none/0 一并写入 payload，若仅凭 fields_set 判显式，
    会把工单头/路线 percent|fixed 盖成 none，导致头上配置了超报却不能报。
    仅当行上模式为 fixed/percent 时才视为显式覆盖。
    """
    if not fields_set:
        return False
    if not (set(fields_set) & {"over_report_mode", "over_report_value"}):
        return False
    return normalize_over_report_mode(mode) != OVER_REPORT_NONE


def effective_over_report_for_reporting(
    work_order: Any,
    work_order_operation: Any,
) -> Tuple[str, Decimal]:
    """
    报工上限：优先工序行快照；行为 none 时回落工单头。

    与开单 merge 一致：行默认 none 表示继承，不是「强制不允许超报」。
    若头也为 none，调用方可用 resolve_effective_over_report_async 再回落工序档案。
    """
    om, ov = tuple_from_model(work_order_operation)
    if om != OVER_REPORT_NONE:
        return om, ov
    return tuple_from_model(work_order)


async def resolve_effective_over_report_async(
    tenant_id: int,
    work_order: Any,
    work_order_operation: Any,
) -> Tuple[str, Decimal]:
    """
    报工有效超报：工序行 → 工单头 → 工序档案（GX 等主数据）。

    开单若误把行快照写成 none，仍认工序档案上的 percent/fixed。
    """
    om, ov = effective_over_report_for_reporting(work_order, work_order_operation)
    if om != OVER_REPORT_NONE:
        return om, ov
    mid = getattr(work_order_operation, "operation_id", None)
    if not mid:
        return om, ov
    try:
        from apps.master_data.models.process import Operation

        master = await Operation.get_or_none(
            id=int(mid),
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        )
    except Exception:
        return om, ov
    return tuple_from_model(master)


def extra_has_over_report_keys(extra: Any) -> bool:
    if not isinstance(extra, dict):
        return False
    return "over_report_mode" in extra or "overReportMode" in extra


def is_route_step_over_report_explicit(extra: Any) -> bool:
    """路线步骤仅当显式配了 fixed/percent 才覆盖工序档案；默认 none 键不盖档案。"""
    if not extra_has_over_report_keys(extra):
        return False
    mode, _ = parse_over_report_from_extra(extra)
    return mode != OVER_REPORT_NONE


def parse_over_report_from_extra(extra: Any) -> Tuple[str, Decimal]:
    if not isinstance(extra, dict):
        return OVER_REPORT_NONE, Decimal("0")
    mode = extra.get("over_report_mode")
    if mode is None:
        mode = extra.get("overReportMode")
    raw_val = extra.get("over_report_value")
    if raw_val is None:
        raw_val = extra.get("overReportValue")
    return normalize_over_report_mode(mode), to_decimal(raw_val)


def merge_over_report_layers(
    material: Tuple[str, Decimal],
    master_op: Tuple[str, Decimal],
    route_default: Tuple[str, Decimal],
    route_step: Tuple[str, Decimal],
    route_step_explicit: bool,
    wo_header: Tuple[str, Decimal],
    line: Tuple[str, Decimal],
    line_explicit: bool,
) -> Tuple[str, Decimal]:
    m, v = normalize_over_report_mode(material[0]), to_decimal(material[1])
    for lm, lv in (master_op, route_default):
        nm = normalize_over_report_mode(lm)
        if nm != OVER_REPORT_NONE:
            m, v = nm, to_decimal(lv)
    if route_step_explicit:
        m, v = normalize_over_report_mode(route_step[0]), to_decimal(route_step[1])
    else:
        nm = normalize_over_report_mode(route_step[0])
        if nm != OVER_REPORT_NONE:
            m, v = nm, to_decimal(route_step[1])
    nm = normalize_over_report_mode(wo_header[0])
    if nm != OVER_REPORT_NONE:
        m, v = nm, to_decimal(wo_header[1])
    if line_explicit:
        m, v = normalize_over_report_mode(line[0]), to_decimal(line[1])
    else:
        nm = normalize_over_report_mode(line[0])
        if nm != OVER_REPORT_NONE:
            m, v = nm, to_decimal(line[1])
    return m, v


def clamp_over_report_value_for_mode(mode: str, value: Any) -> Decimal:
    """percent 模式按百分数 0–100 解释；异常大值（如误填 10000）钳制到 100。"""
    md = normalize_over_report_mode(mode)
    v = to_decimal(value)
    if md == OVER_REPORT_PERCENT:
        if v > Decimal("100"):
            return Decimal("100")
        if v < Decimal("0"):
            return Decimal("0")
    elif md == OVER_REPORT_FIXED:
        if v < Decimal("0"):
            return Decimal("0")
    return v


def validate_over_report_value_for_mode(mode: Optional[str], value: Any) -> Decimal:
    """写入校验：percent 须为 0–100 百分数；值不可为负。返回规范化后的 Decimal。"""
    md = normalize_over_report_mode(mode)
    v = to_decimal(value)
    if v < 0:
        raise ValueError("超报值不能为负数")
    if md == OVER_REPORT_PERCENT and v > Decimal("100"):
        raise ValueError("按比例超报时，超报值须在 0–100 之间（百分数）")
    return v


def max_completed_quantity_for_plan(plan_qty: Any, mode: str, value: Decimal) -> Decimal:
    plan = to_decimal(plan_qty)
    if plan < 0:
        plan = Decimal("0")
    md = normalize_over_report_mode(mode)
    if md == OVER_REPORT_NONE:
        return plan
    if md == OVER_REPORT_FIXED:
        return plan + clamp_over_report_value_for_mode(md, value)
    if md == OVER_REPORT_PERCENT:
        pct = clamp_over_report_value_for_mode(md, value)
        extra = plan * pct / Decimal("100")
        return plan + extra.quantize(Decimal("0.01"))
    return plan


def status_reporting_target_quantity(work_order: Any, work_order_operation: Any) -> Decimal:
    """按状态报工标记完成时，本道工序应达到的累计完成/合格数量（含超报上限）。"""
    plan_qty = to_decimal(getattr(work_order, "quantity", None))
    om, ov = effective_over_report_for_reporting(work_order, work_order_operation)
    return max_completed_quantity_for_plan(plan_qty, om, ov)


def status_reporting_complete_delta(work_order: Any, work_order_operation: Any) -> Decimal:
    """按状态报工标记完成时，本次应报工数量（距累计上限的剩余量）。"""
    target = status_reporting_target_quantity(work_order, work_order_operation)
    current = to_decimal(getattr(work_order_operation, "completed_quantity", None))
    return max(Decimal("0"), target - current)


def remaining_completed_headroom(
    plan_qty: Any,
    current_completed: Any,
    mode: str,
    value: Decimal,
) -> Decimal:
    """数量报工：距「计划+超报」累计完成上限的剩余可报量（不含质检补报突破上限）。"""
    cap = max_completed_quantity_for_plan(plan_qty, mode, value)
    current = to_decimal(current_completed)
    return max(Decimal("0"), cap - current)


def first_operation_material_incoming(
    plan_qty: Any,
    work_order_operation: Any = None,
    work_order: Any = None,
) -> Decimal:
    """
    首道在制起点：仅工单计划数量。

    超报只抬高报工累计完成上限，不默认抬高在制/剩余物料；
    超报段须靠正式领料（含补料过账）在工单侧堆高可支撑产量后叠加（见
    WorkOrderService.resolve_material_incoming_picking_extra_units）。
    """
    _ = (work_order_operation, work_order)
    plan = to_decimal(plan_qty)
    if plan < 0:
        plan = Decimal("0")
    return plan
