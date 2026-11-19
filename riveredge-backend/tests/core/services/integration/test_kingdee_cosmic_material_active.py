from core.services.integration.kingdee_cosmic_material_active import (
    apply_cosmic_sbd_getlist_active_data,
    filter_cosmic_material_rows_active,
    is_cosmic_material_row_active,
    is_cosmic_sbd_getlist_master_path,
)


def test_is_cosmic_material_row_active():
    assert is_cosmic_material_row_active({"enable": "1", "status": "C"})
    assert not is_cosmic_material_row_active({"enable": "0", "status": "C"})
    assert not is_cosmic_material_row_active({"enable": "1", "status": "A"})


def test_filter_cosmic_material_rows_active():
    rows = [
        {"number": "A", "enable": "1", "status": "C"},
        {"number": "B", "enable": "0", "status": "C"},
        {"number": "C", "enable": "1", "status": "A"},
    ]
    assert len(filter_cosmic_material_rows_active(rows)) == 1


def test_apply_cosmic_sbd_getlist_active_data_injects_audited_and_enabled():
    body = apply_cosmic_sbd_getlist_active_data(
        {"data": {}, "pageNo": 1, "pageSize": 100},
        path="kapi/v2/sbd/bd_warehouse/getList",
        active_only=True,
    )
    assert body["data"]["status"] == ["C"]
    assert body["data"]["enable"] == ["1"]


def test_warelocareference_query_not_treated_as_sbd_getlist_master():
    path = "kapi/v2/sbd/bd_warelocareference/query"
    assert not is_cosmic_sbd_getlist_master_path(path)
    body = apply_cosmic_sbd_getlist_active_data(
        {"data": {"warehouse_number": "1017"}, "pageNo": 1, "pageSize": 1000},
        path=path,
        active_only=True,
    )
    assert "status" not in body["data"]
    assert "enable" not in body["data"]
    rows = [
        {
            "warehouse_number": "1017",
            "location_number": "无货架",
            "location_name": "无货架",
        }
    ]
    assert len(filter_cosmic_material_rows_active(rows)) == 0


def test_apply_cosmic_sbd_getlist_does_not_override_custom_status():
    body = apply_cosmic_sbd_getlist_active_data(
        {"data": {"status": ["A"]}, "pageNo": 1},
        path="kapi/v2/sbd/bd_warehouse/getList",
        active_only=True,
    )
    assert body["data"]["status"] == ["A"]
