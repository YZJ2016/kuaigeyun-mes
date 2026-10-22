"""薄编排引擎：场景串联、时钟工厂、模式门禁。

业务步骤仍由 FlowDataGenerateService 内既有 Service 调用完成；
本模块只负责「先用哪套时钟 / 跑哪些场景段 / 模式禁什么」。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence

from apps.kuaizhizao.services.flow_sim.clock import BusinessClock, IntervalSpec
from apps.kuaizhizao.services.flow_sim.modes import (
    SimMode,
    is_allow_skip_iqc_effective,
    is_budget_time_allowed,
    is_force_simple_allowed,
    normalize_sim_mode,
)
from apps.kuaizhizao.services.flow_sim.scenarios import (
    FULL_CHAIN_SCENARIOS,
    ScenarioId,
    resolve_scenario_ids,
    scenario_progress_span,
)
from core.services.document_time_rewrite_service import WorkScheduleParams


def build_clock(
    *,
    mode: SimMode,
    anchor: datetime,
    default_min: int,
    default_max: int,
    intervals: dict[str, tuple[int, int]],
    work_schedule: Optional[WorkScheduleParams] = None,
    use_work_schedule: bool = False,
    flow_end_at: Optional[datetime] = None,
    remaining_events: Optional[int] = None,
) -> BusinessClock:
    """preview/execute 共用：真实模式永不挂 deadline。"""
    default_interval = IntervalSpec(default_min, default_max)
    specs = {
        k: IntervalSpec(v[0], v[1]) for k, v in intervals.items()
    }
    allow_budget = is_budget_time_allowed(mode)
    deadline = flow_end_at if allow_budget else None
    remain = remaining_events if allow_budget and deadline is not None else None
    return BusinessClock.build(
        anchor=anchor,
        default_interval=default_interval,
        intervals=specs,
        work_schedule=work_schedule,
        use_work_schedule=use_work_schedule,
        deadline=deadline,
        remaining_events=remain,
        allow_budget=allow_budget,
    )


def apply_mode_gates(req: Any) -> dict[str, Any]:
    """按 sim_mode 改写请求侧效应开关；返回审计字段。"""
    mode = normalize_sim_mode(getattr(req, "sim_mode", None))
    setattr(req, "sim_mode", mode)
    scenarios = resolve_scenario_ids(getattr(req, "scenarios", None))
    setattr(req, "scenarios", scenarios)

    allow_budget = is_budget_time_allowed(mode)
    if not allow_budget:
        setattr(req, "flow_end_at", None)

    skip = is_allow_skip_iqc_effective(
        mode, bool(getattr(req, "allow_skip_iqc", False))
    )
    setattr(req, "allow_skip_iqc", skip)

    force_simple = is_force_simple_allowed(mode)
    return {
        "sim_mode": mode,
        "scenarios": list(scenarios),
        "budget_time_allowed": allow_budget,
        "allow_skip_iqc": skip,
        "force_simple_when_unset": force_simple,
    }


def map_steps_for_scenarios(
    scenarios: Sequence[ScenarioId],
    *,
    base_steps: Optional[dict[str, bool]] = None,
) -> dict[str, bool]:
    """场景为唯一步骤真源：只打开场景并集中的 step。

    base_steps 仅作兼容入参，不再用页面勾选覆盖场景（避免双轨）。
    """
    from apps.kuaizhizao.services.flow_sim.scenarios import SCENARIO_DEFS

    _ = base_steps  # 兼容旧调用方，故意忽略
    enabled_keys: set[str] = set()
    for sid in scenarios:
        defn = SCENARIO_DEFS.get(sid)
        if defn:
            enabled_keys.update(defn.step_keys)
    all_keys = {
        "demand_computation",
        "purchase",
        "incoming_inspection",
        "outsource",
        "inventory_topup",
        "production_picking",
        "reporting",
        "process_inspection",
        "finished_goods_inspection",
        "finished_goods_receipt",
        "shipment_delivery",
    }
    return {key: key in enabled_keys for key in all_keys}


def scenario_phase_message(scenario_id: ScenarioId, detail: str) -> str:
    from apps.kuaizhizao.services.flow_sim.scenarios import SCENARIO_DEFS

    label = SCENARIO_DEFS.get(scenario_id, None)
    name = label.label if label else scenario_id
    return f"[{name}] {detail}"


__all__ = [
    "FULL_CHAIN_SCENARIOS",
    "apply_mode_gates",
    "build_clock",
    "map_steps_for_scenarios",
    "scenario_phase_message",
    "scenario_progress_span",
]
