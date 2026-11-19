"""金蝶出库可用预检：仓位口径与行匹配。"""

from __future__ import annotations

from decimal import Decimal

from apps.kuaizhizao.services.kingdee_outbound_avb_precheck_service import (
    _match_row_to_demand,
    _sum_kingdee_avb,
)


def test_match_row_requires_bin_when_demand_has_location() -> None:
    row = {
        "material_number": "0305080004",
        "warehouse_number": "W1004",
        "location_number": "",
        "avbqty": 5,
    }
    assert not _match_row_to_demand(
        row,
        material_code="0305080004",
        warehouse_code="W1004",
        location_name="W1004_无货架",
        batch_no=None,
        use_lot=False,
    )
    row_bin = {**row, "location_number": "W1004_无货架", "avbqty": 3}
    assert _match_row_to_demand(
        row_bin,
        material_code="0305080004",
        warehouse_code="W1004",
        location_name="W1004_无货架",
        batch_no=None,
        use_lot=False,
    )


def test_sum_kingdee_avb_strict_location() -> None:
    rows = [
        {"material_number": "M1", "warehouse_number": "W1", "location_number": "", "qty": 5},
        {"material_number": "M1", "warehouse_number": "W1", "location_number": "W1_无货架", "qty": 2},
    ]
    total = _sum_kingdee_avb(
        rows,
        material_code="M1",
        warehouse_code="W1",
        location_name="W1_无货架",
        batch_no=None,
        use_lot=False,
    )
    assert total == Decimal("2")
