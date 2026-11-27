"""即时库存行辅助单位 → 物料固定辅助单位推算。"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.kuaiconnect.services.inbound_sync.inventory_sync_service import (
    _aux_base_ratio_n_d,
    _inventory_auxiliary_unit,
    ensure_material_fixed_aux_from_inventory_row,
)
from apps.kuaizhizao.utils.ledger_dual_quantity_utils import resolve_ledger_auxiliary_unit
from infra.exceptions.exceptions import ValidationError


def test_aux_base_ratio_from_kingdee_kg_jian():
    # 基本 10kg / 辅助 20 件 → 1 件 = 0.5 kg → n=1,d=2
    n, d = _aux_base_ratio_n_d(Decimal("10"), Decimal("20"))
    assert (n, d) == (1, 2)


def test_aux_base_ratio_rejects_zero_aux():
    with pytest.raises(ValidationError):
        _aux_base_ratio_n_d(Decimal("10"), Decimal("0"))


def test_inventory_auxiliary_unit_prefers_secunit_number():
    assert (
        _inventory_auxiliary_unit({"secunit_number": "件", "secunit_name": "件"}) == "件"
    )


def test_inventory_auxiliary_from_cosmic_unit2nd_qty2nd():
    """苍穹 getInventoryDetail 真源字段：unit2nd.* / qty2nd|avbqty2nd。"""
    from apps.kuaiconnect.services.inbound_sync.inventory_sync_service import (
        INVENTORY_MAP_EMPTY_FALLBACKS,
        _inventory_auxiliary_quantity,
    )
    from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import map_sync_rows

    raw = {
        "material.number": "0201010108",
        "avbqty": 10.0,
        "baseqty": 10.0,
        "qty2nd": 20,
        "avbqty2nd": 20,
        "unit2nd.number": "件",
        "unit2nd.name": "件",
        "unit.number": "kg",
    }
    mapped = map_sync_rows(
        [raw],
        {"material.number": "material_code", "avbqty": "quantity"},
        empty_fallbacks=INVENTORY_MAP_EMPTY_FALLBACKS,
    )[0]
    assert _inventory_auxiliary_unit(mapped) == "件"
    assert _inventory_auxiliary_quantity(mapped) == 20.0
    assert _inventory_auxiliary_unit(raw) == "件"
    assert _inventory_auxiliary_quantity(raw) == 20.0


@pytest.mark.asyncio
async def test_ensure_fixed_aux_writes_units_when_missing(monkeypatch):
    saved = {}

    class FakeMaterial(SimpleNamespace):
        async def save(self, update_fields=None):
            saved["units"] = self.units
            saved["update_fields"] = update_fields

    material = FakeMaterial(base_unit="kg", units=None, id=1)
    changed = await ensure_material_fixed_aux_from_inventory_row(
        material,
        aux_unit="件",
        base_quantity=Decimal("10"),
        aux_quantity=Decimal("20"),
        current_user=None,
    )
    assert changed is True
    assert resolve_ledger_auxiliary_unit(material) == "件"
    units = material.units["units"]
    assert units[0]["unit"] == "件"
    assert units[0]["numerator"] == 1
    assert units[0]["denominator"] == 2
    assert units[0]["conversionType"] == "fixed"
    assert saved.get("units") == material.units


@pytest.mark.asyncio
async def test_ensure_fixed_aux_upgrades_floating_row():
    saved = {}

    class FakeMaterial(SimpleNamespace):
        async def save(self, update_fields=None):
            saved["units"] = self.units

    material = FakeMaterial(
        base_unit="kg",
        units={
            "units": [{"unit": "件", "conversionType": "floating"}],
            "scenarios": {},
        },
        id=1,
    )
    changed = await ensure_material_fixed_aux_from_inventory_row(
        material,
        aux_unit="件",
        base_quantity=Decimal("10"),
        aux_quantity=Decimal("20"),
        current_user=None,
    )
    assert changed is True
    assert resolve_ledger_auxiliary_unit(material) == "件"
    assert material.units["units"][0]["conversionType"] == "fixed"
    assert material.units["units"][0]["numerator"] == 1
    assert material.units["units"][0]["denominator"] == 2
    assert saved.get("units") == material.units


@pytest.mark.asyncio
async def test_ensure_fixed_aux_noop_when_already_has_same_unit():
    material = SimpleNamespace(
        base_unit="kg",
        units={
            "units": [
                {
                    "unit": "件",
                    "numerator": 1,
                    "denominator": 2,
                    "conversionType": "fixed",
                }
            ],
            "scenarios": {},
        },
        id=1,
    )

    async def _save(**_kwargs):
        raise AssertionError("should not save")

    material.save = _save  # type: ignore[method-assign]
    changed = await ensure_material_fixed_aux_from_inventory_row(
        material,
        aux_unit="件",
        base_quantity=Decimal("10"),
        aux_quantity=Decimal("20"),
        current_user=None,
    )
    assert changed is False
