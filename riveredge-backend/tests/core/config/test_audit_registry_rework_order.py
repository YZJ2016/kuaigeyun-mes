"""返工单 audit 按 business_type 分叉，不得仅凭 entry_by_entity_type 解析。"""

from core.config.audit_registry import (
    entry_by_entity_type,
    entry_by_entity_type_and_business,
)


def test_rework_order_audit_entries_are_business_scoped():
    assert entry_by_entity_type("rework_order") is None
    multi = entry_by_entity_type_and_business("rework_order", "multi_signoff")
    assert multi is not None
    assert multi.node_key == "rework_order"
    inv = entry_by_entity_type_and_business("rework_order", "inventory_verify")
    assert inv is not None
    assert inv.node_key == "rework_order_inventory_verify"
