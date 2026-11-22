"""提交审核请求内暂存发起人分支选择与审批部门（供 start_approval 读取）。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Dict, Optional

_submit_branch_by_node: ContextVar[Optional[Dict[str, int]]] = ContextVar(
    "_submit_branch_by_node",
    default=None,
)

_hierarchy_department_uuid: ContextVar[Optional[str]] = ContextVar(
    "_hierarchy_department_uuid",
    default=None,
)


def set_submit_branch_by_node(branch_by_node: Optional[Dict[str, int]]):
    return _submit_branch_by_node.set(branch_by_node or None)


def reset_submit_branch_by_node(token) -> None:
    _submit_branch_by_node.reset(token)


def get_submit_branch_by_node() -> Dict[str, int]:
    raw = _submit_branch_by_node.get()
    return dict(raw) if isinstance(raw, dict) else {}


def set_hierarchy_department_uuid(department_uuid: Optional[str]):
    value = (department_uuid or "").strip() or None
    return _hierarchy_department_uuid.set(value)


def reset_hierarchy_department_uuid(token) -> None:
    _hierarchy_department_uuid.reset(token)


def get_hierarchy_department_uuid() -> Optional[str]:
    raw = _hierarchy_department_uuid.get()
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None
