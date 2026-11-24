"""工序委外生命周期与后续步骤建议。"""

from types import SimpleNamespace

from apps.kuaizhizao.services.document_lifecycle_service import get_outsource_order_lifecycle


def test_outsource_order_released_suggests_process_issue():
    row = SimpleNamespace(
        status="released",
        outsource_quantity=10,
        received_quantity=0,
        purchase_receipt_id=None,
    )
    lc = get_outsource_order_lifecycle(row)
    assert lc["current_stage_key"] == "released"
    assert "工序发料" in lc["next_step_suggestions"]
    assert lc.get("sub_stages") is None


def test_outsource_order_in_progress_suggests_process_issue():
    row = SimpleNamespace(
        status="in_progress",
        outsource_quantity=10,
        received_quantity=0,
        purchase_receipt_id=None,
    )
    lc = get_outsource_order_lifecycle(row)
    assert lc["current_stage_key"] == "in_progress"
    assert "工序发料" in lc["next_step_suggestions"]


def test_outsource_order_completed_suggests_settlement():
    row = SimpleNamespace(
        status="completed",
        outsource_quantity=10,
        received_quantity=10,
        purchase_receipt_id=99,
    )
    lc = get_outsource_order_lifecycle(row)
    assert lc["next_step_suggestions"] == ["委外结算"]
