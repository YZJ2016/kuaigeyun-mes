"""金蝶星空物料行有效判定：已审核（FDocumentStatus=C）+ 未禁用（FForbidStatus=A）。

苍穹用 status/enable；星空 ExecuteBillQuery 字段名不同。物料同步 transform 不得套用苍穹过滤器，
否则「仅有效」会把星空行全部滤成 fetched=0。
"""

from __future__ import annotations

from typing import Any, Dict, List


def _row_get_ci(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in row and row.get(key) is not None:
            return str(row.get(key) or "").strip()
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        val = lower_map.get(key.lower())
        if val is not None:
            return str(val or "").strip()
    return ""


def is_galaxy_material_row_active(row: Dict[str, Any]) -> bool:
    """已审核且未禁用；缺状态字段时视为有效（已由 FilterString 收窄）。"""
    doc = _row_get_ci(row, "FDocumentStatus").upper()
    forbid = _row_get_ci(row, "FForbidStatus").upper()
    if doc and doc != "C":
        return False
    if forbid and forbid != "A":
        return False
    return True


def filter_galaxy_material_rows_active(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict) and is_galaxy_material_row_active(r)]


def is_galaxy_execute_bill_query_path(path: str) -> bool:
    lower = str(path or "").lower().replace("\\", "/")
    return "executebillquery" in lower or lower.endswith(".kdsvc")
