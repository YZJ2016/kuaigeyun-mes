"""流程造数真实 MES 仿真：场景剧本 + 单一时钟 + 薄编排。

真实模式（real）：工作时段 + 标准工时，禁止 flow_end_at 压缩与强制简易质检。
填数模式（fill）：才允许时间窗均摊 / allow_skip_iqc。
"""

from apps.kuaizhizao.services.flow_sim.clock import BusinessClock
from apps.kuaizhizao.services.flow_sim.kit import KitPrecheckResult, precheck_simulation_kit
from apps.kuaizhizao.services.flow_sim.modes import SimMode, normalize_sim_mode
from apps.kuaizhizao.services.flow_sim.scenarios import (
    FULL_CHAIN_SCENARIOS,
    SCENARIO_DEFS,
    ScenarioId,
    resolve_scenario_ids,
)

__all__ = [
    "BusinessClock",
    "FULL_CHAIN_SCENARIOS",
    "KitPrecheckResult",
    "SCENARIO_DEFS",
    "ScenarioId",
    "SimMode",
    "normalize_sim_mode",
    "precheck_simulation_kit",
    "resolve_scenario_ids",
]
