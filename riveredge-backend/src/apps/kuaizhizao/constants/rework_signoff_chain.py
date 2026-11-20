"""会签返工节点链（客户原文唯一顺序，禁止再用 form_sections 冒充流转）。"""

from __future__ import annotations

from typing import Any, List, Mapping, Tuple

from apps.kuaizhizao.constants.rework_signoff_sections import (
    MULTI_SECTION_NODE_KEYS,
    POSITION_REVIEW_SUB_SECTIONS,
    REWORK_EXEC_SUB_SECTIONS,
)

NodeDef = Tuple[str, str]

SIGNOFF_FLOW_KEY = "signoff_flow"
SIGNOFF_CHAIN_VERSION_V1 = 1
SIGNOFF_CHAIN_VERSION_V2 = 2
SIGNOFF_CHAIN_VERSION_DEFAULT = SIGNOFF_CHAIN_VERSION_V2

# v1：历史在途单
REWORK_SIGNOFF_CHAIN_AA_V1: List[NodeDef] = [
    ("sales", "销售"),
    ("quality", "质量"),
    ("manufacturing", "生产"),
    ("purchasing", "采购"),
    ("leader", "审核批准"),
    ("planning", "计划"),
    ("warehouse", "仓库"),
    ("manufacturing_exec", "完工入库"),
    ("finance", "财务"),
]

REWORK_SIGNOFF_CHAIN_AB_V1: List[NodeDef] = [
    ("sales", "销售"),
    ("rd", "研发"),
    ("quality", "质量"),
    ("manufacturing", "生产"),
    ("purchasing", "采购"),
    ("leader", "审核批准"),
    ("planning", "计划"),
    ("warehouse", "仓库"),
    ("manufacturing_exec", "完工入库"),
    ("finance", "财务"),
]

# v2：白板流程（新单默认）
REWORK_SIGNOFF_CHAIN_AA: List[NodeDef] = [
    ("sales", "销售"),
    ("quality", "返工需求提出"),
    ("ie_engineering", "返工排位策划"),
    ("position_review", "返工排位审核"),
    ("purchasing", "材料采购"),
    ("leader", "审核批准"),
    ("planning", "计划排产"),
    ("rework_exec", "返工执行"),
    ("manufacturing_exec", "完工入库"),
    ("finance", "财务"),
]

REWORK_SIGNOFF_CHAIN_AB: List[NodeDef] = [
    ("sales", "销售"),
    ("rd", "研发"),
    ("quality", "返工需求提出"),
    ("ie_engineering", "返工排位策划"),
    ("position_review", "返工排位审核"),
    ("purchasing", "材料采购"),
    ("leader", "审核批准"),
    ("planning", "计划排产"),
    ("rework_exec", "返工执行"),
    ("manufacturing_exec", "完工入库"),
    ("finance", "财务"),
]

def _path_key(path_type: str | None) -> str:
    return "ab" if str(path_type or "").strip().lower() == "ab" else "aa"


def chain_version_from_flow(flow: Mapping[str, Any] | None) -> int:
    if not flow:
        return SIGNOFF_CHAIN_VERSION_DEFAULT
    raw = flow.get("chain_version")
    if raw is None:
        return SIGNOFF_CHAIN_VERSION_V1
    try:
        return (
            SIGNOFF_CHAIN_VERSION_V2
            if int(raw) >= SIGNOFF_CHAIN_VERSION_V2
            else SIGNOFF_CHAIN_VERSION_V1
        )
    except (TypeError, ValueError):
        return SIGNOFF_CHAIN_VERSION_V1


def chain_for_path(
    path_type: str | None,
    *,
    chain_version: int | None = None,
) -> List[NodeDef]:
    ver = chain_version if chain_version is not None else SIGNOFF_CHAIN_VERSION_DEFAULT
    path = _path_key(path_type)
    if ver == SIGNOFF_CHAIN_VERSION_V1:
        return list(REWORK_SIGNOFF_CHAIN_AB_V1 if path == "ab" else REWORK_SIGNOFF_CHAIN_AA_V1)
    return list(REWORK_SIGNOFF_CHAIN_AB if path == "ab" else REWORK_SIGNOFF_CHAIN_AA)


def chain_for_order(path_type: str | None, flow: Mapping[str, Any] | None) -> List[NodeDef]:
    return chain_for_path(path_type, chain_version=chain_version_from_flow(flow))


def node_label(path_type: str | None, node_key: str, *, chain_version: int | None = None) -> str:
    key = str(node_key or "").strip()
    if chain_version is None:
        for _ver in (SIGNOFF_CHAIN_VERSION_V2, SIGNOFF_CHAIN_VERSION_V1):
            for code, name in chain_for_path(path_type, chain_version=_ver):
                if code == key:
                    return name
        return key
    for code, name in chain_for_path(path_type, chain_version=chain_version):
        if code == key:
            return name
    return key