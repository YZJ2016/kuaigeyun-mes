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


def test_sources_for_persist_keeps_override_only_when_remembered():
    from core.services.data.sync_binding_sources import sources_for_persist

    remembered = sources_for_persist(
        [
            {
                "kind": "api",
                "api_uuid": "11111111-1111-1111-1111-111111111111",
                "field_mapping": {"FNumber": "material_code"},
                "request_body": {"pageSize": 50},
                "persist_request_override": True,
            }
        ]
    )
    assert remembered[0]["request_body"] == {"pageSize": 50}
    assert remembered[0]["persist_request_override"] is True

    session_only = sources_for_persist(
        [
            {
                "kind": "api",
                "api_uuid": "11111111-1111-1111-1111-111111111111",
                "field_mapping": {"FNumber": "material_code"},
                "request_body": {"pageSize": 50},
                "persist_request_override": False,
            }
        ]
    )
    assert "request_body" not in session_only[0]
    assert "persist_request_override" not in session_only[0]


def test_sources_for_persist_keeps_batch_fill_when_remembered():
    from core.services.data.sync_binding_sources import sources_for_persist

    remembered = sources_for_persist(
        [
            {
                "kind": "api",
                "api_uuid": "11111111-1111-1111-1111-111111111111",
                "field_mapping": {"FNumber": "material_code"},
                "batch_fill_path": "params.material",
                "batch_fill_values": ["A001", "A002"],
                "persist_request_override": True,
            }
        ]
    )
    assert remembered[0]["batch_fill_path"] == "params.material"
    assert remembered[0]["batch_fill_values"] == ["A001", "A002"]


def test_map_sync_rows_reads_dotted_keys_and_nested_objects():
    from apps.master_data.services.master_data_sync_common import map_sync_rows

    mapping = {
        "material.number": "material_code",
        "avbqty": "quantity",
        "warehouse.number": "warehouse_code",
    }
    dotted = map_sync_rows(
        [{"material.number": "M1", "avbqty": "12", "warehouse.number": "CK-1"}],
        mapping,
    )
    assert dotted == [{"material_code": "M1", "quantity": "12", "warehouse_code": "CK-1"}]

    nested = map_sync_rows(
        [{"material": {"number": "M2"}, "avbqty": 3, "warehouse": {"number": "CK-2"}}],
        mapping,
    )
    assert nested == [{"material_code": "M2", "quantity": 3, "warehouse_code": "CK-2"}]


def test_map_sync_rows_quantity_fallback_skips_empty_baseqty():
    from apps.master_data.services.master_data_sync_common import map_sync_rows
    from apps.kuaizhizao.services.inventory_sync_service import INVENTORY_MAP_EMPTY_FALLBACKS

    mapping = {
        "material.number": "material_code",
        "baseqty": "quantity",
        "warehouse.number": "warehouse_code",
    }
    rows = map_sync_rows(
        [
            {
                "material.number": "M1",
                "baseqty": "",
                "avbqty": "23229",
                "qty": "23229",
                "warehouse.number": "CK-1",
            }
        ],
        mapping,
        empty_fallbacks=INVENTORY_MAP_EMPTY_FALLBACKS,
    )
    assert rows[0]["quantity"] == "23229"


def test_empty_inventory_write_message_includes_fetch_count():
    from apps.kuaizhizao.services.inventory_sync_service import _empty_inventory_write_message
    from types import SimpleNamespace

    msg = _empty_inventory_write_message(
        SimpleNamespace(skipped=4, failed=0, errors=["物料 M1 缺少仓库编码或仓库名称，已跳过"] * 4),
        fetched=4,
    )
    assert "拉取 4 条" in msg
    assert "新建 0" in msg
    assert "共 4 条" in msg
