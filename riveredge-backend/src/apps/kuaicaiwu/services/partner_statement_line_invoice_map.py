"""对账单物料行 ID → 发票 pull 预览 detail_lines 绑定。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


def _line_source_tuple(line: Dict[str, Any]) -> Optional[Tuple[str, int, int]]:
    batch_id = int(line.get("outsource_order_receipt_id") or 0)
    if batch_id > 0:
        return ("outsource_order_receipt", batch_id, batch_id)
    for doc_type, doc_key, item_key in (
        ("purchase_receipt", "purchase_receipt_id", "purchase_receipt_item_id"),
        ("sales_delivery", "sales_delivery_id", "sales_delivery_item_id"),
        ("purchase_order", "purchase_order_id", "purchase_order_item_id"),
        ("sales_order", "sales_order_id", "sales_order_item_id"),
    ):
        doc_id = int(line.get(doc_key) or 0)
        if doc_id <= 0:
            continue
        item_id = int(line.get(item_key) or 0)
        if item_id > 0:
            return (doc_type, doc_id, item_id)
    return None


async def attach_partner_statement_line_ids_to_detail_lines(
    tenant_id: int,
    statement_ids: Sequence[int],
    detail_lines: List[Dict[str, Any]],
) -> None:
    if not statement_ids or not detail_lines:
        return
    from apps.kuaicaiwu.models.partner_statement_line import PartnerStatementLine

    stmt_ids = [int(x) for x in statement_ids if int(x) > 0]
    if not stmt_ids:
        return
    rows = await PartnerStatementLine.filter(
        tenant_id=tenant_id,
        statement_id__in=stmt_ids,
        line_kind="material",
        deleted_at__isnull=True,
    ).order_by("id").all()
    index: Dict[Tuple[str, int, int], int] = {}
    for row in rows:
        doc_type = str(row.source_doc_type or "").strip()
        doc_id = int(row.source_doc_id or 0)
        line_id = int(row.source_line_id or 0)
        if not doc_type or doc_id <= 0:
            continue
        for key in (
            (doc_type, doc_id, line_id),
            (doc_type, doc_id, 0),
            (doc_type, doc_id, doc_id),
        ):
            if key not in index:
                index[key] = int(row.id)

    def _resolve_stmt_line_id(key: Tuple[str, int, int]) -> Optional[int]:
        doc_type, doc_id, line_id = key
        for candidate in (
            (doc_type, doc_id, line_id),
            (doc_type, doc_id, doc_id),
            (doc_type, doc_id, 0),
        ):
            hit = index.get(candidate)
            if hit:
                return hit
        return None

    for line in detail_lines:
        key = _line_source_tuple(line)
        if not key:
            continue
        stmt_line_id = _resolve_stmt_line_id(key)
        if stmt_line_id:
            line["partner_statement_line_id"] = stmt_line_id


async def maybe_attach_partner_statement_line_ids(
    tenant_id: int,
    partner_statement_ids: Optional[Sequence[int]],
    preview: Union[Dict[str, Any], None],
) -> None:
    if not partner_statement_ids or not preview:
        return
    detail_lines = preview.get("detail_lines")
    if not detail_lines:
        return
    await attach_partner_statement_line_ids_to_detail_lines(
        tenant_id,
        partner_statement_ids,
        list(detail_lines),
    )