"""点位阈值比较。只做 gt/lt/gte/lte/eq/ne。"""

from decimal import Decimal
from typing import Optional

OPERATORS = frozenset({"gt", "lt", "gte", "lte", "eq", "ne"})


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def format_actual_value(
    value_text: Optional[str],
    value_number: Optional[Decimal],
    value_bool: Optional[bool],
) -> str:
    if value_number is not None:
        text = format(_decimal(value_number), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    if value_bool is not None:
        return "true" if value_bool else "false"
    if value_text is not None:
        return str(value_text)
    return ""


def is_threshold_breached(
    operator: str,
    *,
    threshold_number: Optional[Decimal],
    threshold_text: Optional[str],
    value_number: Optional[Decimal],
    value_text: Optional[str],
    value_bool: Optional[bool],
) -> bool:
    op = (operator or "").strip()
    if op not in OPERATORS:
        return False
    if op in {"gt", "lt", "gte", "lte"}:
        if threshold_number is None or value_number is None:
            return False
        left = _decimal(value_number)
        right = _decimal(threshold_number)
        if op == "gt":
            return left > right
        if op == "lt":
            return left < right
        if op == "gte":
            return left >= right
        return left <= right
    if threshold_number is not None and value_number is not None:
        same = _decimal(value_number) == _decimal(threshold_number)
    elif threshold_text is not None and value_text is not None:
        same = str(value_text) == str(threshold_text)
    elif value_bool is not None and threshold_text in {"true", "false"}:
        same = value_bool is (threshold_text == "true")
    else:
        return False
    return same if op == "eq" else not same
