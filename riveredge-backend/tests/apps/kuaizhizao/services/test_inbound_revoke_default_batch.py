"""中途启用批号后，入库撤回可冲 DEFAULT 台账。"""

from apps.kuaizhizao.services.inventory_service import resolve_managed_decrease_batch_no


def test_inbound_revoke_empty_batch_maps_to_default():
    assert resolve_managed_decrease_batch_no(None, "purchase_receipt_revoke") == "DEFAULT"
    assert resolve_managed_decrease_batch_no("", "other_inbound_revoke") == "DEFAULT"
    assert resolve_managed_decrease_batch_no("  ", "finished_goods_receipt_revoke") == "DEFAULT"


def test_inbound_revoke_keeps_explicit_batch():
    assert resolve_managed_decrease_batch_no("B001", "purchase_receipt_revoke") == "B001"


def test_normal_outbound_still_requires_batch():
    assert resolve_managed_decrease_batch_no(None, "sales_delivery") is None
    assert resolve_managed_decrease_batch_no("", "production_picking") is None
    assert resolve_managed_decrease_batch_no(None, None) is None
