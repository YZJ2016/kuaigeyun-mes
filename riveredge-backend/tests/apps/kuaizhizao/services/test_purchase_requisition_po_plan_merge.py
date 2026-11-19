"""采购申请→采购订单规划合并契约（无 DB）：勾选序稳定 + 供应商合并规则。"""

from __future__ import annotations


def order_items_by_selected_ids(
    selected_ids: list[int],
    item_ids_present: set[int],
) -> list[int]:
    """镜像 plan_purchase_orders_from_requisition_convert 的勾选序。"""
    return [iid for iid in selected_ids if iid in item_ids_present]


def resolve_merged_header_supplier_id(line_supplier_ids: list[int]) -> int:
    """镜像规划层表头供应商：唯一有效供应商保留，否则待定(0)。"""
    unique_positive = {sid for sid in line_supplier_ids if sid > 0}
    if len(unique_positive) == 1:
        return next(iter(unique_positive))
    return 0


def test_selected_ids_order_stable_across_db_shuffle():
    selected = [30, 10, 20]
    # DB id__in 回来的集合无序
    present = {20, 30, 10}
    assert order_items_by_selected_ids(selected, present) == [30, 10, 20]


def test_same_supplier_keeps_header_supplier():
    assert resolve_merged_header_supplier_id([5, 5, 5]) == 5


def test_mixed_or_missing_supplier_becomes_pending():
    assert resolve_merged_header_supplier_id([5, 8]) == 0
    assert resolve_merged_header_supplier_id([0, 0]) == 0
    assert resolve_merged_header_supplier_id([5, 0]) == 5
    assert resolve_merged_header_supplier_id([]) == 0
