"""IoT 点位阈值判定。"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

OPERATORS = frozenset({"gt", "lt", "gte", "lte", "eq", "ne"})


def _to_decimal(raw: Optional[Decimal]) -> Optional[Decimal]:
    if raw is None:
        return None
    return Decimal(str(raw))


def is_threshold_breached(
    operator: str,
    *,
    threshold_number: Optional[Decimal],
    threshold_text: Optional[str],
    value_number: Optional[Decimal],
    value_text: Optional[str],
    value_bool: Optional[bool],
) -> bool:
    op = str(operator or "").lower()
    if op in {"gt", "lt", "gte", "lte"}:
        left = _to_decimal(value_number)
        right = _to_decimal(threshold_number)
        if left is None or right is None:
            return False
        if op == "gt":
            return left > right
        if op == "lt":
            return left < right
        if op == "gte":
            return left >= right
        return left <= right

    actual = value_text
    if actual is None and value_number is not None:
        actual = str(value_number)
    if actual is None and value_bool is not None:
        actual = "true" if value_bool else "false"
    expected = threshold_text
    if expected is None and threshold_number is not None:
        expected = str(threshold_number)
    if actual is None or expected is None:
        return False
    if op == "eq":
        return str(actual).strip().lower() == str(expected).strip().lower()
    if op == "ne":
        return str(actual).strip().lower() != str(expected).strip().lower()
    return False


def format_actual_value(
    value_text: Optional[str],
    value_number: Optional[Decimal],
    value_bool: Optional[bool],
) -> str:
    if value_text is not None and str(value_text).strip():
        return str(value_text)
    if value_number is not None:
        return str(value_number)
    if value_bool is not None:
        return "true" if value_bool else "false"
    return ""
