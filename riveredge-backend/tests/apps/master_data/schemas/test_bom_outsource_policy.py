"""BOM 子件委外策略校验。"""

import pytest
from types import SimpleNamespace

from apps.master_data.constants.material_source_type import (
    SOURCE_TYPE_BUY,
    SOURCE_TYPE_MAKE,
    SOURCE_TYPE_OUTSOURCE,
)
from apps.master_data.schemas.material_schemas import (
    assert_bom_items_outsource_policy,
    resolve_bom_line_is_outsource,
)


def _component(source_type: str, cid: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=cid,
        source_type=source_type,
        main_code=f"M-{cid}",
        code=f"M-{cid}",
        name="测试物料",
    )


def test_outsource_material_requires_outsource_flag():
    items = [SimpleNamespace(component_id=1, is_outsource=False)]
    component_by_id = {1: _component(SOURCE_TYPE_OUTSOURCE)}
    with pytest.raises(ValueError, match="须标记为委外"):
        assert_bom_items_outsource_policy(items, component_by_id)


def test_buy_material_cannot_outsource():
    items = [SimpleNamespace(component_id=1, is_outsource=True)]
    component_by_id = {1: _component(SOURCE_TYPE_BUY)}
    with pytest.raises(ValueError, match="不允许委外"):
        assert_bom_items_outsource_policy(items, component_by_id)


def test_make_material_outsource_toggle():
    comp = _component(SOURCE_TYPE_MAKE)
    item_off = SimpleNamespace(component_id=1, is_outsource=False)
    item_on = SimpleNamespace(component_id=1, is_outsource=True)
    component_by_id = {1: comp}
    assert_bom_items_outsource_policy([item_off], component_by_id)
    assert_bom_items_outsource_policy([item_on], component_by_id)
    assert resolve_bom_line_is_outsource(item_on, SOURCE_TYPE_MAKE) is True
    assert resolve_bom_line_is_outsource(item_off, SOURCE_TYPE_MAKE) is False