"""物料编码搜索模式：前缀 vs 模糊."""

import pytest

from apps.master_data.services.material_code_search_mode import (
    coerce_material_code_search_mode,
    material_row_matches_keyword,
)
from infra.services.business_config_service import (
    DEFAULT_PARAMETERS,
    IMPLEMENTED_PARAMETER_KEYS,
    PARAMETER_KEYS,
    coerce_master_data_parameters,
)


class _MaterialRow:
    main_code = "1101001"
    code = "1101001"
    name = "测试物料"
    specification = "规格100"


def test_coerce_material_code_search_mode_defaults():
    assert coerce_material_code_search_mode(None) == "fuzzy"
    assert coerce_material_code_search_mode("prefix") == "prefix"
    assert coerce_material_code_search_mode("invalid") == "fuzzy"


def test_prefix_miss_middle_code_segment():
    assert material_row_matches_keyword(_MaterialRow(), "100", "prefix") is False


def test_prefix_hit_code_head():
    assert material_row_matches_keyword(_MaterialRow(), "110", "prefix") is True


def test_fuzzy_hit_middle_code_segment():
    assert material_row_matches_keyword(_MaterialRow(), "100", "fuzzy") is True


def test_fuzzy_does_not_use_name_in_prefix_mode():
    row = _MaterialRow()
    assert material_row_matches_keyword(row, "测试", "prefix") is False
    assert material_row_matches_keyword(row, "测试", "fuzzy") is True


def test_parameter_registered():
    key = "parameters.master_data.material_code_search_mode"
    assert key in PARAMETER_KEYS
    assert key in IMPLEMENTED_PARAMETER_KEYS
    assert DEFAULT_PARAMETERS["master_data"]["material_code_search_mode"] == "fuzzy"


def test_coerce_master_data_includes_search_mode():
    out = coerce_master_data_parameters({"material_code_search_mode": "prefix"})
    assert out["material_code_search_mode"] == "prefix"