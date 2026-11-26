"""BOM 重复子件须以 install_position 区分。"""

import pytest
from decimal import Decimal

from apps.master_data.schemas.material_schemas import BOMBatchCreate, BOMItemCreate


def _item(component_id: int, install_position: str | None = None) -> BOMItemCreate:
    return BOMItemCreate(
        component_id=component_id,
        install_position=install_position,
        quantity=Decimal("1"),
    )


def test_duplicate_component_requires_install_position():
    with pytest.raises(ValueError, match="重复子物料须填写位置"):
        BOMBatchCreate(
            material_id=1,
            items=[_item(10), _item(10)],
        )


def test_duplicate_component_different_positions_allowed():
    batch = BOMBatchCreate(
        material_id=1,
        items=[_item(10, "A1"), _item(10, "A2")],
    )
    assert len(batch.items) == 2


def test_same_component_and_position_rejected():
    with pytest.raises(ValueError, match="相同子物料与位置不能重复"):
        BOMBatchCreate(
            material_id=1,
            items=[_item(10, "A1"), _item(10, "A1")],
        )