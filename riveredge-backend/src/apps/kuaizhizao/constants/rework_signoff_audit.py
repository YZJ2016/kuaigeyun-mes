"""会签返工各节点审批 node_key（配置中心审核绑定）。"""

from __future__ import annotations

SIGNOFF_AUDIT_NODE_PREFIX = "rework_signoff_"

# 销售提交时自动办结，不走节点审批
SIGNOFF_AUDIT_SKIP_DEPT_CODES = frozenset({"sales", "closed"})


def signoff_audit_node_key(dept_code: str) -> str:
    code = str(dept_code or "").strip()
    return f"{SIGNOFF_AUDIT_NODE_PREFIX}{code}"


def signoff_audit_manifest_business_type(dept_code: str) -> str:
    """manifest.audit.business_type：与 entity_type 组合唯一，避免挤占 multi_signoff 整单入口。"""
    return f"signoff_node_{str(dept_code or '').strip()}"