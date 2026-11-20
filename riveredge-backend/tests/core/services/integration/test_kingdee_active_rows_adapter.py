"""金蝶有效行 Adapter 回归。"""

from core.services.integration.erp_adapters.kingdee_active_rows import (
    filter_kingdee_master_rows_active,
    resolve_kingdee_path_family,
    stamp_kingdee_sync_is_active,
)


def test_path_family_galaxy():
    is_cosmic, is_galaxy = resolve_kingdee_path_family(
        "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
    )
    assert is_galaxy is True
    assert is_cosmic is False


def test_path_family_cosmic_material():
    is_cosmic, is_galaxy = resolve_kingdee_path_family(
        "ierp/kapi/v2/basedata/bd_material/batchQuery"
    )
    assert is_cosmic is True
    assert is_galaxy is False


def test_filter_inactive_when_active_only_false_keeps_all():
    rows = [{"status": "C"}, {"status": "A"}]
    kept, skipped = filter_kingdee_master_rows_active(
        rows, api_path="/bd_material/batchquery", active_only=False
    )
    assert len(kept) == 2
    assert skipped == 0


def test_stamp_sets_sync_is_active():
    rows = [{"number": "M1", "status": "C", "enable": "1"}]
    out = stamp_kingdee_sync_is_active(rows, api_path="/bd_material/batchquery")
    assert "sync_is_active" in out[0]
