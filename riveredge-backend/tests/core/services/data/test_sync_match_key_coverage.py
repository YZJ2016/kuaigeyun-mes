"""同步来源匹配键覆盖：BOM line_key 可由父件+子件派生。"""

import pytest

from core.services.data.sync_binding_sources import (
    mapping_covers_match_key,
    validate_sources_for_match_key,
)
from infra.exceptions.exceptions import ValidationError


def test_line_key_covered_by_parent_and_component():
    mapping = {
        "material_number": "parent_code",
        "entrymaterial_number": "component_code",
        "entryqty": "quantity",
    }
    assert mapping_covers_match_key(mapping, "line_key") is True


def test_line_key_requires_both_sides():
    assert mapping_covers_match_key({"a": "parent_code"}, "line_key") is False
    assert mapping_covers_match_key({"a": "component_code"}, "line_key") is False


def test_validate_sources_accepts_bom_derived_line_key():
    validate_sources_for_match_key(
        [
            {
                "kind": "api",
                "api_uuid": "11111111-1111-1111-1111-111111111111",
                "field_mapping": {
                    "material_number": "parent_code",
                    "entrymaterial_number": "component_code",
                    "entryqty": "quantity",
                },
            }
        ],
        "line_key",
    )


def test_validate_sources_still_requires_literal_for_other_keys():
    with pytest.raises(ValidationError, match="匹配键 code"):
        validate_sources_for_match_key(
            [
                {
                    "kind": "api",
                    "api_uuid": "11111111-1111-1111-1111-111111111111",
                    "field_mapping": {"FNumber": "name"},
                }
            ],
            "code",
        )
