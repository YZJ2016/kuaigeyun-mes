"""金蝶仓位号：本地复合编码与 source_location_code 解析。"""

from __future__ import annotations

from types import SimpleNamespace

from apps.master_data.utils.kingdee_location_number import (
    derive_kingdee_location_number_from_composite_local_code,
    index_storage_locations_for_inbound_sync,
    kingdee_location_number_from_storage_location,
    resolve_kingdee_location_number_from_codes,
    resolve_storage_location_for_inbound_sync,
)


def test_kingdee_number_prefers_source_location_code() -> None:
    loc = SimpleNamespace(code="1002_无货架", source_location_code="无货架")
    assert kingdee_location_number_from_storage_location(loc) == "无货架"


def test_kingdee_number_falls_back_to_local_code() -> None:
    loc = SimpleNamespace(code="A01", source_location_code=None)
    assert kingdee_location_number_from_storage_location(loc) == "A01"


def test_derive_kingdee_number_from_composite_without_source() -> None:
    loc = SimpleNamespace(code="1002_无货架", source_location_code=None)
    assert (
        kingdee_location_number_from_storage_location(loc, warehouse_number="1002")
        == "无货架"
    )
    assert (
        resolve_kingdee_location_number_from_codes(
            local_code="1002_无货架",
            warehouse_number="1002",
        )
        == "无货架"
    )
    assert (
        derive_kingdee_location_number_from_composite_local_code("1002_无货架", "1002")
        == "无货架"
    )


def test_composite_local_code_maps_to_kingdee_via_source_field() -> None:
    """多仓共用「无货架」时本地 code 为 1002_无货架，推送须读 source_location_code。"""
    loc = SimpleNamespace(code="1002_无货架", source_location_code="无货架")
    assert kingdee_location_number_from_storage_location(loc) == "无货架"


def test_inbound_sync_resolves_kingdee_location_number_by_warehouse() -> None:
    loc = SimpleNamespace(
        id=9,
        code="1002_无货架",
        source_location_code="无货架",
        name="无货架",
        warehouse_id=1002,
    )
    by_code, by_wh_source, by_name = index_storage_locations_for_inbound_sync([loc])
    matched = resolve_storage_location_for_inbound_sync(
        warehouse_id=1002,
        source_location_key="无货架",
        location_by_code=by_code,
        location_by_wh_source=by_wh_source,
        location_by_name=by_name,
    )
    assert matched is loc
