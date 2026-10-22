"""造数场景拆段：可单独跑，也可串联成全链路。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

ScenarioId = Literal[
    "mrp_push",
    "purchase_inbound",
    "wo_complete",
    "owo_fulfill",
    "ship",
]

FULL_CHAIN_SCENARIOS: tuple[ScenarioId, ...] = (
    "mrp_push",
    "purchase_inbound",
    "owo_fulfill",
    "wo_complete",
    "ship",
)


@dataclass(frozen=True)
class ScenarioDef:
    id: ScenarioId
    label: str
    # 对应 FlowGenerateRequest.steps 中相关开关的并集提示
    step_keys: tuple[str, ...]


SCENARIO_DEFS: dict[ScenarioId, ScenarioDef] = {
    "mrp_push": ScenarioDef(
        id="mrp_push",
        label="需求计算与下推",
        # 下推采购单由引擎在本场景内 enable_purchase_push，不复用 purchase 入库开关
        step_keys=("demand_computation",),
    ),
    "purchase_inbound": ScenarioDef(
        id="purchase_inbound",
        label="采购审核入库",
        step_keys=("purchase", "incoming_inspection"),
    ),
    "owo_fulfill": ScenarioDef(
        id="owo_fulfill",
        label="委外发料收货",
        step_keys=("outsource",),
    ),
    "wo_complete": ScenarioDef(
        id="wo_complete",
        label="工单生产链完工",
        step_keys=(
            "inventory_topup",
            "production_picking",
            "reporting",
            "process_inspection",
            "finished_goods_inspection",
            "finished_goods_receipt",
        ),
    ),
    "ship": ScenarioDef(
        id="ship",
        label="发货出库",
        step_keys=("shipment_delivery",),
    ),
}


def resolve_scenario_ids(
    raw: Optional[Sequence[str]],
    *,
    default_full_chain: bool = True,
) -> list[ScenarioId]:
    """解析场景列表；空则全链路。"""
    if not raw:
        return list(FULL_CHAIN_SCENARIOS) if default_full_chain else []
    out: list[ScenarioId] = []
    seen: set[str] = set()
    for item in raw:
        key = str(item or "").strip().lower()
        if key in ("full", "all", "full_chain", "全链路"):
            return list(FULL_CHAIN_SCENARIOS)
        if key not in SCENARIO_DEFS or key in seen:
            continue
        seen.add(key)
        out.append(key)  # type: ignore[arg-type]
    return out or list(FULL_CHAIN_SCENARIOS)


def scenario_progress_span(index: int, total: int) -> tuple[int, int]:
    """把全局 0–100 进度切成各场景区间。"""
    total = max(1, int(total))
    index = max(0, min(index, total - 1))
    lo = int(100 * index / total)
    hi = int(100 * (index + 1) / total)
    return lo, max(lo + 1, hi)
