from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
    apply_ledger_fields_to_inventory_row,
    material_ledger_is_dual_unit,
    material_ledger_uses_manual_aux_quantity,
    resolve_confirmation_ledger_pair,
    resolve_ledger_auxiliary_unit,
    resolve_material_display_auxiliary_unit,
    resolve_stored_ledger_quantities,
    resolve_sync_ledger_quantities,
    sync_material_batch_ledger_quantities,
)
from infra.exceptions.exceptions import ValidationError


def _mat(*, base="PCS", inv=None, units=None):
    return SimpleNamespace(
        base_unit=base,
        inventory_unit=inv or base,
        units=units,
    )


def _fixed_aux_units(aux="BOX"):
    return {
        "units": [
            {"unit": aux, "numerator": 10, "denominator": 1, "conversionType": "fixed"},
        ],
        "scenarios": {},
    }


def test_single_unit_sync_without_aux_field():
    m = _mat(base="PCS")
    synced = resolve_sync_ledger_quantities(m, primary_quantity=10, base_quantity_raw=None)
    assert synced.quantity == Decimal("10")
    assert synced.base_quantity == Decimal("10")
    assert synced.aux_quantity == Decimal("10")


def test_dual_aux_sync_from_baseqty():
    m = _mat(base="PCS", inv="PCS", units=_fixed_aux_units("BOX"))
    synced = resolve_sync_ledger_quantities(
        m,
        primary_quantity=100,
        base_quantity_raw=100,
        aux_quantity_raw=None,
    )
    assert synced.quantity == Decimal("100")
    assert synced.base_quantity == Decimal("100")
    assert synced.aux_quantity == Decimal("10")


def test_dual_aux_sync_requires_aux_when_base_zero():
    m = _mat(base="PCS", units=_fixed_aux_units("BOX"))
    with pytest.raises(ValidationError):
        resolve_sync_ledger_quantities(
            m,
            primary_quantity=5,
            base_quantity_raw=0,
            aux_quantity_raw=None,
        )


def test_stored_single_unit_secondary_defaults_to_primary():
    m = _mat(base="EA")
    p, s = resolve_stored_ledger_quantities(m, primary_quantity=5, aux_quantity_raw=None)
    assert p == Decimal("5")
    assert s == Decimal("5")


def test_sync_material_batch_single_unit_forces_triplet():
    m = _mat(base="个", inv="个")
    batch = SimpleNamespace(quantity=300, base_quantity=100, aux_quantity=-150)
    sync_material_batch_ledger_quantities(batch, m)
    assert batch.quantity == Decimal("300")
    assert batch.base_quantity == Decimal("300")
    assert batch.aux_quantity == Decimal("300")


def test_stored_single_unit_ignores_stale_aux():
    """单计量批号上孤立的 aux_quantity 不参与展示（避免副数量负库存）。"""
    m = _mat(base="个", inv="个")
    p, s = resolve_stored_ledger_quantities(
        m, primary_quantity=300, aux_quantity_raw=-150
    )
    assert p == Decimal("300")
    assert s == Decimal("300")


def test_stored_dual_unit_no_fallback():
    m = _mat(base="PCS", units=_fixed_aux_units("BOX"))
    p, s = resolve_stored_ledger_quantities(m, primary_quantity=3, aux_quantity_raw=None)
    assert p == Decimal("3")
    assert s == Decimal("0")


def test_stored_dual_unit_reconcile_negative_aux_from_base():
    m = _mat(base="PCS", inv="PCS", units=_fixed_aux_units("BOX"))
    p, s = resolve_stored_ledger_quantities(
        m,
        primary_quantity=100,
        aux_quantity_raw=-150,
        base_quantity_raw=100,
    )
    assert p == Decimal("100")
    assert s == Decimal("10")


def test_material_ledger_is_dual_unit_by_aux_not_inv_base_diff():
    assert not material_ledger_is_dual_unit(_mat(base="A", inv="BOX"))
    assert material_ledger_is_dual_unit(_mat(base="PCS", inv="BOX", units=_fixed_aux_units("BOX")))


def _floating_aux_units(aux="件"):
    return {
        "units": [
            {"unit": aux, "conversionType": "floating"},
        ],
        "scenarios": {},
    }


def test_resolve_material_display_auxiliary_unit_includes_floating():
    m = _mat(base="KG", inv="KG", units=_floating_aux_units("件"))
    assert resolve_material_display_auxiliary_unit(m) == "件"
    assert resolve_ledger_auxiliary_unit(m) is None
    assert not material_ledger_is_dual_unit(m)


def test_apply_ledger_row_floating_aux_shows_unit_without_quantity():
    m = _mat(base="KG", inv="KG", units=_floating_aux_units("件"))
    out = apply_ledger_fields_to_inventory_row(
        {"quantity": 24, "aux_quantity": 24},
        m,
    )
    assert out["secondary_unit"] == "件"
    assert out["ledger_has_auxiliary_unit"] is True
    assert out["ledger_is_dual_unit"] is False
    assert out["secondary_quantity"] is None


def test_apply_ledger_row_floating_aux_shows_recorded_aux_qty():
    m = _mat(base="KG", inv="KG", units=_floating_aux_units("件"))
    out = apply_ledger_fields_to_inventory_row(
        {"quantity": 24, "aux_quantity": 5},
        m,
    )
    assert out["secondary_unit"] == "件"
    assert out["secondary_quantity"] == 5.0


def test_manual_aux_sync_preserves_batch_aux_quantity():
    m = _mat(base="KG", inv="KG", units=_floating_aux_units("件"))
    assert material_ledger_uses_manual_aux_quantity(m)
    batch = SimpleNamespace(quantity=24, base_quantity=24, aux_quantity=5)
    sync_material_batch_ledger_quantities(batch, m)
    assert batch.aux_quantity == Decimal("5")
    assert batch.quantity == Decimal("24")


def test_stored_manual_aux_reads_batch_aux():
    m = _mat(base="KG", inv="KG", units=_floating_aux_units("件"))
    p, s = resolve_stored_ledger_quantities(m, primary_quantity=24, aux_quantity_raw=5)
    assert p == Decimal("24")
    assert s == Decimal("5")


def test_resolve_ledger_auxiliary_unit_skips_floating():
    m = _mat(
        units={
            "units": [
                {"unit": "TON", "conversionType": "floating"},
                {"unit": "BOX", "numerator": 1, "denominator": 1, "conversionType": "fixed"},
            ],
        },
    )
    assert resolve_ledger_auxiliary_unit(m) == "BOX"


def test_confirmation_aux_to_base_posting():
    m = _mat(base="PCS", inv="PCS", units=_fixed_aux_units("BOX"))
    inv_q, base_q = resolve_confirmation_ledger_pair(
        m,
        primary_quantity=100,
        secondary_quantity_raw=10,
    )
    assert inv_q == Decimal("100")
    assert base_q == Decimal("100")


def test_confirmation_single_primary_only():
    m = _mat(base="PCS")
    inv_q, base_q = resolve_confirmation_ledger_pair(
        m, primary_quantity=7, secondary_quantity_raw=None
    )
    assert inv_q == base_q == Decimal("7")
