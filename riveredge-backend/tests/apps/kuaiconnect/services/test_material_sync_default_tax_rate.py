from apps.kuaiconnect.services.inbound_sync.material_sync_service import (
    merge_material_defaults_default_tax_rate,
    resolve_material_sync_default_tax_rate_percent,
)


def test_resolve_tax_from_cosmic_taxrate_field():
    row = {"default_tax_rate": 13}
    assert resolve_material_sync_default_tax_rate_percent(row) == 13


def test_resolve_tax_from_decimal_ratio():
    row = {"taxrate.taxrate": 0.13}
    assert resolve_material_sync_default_tax_rate_percent(row) == 13


def test_resolve_tax_from_v13_code():
    row = {"taxrate_number": "V13"}
    assert resolve_material_sync_default_tax_rate_percent(row) == 13


def test_resolve_tax_one_percent():
    row = {"taxrate.taxrate": 1}
    assert resolve_material_sync_default_tax_rate_percent(row) == 1


def test_merge_defaults_preserves_other_keys():
    merged = merge_material_defaults_default_tax_rate(
        {"sales": {"defaultSalePrice": 100}}, 13
    )
    assert merged["defaultTaxRate"] == 13
    assert merged["sales"]["defaultSalePrice"] == 100