"""业务单据 attachments JSON 字段计数（列表/取单展示用）。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def count_document_attachments(value: Any) -> int:
    """统计 attachments 列表中的有效条目数。"""
    if not value or not isinstance(value, list):
        return 0
    count = 0
    for item in value:
        if not isinstance(item, dict):
            continue
        if any(item.get(key) for key in ("uid", "uuid", "name", "url")):
            count += 1
    return count


def normalize_document_attachments_for_carry(raw: Any) -> Optional[List[Dict[str, Any]]]:
    """下推/复制：规范源单行 attachments JSON，无效条目剔除。"""
    from apps.kuaizhizao.utils.sales_order_attachment_carry import merge_attachment_lists

    merged = merge_attachment_lists(raw or [])
    return merged if merged else None


def sum_header_and_line_attachment_counts(
    header_attachments: Any,
    line_attachments_iterable: Optional[Iterable[Any]] = None,
) -> int:
    total = count_document_attachments(header_attachments)
    if line_attachments_iterable:
        for line_att in line_attachments_iterable:
            total += count_document_attachments(line_att)
    return total