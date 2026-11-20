"""用户导入字段解析（金蝶导出列适配）。"""

from __future__ import annotations

from typing import Any, Optional


def normalize_import_employee_number(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def parse_import_gender(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text in {"男", "male", "m", "1"}:
        return "male"
    if text in {"女", "female", "f", "2"}:
        return "female"
    if text in {"其他", "other", "o"}:
        return "other"
    return text[:10]


def parse_import_user_disabled(raw: Any) -> Optional[bool]:
    """金蝶「用户禁用」：是/true/1 表示禁用 → is_active=False。"""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text in {"是", "yes", "y", "true", "1", "禁用", "disabled"}:
        return False
    if text in {"否", "no", "n", "false", "0", "启用", "enabled"}:
        return True
    return None


def split_import_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    parts = [p.strip() for p in text.replace("，", ",").split(",")]
    return [p for p in parts if p]
