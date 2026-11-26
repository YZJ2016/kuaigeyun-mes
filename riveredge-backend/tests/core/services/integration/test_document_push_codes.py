"""document_push_codes 单测。"""

from unittest.mock import AsyncMock, patch

import pytest

from core.services.integration.document_push_codes import (
    DEFAULT_UNIT_NUMBER,
    apply_unit_code_map,
    extract_unit_code_map_from_conversion,
    resolve_push_unit_number,
    resolve_unit_for_push,
)


def test_apply_unit_code_map_passthrough_without_map():
    # 默认不套内置别名，pcs/kg 保持单位管理原 code
    assert apply_unit_code_map("pcs") == "pcs"
    assert apply_unit_code_map("kg") == "kg"
    assert apply_unit_code_map("个") == "个"
    assert apply_unit_code_map("个", use_builtin_aliases=True) == "006"


def test_apply_unit_code_map_can_disable_builtin():
    assert apply_unit_code_map("kg", use_builtin_aliases=False) == "kg"
    assert apply_unit_code_map("kg", {"kg": "kg"}, use_builtin_aliases=False) == "kg"


def test_apply_unit_code_map_api_map_overrides_builtin():
    assert apply_unit_code_map("个", {"个": "999"}) == "999"
    assert apply_unit_code_map("pcs", {"pcs": "006"}) == "006"


def test_extract_unit_code_map_from_conversion():
    entries = [
        {"field_name": "source_type", "mapping": {"1": "Make"}},
        {"field_name": "FUnitId.FNumber", "mapping": {"个": "006", "台": "001"}},
        {"field_name": "unit", "mapping": {"箱": "010"}},
    ]
    got = extract_unit_code_map_from_conversion(entries)
    assert got == {"个": "006", "台": "001", "箱": "010"}


def test_extract_unit_code_map_ignores_flat_dict():
    assert extract_unit_code_map_from_conversion({"个": "006"}) == {}


def test_extract_unit_code_map_case_insensitive_field():
    got = extract_unit_code_map_from_conversion(
        [{"field_name": "fbaseunitid.fnumber", "mapping": {"Pcs": "006"}}]
    )
    assert got == {"Pcs": "006"}


def test_default_unit_number():
    assert DEFAULT_UNIT_NUMBER == "006"


@pytest.mark.asyncio
async def test_resolve_push_unit_number_catalog_wins_over_builtin_kg_alias():
    """目录已有字面量 kg 时不得再改写成 004。"""
    with patch(
        "core.services.integration.document_push_codes.lookup_unit_catalog_code",
        new_callable=AsyncMock,
        side_effect=lambda _tid, ref: "kg" if str(ref).lower() == "kg" else None,
    ):
        got = await resolve_push_unit_number(
            1,
            unit_refs=["kg"],
            allow_builtin_aliases=True,
        )
    assert got == "kg"


@pytest.mark.asyncio
async def test_resolve_push_unit_number_cosmic_inventory_skips_builtin():
    with patch(
        "core.services.integration.document_push_codes.lookup_unit_catalog_code",
        new_callable=AsyncMock,
        return_value=None,
    ):
        got = await resolve_push_unit_number(
            1,
            unit_refs=["kg"],
            allow_builtin_aliases=False,
        )
    assert got == "kg"


@pytest.mark.asyncio
async def test_resolve_unit_for_push_catalog_skips_alias():
    with patch(
        "core.services.integration.document_push_codes.lookup_unit_catalog_code",
        new_callable=AsyncMock,
        return_value="kg",
    ):
        got = await resolve_unit_for_push(1, unit_hint="kg")
    assert got["unit_number"] == "kg"
    assert got["base_unit_number"] == "kg"
