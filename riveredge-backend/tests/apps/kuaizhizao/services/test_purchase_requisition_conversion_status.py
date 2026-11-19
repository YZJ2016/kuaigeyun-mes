"""采购申请转单状态回写契约（对齐 _recalc_conversion_status，无 DB）。"""

from __future__ import annotations

from apps.kuaizhizao.constants import DocumentStatus, normalize_status


def _recalc_status_pure(
    current_status: str,
    *,
    item_count: int,
    converted_count: int,
) -> str:
    """镜像 PurchaseRequisitionService._recalc_conversion_status 的状态分支。"""
    has_any = converted_count > 0
    all_converted = item_count > 0 and converted_count >= item_count
    current_norm = normalize_status(current_status)
    if all_converted:
        return DocumentStatus.FULL_CONVERTED.value
    if has_any:
        return DocumentStatus.PARTIAL_CONVERTED.value
    if current_norm in (
        DocumentStatus.AUDITED.value,
        DocumentStatus.APPROVED.value,
        DocumentStatus.CONFIRMED.value,
        DocumentStatus.PARTIAL_CONVERTED.value,
        DocumentStatus.FULL_CONVERTED.value,
    ):
        return "已通过"
    return current_status


def test_full_converted_when_all_lines_linked():
    assert (
        _recalc_status_pure("已通过", item_count=3, converted_count=3)
        == DocumentStatus.FULL_CONVERTED.value
    )


def test_partial_converted_when_some_lines_linked():
    assert (
        _recalc_status_pure("已通过", item_count=3, converted_count=1)
        == DocumentStatus.PARTIAL_CONVERTED.value
    )


def test_heal_back_to_approved_when_links_cleared():
    """PO 改明细丢源后若无任何转单行，已转单态应回落已通过（进度 0% 真源）。"""
    assert _recalc_status_pure("FULL_CONVERTED", item_count=2, converted_count=0) == "已通过"
    assert _recalc_status_pure("PARTIAL_CONVERTED", item_count=2, converted_count=0) == "已通过"
    assert _recalc_status_pure("已审核", item_count=2, converted_count=0) == "已通过"


def test_draft_and_pending_not_rewritten_when_no_links():
    assert _recalc_status_pure("草稿", item_count=2, converted_count=0) == "草稿"
    assert _recalc_status_pure("待审核", item_count=2, converted_count=0) == "待审核"
