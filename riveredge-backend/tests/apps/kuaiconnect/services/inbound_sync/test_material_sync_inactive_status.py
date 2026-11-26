from apps.kuaiconnect.services.inbound_sync.material_sync_service import (
    collect_kingdee_inactive_material_codes,
)


def test_collect_inactive_cosmic_material_codes():
    rows = [
        {"number": "A1", "status": "C", "enable": "1"},
        {"number": "A2", "status": "C", "enable": "0"},
        {"number": "A3", "status": "A", "enable": "1"},
    ]
    codes = collect_kingdee_inactive_material_codes(
        rows,
        path_for_active="kapi/v2/basedata/bd_material/batchQuery",
    )
    assert codes == {"A2", "A3"}


def test_collect_ignores_non_material_path():
    rows = [{"number": "X", "status": "C", "enable": "0"}]
    assert not collect_kingdee_inactive_material_codes(rows, path_for_active="kapi/v2/other/query")