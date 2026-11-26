"""发票结算粒度校验：汇总/明细不得混用占用路径。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

from apps.kuaicaiwu.config.finance_settlement_contract import (
    SETTLEMENT_MODE_DETAIL,
    SETTLEMENT_MODE_SUMMARY,
    SETTLEMENT_MODES,
)
from infra.exceptions.exceptions import ValidationError

_MONEY = Decimal("0.01")


def normalize_settlement_mode(value: Optional[str]) -> str:
    mode = str(value or SETTLEMENT_MODE_SUMMARY).strip().lower()
    if mode not in SETTLEMENT_MODES:
        raise ValidationError("settlement_mode 须为 summary 或 detail")
    return mode


def assert_detail_invoice_lines_strict_1_1(
    items: Sequence[dict[str, Any]],
    *,
    amount_field: str = "amount",
) -> None:
    """明细发票：每行须有有效源单与 source_line_id；同一发票内禁止重复绑定同一源行。"""
    del amount_field
    seen: set[tuple[Any, Any, Any]] = set()
    for idx, row in enumerate(items):
        sid = row.get("source_line_id")
        if sid is None:
            raise ValidationError(f"明细发票第 {idx + 1} 行缺少 source_line_id")
        src_doc_type = str(row.get("source_doc_type") or "").strip()
        if not src_doc_type:
            raise ValidationError(f"明细发票第 {idx + 1} 行缺少 source_doc_type")
        try:
            src_doc_id = int(row.get("source_doc_id") or 0)
            src_line_id = int(sid)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"明细发票第 {idx + 1} 行源单或行标识格式无效") from exc
        if src_doc_id <= 0 or src_line_id <= 0:
            raise ValidationError(f"明细发票第 {idx + 1} 行 source_doc_id 与 source_line_id 须大于 0")
        key = (src_doc_type, src_doc_id, src_line_id)
        if key in seen:
            raise ValidationError("明细发票禁止在同一单据内重复绑定同一源单行")
        seen.add(key)
        qty = row.get("quantity")
        if qty is not None and Decimal(str(qty)) <= 0:
            raise ValidationError(f"明细发票第 {idx + 1} 行数量须大于 0")


def assert_summary_invoice_no_line_sources(items: Iterable[dict[str, Any]]) -> None:
    for row in items:
        if row.get("source_line_id") is not None:
            raise ValidationError("汇总发票不得写入 source_line_id")


def assert_settlement_mode_items_consistency(mode: str, items: Sequence[dict[str, Any]]) -> None:
    mode = normalize_settlement_mode(mode)
    if mode == SETTLEMENT_MODE_DETAIL:
        assert_detail_invoice_lines_strict_1_1(items)
    else:
        assert_summary_invoice_no_line_sources(items)