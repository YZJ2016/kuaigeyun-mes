"""排产策略包：加权规则码，不引入独立求解器。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# 交期优先（默认） / 换线最少 / 均衡负荷
STRATEGY_DUE_DATE = "due_date"
STRATEGY_CHANGEOVER_MIN = "changeover_min"
STRATEGY_LOAD_BALANCE = "load_balance"

STRATEGY_CODES: Tuple[str, ...] = (
    STRATEGY_DUE_DATE,
    STRATEGY_CHANGEOVER_MIN,
    STRATEGY_LOAD_BALANCE,
)

STRATEGY_CATALOG: List[Dict[str, Any]] = [
    {
        "code": STRATEGY_DUE_DATE,
        "name": "交期优先",
        "description": "逾期与交期紧迫优先，其次优先级与综合评分",
    },
    {
        "code": STRATEGY_CHANGEOVER_MIN,
        "name": "换线最少",
        "description": "同产品连续排产，降低换型；交期仍作为次级键",
    },
    {
        "code": STRATEGY_LOAD_BALANCE,
        "name": "均衡负荷",
        "description": "交期排序不变，指派资源时优先选当前占用更少的产线/工位",
    },
]


def normalize_strategy(raw: str | None) -> str:
    """空值默认交期优先；未知码显式失败，禁止静默改写。"""
    if raw is None or not str(raw).strip():
        return STRATEGY_DUE_DATE
    code = str(raw).strip().lower()
    if code not in STRATEGY_CODES:
        raise ValueError(
            f"未知排产策略「{raw}」，允许: {', '.join(STRATEGY_CODES)}"
        )
    return code


def strategy_label(code: str) -> str:
    for item in STRATEGY_CATALOG:
        if item["code"] == code:
            return str(item["name"])
    return STRATEGY_CATALOG[0]["name"]
