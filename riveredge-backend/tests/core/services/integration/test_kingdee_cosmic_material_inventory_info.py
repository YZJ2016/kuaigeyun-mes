import importlib.util
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4] / "src"
_MOD_PATH = _SRC / "core/services/integration/kingdee_cosmic_material_inventory_info.py"
_spec = importlib.util.spec_from_file_location("kingdee_cosmic_material_inventory_info_mod", _MOD_PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
apply = _mod.apply_inventory_tracking_to_material_rows
flags = _mod._inventory_tracking_flags_from_row


def test_inventory_tracking_flags_prefers_enablelot_over_masterid():
    row = {"enablelot": True, "masterid_enablelot": False, "enableserial": False}
    assert flags(row)["enablelot"] is True


def test_inventory_tracking_flags_falls_back_to_masterid_enablelot():
    row = {"masterid_enablelot": True, "enableserial": None, "masterid_enableserial": True}
    out = flags(row)
    assert out["enablelot"] is True
    assert out["enableserial"] is True


def test_apply_inventory_tracking_overrides_master_enablelot():
    rows = [{"number": "M001", "enablelot": False, "enableserial": False}]
    tracking = {"M001": {"enablelot": True, "enableserial": False}}
    out = apply(rows, tracking)
    assert out[0]["enablelot"] is True
    assert out[0]["enableserial"] is False


def test_apply_inventory_tracking_skips_unknown_codes():
    rows = [{"number": "M002", "enablelot": False}]
    out = apply(rows, {"M001": {"enablelot": True}})
    assert out[0]["enablelot"] is False
