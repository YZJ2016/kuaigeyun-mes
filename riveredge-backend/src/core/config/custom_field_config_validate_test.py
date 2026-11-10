"""自定义字段 config 契约单元测试（无 DB）。"""

import pytest

from core.config.custom_field_config_validate import (
    apply_non_persisted_field_flags,
    is_associated_object_non_persisted,
    validate_custom_field_config,
)


def test_associated_object_xlookup_ok():
    validate_custom_field_config(
        "associated_object",
        {
            "associatedTable": "master_data_materials",
            "sourceField": "materialId",
            "matchField": "id",
            "returnField": "base_unit",
            "displayMode": "display",
        },
    )


def test_is_associated_object_non_persisted():
    assert is_associated_object_non_persisted(
        "associated_object",
        {"sourceField": "materialId", "displayMode": "display"},
    )
    assert not is_associated_object_non_persisted(
        "associated_object",
        {"sourceField": "materialId", "displayMode": "input"},
    )
    assert not is_associated_object_non_persisted(
        "associated_object",
        {"displayMode": "display"},
    )


def test_apply_non_persisted_field_flags_forces_off():
    payload = {
        "field_type": "associated_object",
        "config": {"sourceField": "materialId", "displayMode": "display"},
        "is_required": True,
        "is_searchable": True,
        "is_sortable": True,
    }
    apply_non_persisted_field_flags(payload)
    assert payload["is_required"] is False
    assert payload["is_searchable"] is False
    assert payload["is_sortable"] is False


def test_associated_object_select_ok():
    validate_custom_field_config(
        "associated_object",
        {
            "associatedTable": "master_data_materials",
            "associatedField": "name",
            "displayMode": "select",
        },
    )


def test_associated_object_display_without_source_rejected():
    with pytest.raises(ValueError, match="源字段"):
        validate_custom_field_config(
            "associated_object",
            {
                "associatedTable": "master_data_materials",
                "matchField": "id",
                "returnField": "base_unit",
                "displayMode": "display",
            },
        )


def test_associated_object_missing_table_rejected():
    with pytest.raises(ValueError, match="associatedTable"):
        validate_custom_field_config(
            "associated_object",
            {"sourceField": "materialId", "matchField": "id", "returnField": "id"},
        )


def test_associated_object_xlookup_missing_match_rejected():
    with pytest.raises(ValueError, match="matchField"):
        validate_custom_field_config(
            "associated_object",
            {
                "associatedTable": "master_data_materials",
                "sourceField": "materialId",
                "returnField": "id",
            },
        )


def test_associated_attribute_missing_attribute_rejected():
    with pytest.raises(ValueError, match="attributeField"):
        validate_custom_field_config(
            "associated_attribute",
            {"associatedTable": "master_data_materials", "displayMode": "select"},
        )


def test_text_type_skips_associated_rules():
    validate_custom_field_config("text", {})
