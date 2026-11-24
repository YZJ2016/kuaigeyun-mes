"""采购申请开口行展示组与分批转单数量三元组（防 e5220295e 回退）。"""

from apps.kuaizhizao.utils.pull_open_line_quantity import (
    build_partial_push_qty_triplet,
    requisition_pull_display_group_key,
)


def test_display_group_separates_notes_and_dates():
    a = requisition_pull_display_group_key(1, 100, required_date="2026-11-25", notes="809")
    b = requisition_pull_display_group_key(1, 100, required_date="2026-11-28", notes="909")
    c = requisition_pull_display_group_key(1, 100, required_date="2026-11-25", notes="809")
    assert a != b
    assert a == c


def test_split_line_group_triplet_restores_original_qty():
    """拆行后组内 quantity 相加为原申请量，占用汇总为已转量。"""
    group_suggested = 3.0 + 2.0
    group_occupied = 2.0
    suggested, pushed, remaining = build_partial_push_qty_triplet(
        group_suggested, group_occupied
    )
    assert suggested == 5.0
    assert pushed == 2.0
    assert remaining == 3.0


def test_second_group_10_3_7():
    group_suggested = 7.0 + 3.0
    group_occupied = 3.0
    suggested, pushed, remaining = build_partial_push_qty_triplet(
        group_suggested, group_occupied
    )
    assert suggested == 10.0
    assert pushed == 3.0
    assert remaining == 7.0