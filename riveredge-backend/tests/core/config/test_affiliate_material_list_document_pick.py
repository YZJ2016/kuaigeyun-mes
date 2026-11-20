"""单据行选料：物料列表 GET 应允许宿主单据读 OR 物料展示。"""

from core.config.affiliate_read_allowlist import resolve_affiliate_read_codes


def test_material_list_search_matches_query_list() -> None:
    codes = resolve_affiliate_read_codes(
        "master-data",
        "GET",
        "/api/v1/apps/master-data/materials?keyword=00006010164",
    )
    assert codes is not None
    assert "master-data:material:read" in codes
    assert "master-data:material:display" in codes
    assert "kuaizhizao:purchase-requisition:read" in codes


def test_material_list_search_does_not_match_unit_catalog() -> None:
    codes = resolve_affiliate_read_codes(
        "master-data",
        "GET",
        "/api/v1/apps/master-data/materials/units",
    )
    assert codes is None or "kuaizhizao:purchase-requisition:read" not in codes
