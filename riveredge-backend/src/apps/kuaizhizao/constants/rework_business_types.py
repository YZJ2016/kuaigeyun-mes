"""R-11 返工业务类型（通用码，禁止客户专名）。"""

from __future__ import annotations

from typing import List, Optional, Tuple

from apps.kuaizhizao.constants.rework_signoff_chain import REWORK_SIGNOFF_CHAIN_AA

# 多部门会签型：走审批节点链
REWORK_BUSINESS_MULTI_SIGNOFF = "multi_signoff"
# 简化执行型：制造闭环（现有默认）
REWORK_BUSINESS_SIMPLE_EXEC = "simple_exec"
# R-07 库存验证：会签型流程 + 客户展示/PQC 汇总扩展字段
REWORK_BUSINESS_INVENTORY_VERIFY = "inventory_verify"

REWORK_BUSINESS_TYPES = frozenset(
    {
        REWORK_BUSINESS_MULTI_SIGNOFF,
        REWORK_BUSINESS_SIMPLE_EXEC,
        REWORK_BUSINESS_INVENTORY_VERIFY,
    }
)

REWORK_BUSINESS_TYPE_DEFAULT = REWORK_BUSINESS_SIMPLE_EXEC

SIGNOFF_REWORK_BUSINESS_TYPES = frozenset(
    {REWORK_BUSINESS_MULTI_SIGNOFF, REWORK_BUSINESS_INVENTORY_VERIFY}
)


def is_signoff_rework_business(business_type: Optional[str]) -> bool:
    return (business_type or "").strip().lower() in SIGNOFF_REWORK_BUSINESS_TYPES


# A-A 默认链。A-B 见 rework_signoff_chain.REWORK_SIGNOFF_CHAIN_AB。编排只认该模块。
REWORK_SIGNOFF_DEPT_DEFAULTS: List[Tuple[str, str]] = list(REWORK_SIGNOFF_CHAIN_AA)
