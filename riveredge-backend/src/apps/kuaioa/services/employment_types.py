"""用工类型多选（空列表=全部）。"""

from __future__ import annotations

from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

ALLOWED_EMPLOYMENT_TYPES = frozenset({"formal", "temp", "labor"})
EMPLOYMENT_TYPE_LABELS = {"formal": "正式工", "temp": "临时工", "labor": "劳务工"}


def normalize_employment_types(raw: Optional[list[Any]]) -> list[str]:
    """空列表表示全部用工类型；非空须为 formal/temp/labor。"""
    if not raw:
        return []
    out: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if not value:
            continue
        if value not in ALLOWED_EMPLOYMENT_TYPES:
            raise BusinessLogicError("用工类型无效")
        if value not in out:
            out.append(value)
    return out


def employment_types_summary(types: list[str]) -> str:
    if not types:
        return "全部用工类型"
    return "、".join(EMPLOYMENT_TYPE_LABELS.get(x, x) for x in types)
