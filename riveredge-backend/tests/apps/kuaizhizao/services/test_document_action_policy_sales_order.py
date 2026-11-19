"""销售订单 document_action_policy 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.kuaizhizao.services.document_action_policy.sales_order import (
    assert_sales_order_capability,
    derive_sales_order_capabilities,
)
from infra.exceptions.exceptions import BusinessLogicError


def _o(**kwargs):
    defaults = {
        "status": "草稿",
        "review_status": "待审核",
        "planning_pushed_to_computation": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_draft_update_delete_submit():
    caps = derive_sales_order_capabilities(_o())
    assert caps.update.allowed
    assert caps.delete.allowed
    assert caps.submit.allowed
    assert not caps.push_computation.allowed


def test_audited_push_computation_allowed():
    caps = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
    )
    assert caps.push_computation.allowed
    assert caps.push_work_order.allowed
    assert not caps.update.allowed


def test_computation_already_pushed_blocks_push():
    caps = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        pushed_to_computation=True,
        has_items=True,
    )
    assert not caps.push_computation.allowed
    assert caps.push_computation.reason == "sales_order.push_computation.already_pushed"
    assert caps.withdraw_computation.allowed
    assert caps.withdraw_computation.reason is None


def test_line_work_orders_block_computation_push():
    caps = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
        has_line_work_orders=True,
    )
    assert not caps.push_computation.allowed
    assert caps.push_computation.reason == "sales_order.push_computation.line_work_orders"


def test_withdraw_submit_pending_review():
    caps = derive_sales_order_capabilities(_o(status="待审核", review_status="待审核"))
    assert caps.withdraw_submit.allowed


def test_withdraw_submit_blocked_when_computation_pushed():
    caps = derive_sales_order_capabilities(
        _o(status="待审核", review_status="待审核"),
        computation_pushed_blocks_withdraw=True,
    )
    assert not caps.withdraw_submit.allowed


def test_approve_pending_review():
    caps = derive_sales_order_capabilities(_o(status="待审核", review_status="待审核"))
    assert caps.approve.allowed


def test_revoke_approval_strictly_audited():
    caps = derive_sales_order_capabilities(_o(status="已审核", review_status="审核通过"))
    assert caps.revoke_approval.allowed


def test_revoke_approval_confirmed_effective():
    caps = derive_sales_order_capabilities(_o(status="CONFIRMED", review_status="审核通过"))
    assert caps.revoke_approval.allowed
    caps2 = derive_sales_order_capabilities(_o(status="已生效", review_status="已通过"))
    assert caps2.revoke_approval.allowed


def test_revoke_approval_denied_when_closed():
    caps = derive_sales_order_capabilities(_o(status="已关闭", review_status="审核通过"))
    assert not caps.revoke_approval.allowed


def test_revoke_approval_denied_when_has_downstream():
    caps = derive_sales_order_capabilities(
        _o(status="CONFIRMED", review_status="APPROVED"),
        has_downstream_documents=True,
    )
    assert not caps.revoke_approval.allowed
    assert caps.revoke_approval.reason == "sales_order.revoke_approval.has_downstream"
    assert caps.create_change_order.allowed

    with pytest.raises(BusinessLogicError) as exc:
        assert_sales_order_capability(
            _o(status="已审核", review_status="审核通过"),
            "revoke_approval",
            has_downstream_documents=True,
        )
    assert "下游单据" in str(exc.value)
    assert "反审核并删除下游" in str(exc.value)


def test_create_change_order_when_locked():
    caps = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
    )
    assert caps.create_change_order.allowed
    assert not caps.update.allowed


def test_push_shipment_and_delivery_require_pushable_qty():
    """部分下推：无可下推数量时禁发运/出库；有剩余则可推。"""
    blocked = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
        has_pushable_qty=False,
    )
    assert not blocked.push_shipment_notice.allowed
    assert blocked.push_shipment_notice.reason == "sales_order.push_shipment.no_backorder"
    assert not blocked.push_sales_delivery.allowed
    assert blocked.push_sales_delivery.reason == "sales_order.push_delivery.no_backorder"

    allowed = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
        has_pushable_qty=True,
    )
    assert allowed.push_shipment_notice.allowed
    assert allowed.push_sales_delivery.allowed


def test_push_delivery_blocked_when_shipment_notice_required():
    caps = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
        has_pushable_qty=True,
        require_shipment_notice_before_delivery=True,
    )
    assert caps.push_shipment_notice.allowed
    assert not caps.push_sales_delivery.allowed
    assert caps.push_sales_delivery.reason == "sales_order.push_delivery.require_shipment_notice"


def test_delete_and_revoke_blocked_when_has_downstream():
    caps = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_downstream_documents=True,
    )
    assert not caps.delete.allowed
    assert caps.delete.reason == "sales_order.delete.has_downstream"
    assert not caps.revoke_approval.allowed
    assert caps.revoke_approval.reason == "sales_order.revoke_approval.has_downstream"


def test_push_sales_return_requires_delivered_qty():
    caps = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
        has_returnable_qty=False,
    )
    assert not caps.push_sales_return.allowed
    assert caps.push_sales_return.reason == "sales_order.push_return.no_delivered"

    caps_ok = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
        has_returnable_qty=True,
    )
    assert caps_ok.push_sales_return.allowed


def test_push_invoice_blocked_when_fully_invoiced():
    caps = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
        has_remaining_invoice_amount=False,
    )
    assert not caps.push_invoice.allowed
    assert caps.push_invoice.reason == "sales_order.push_invoice.already_fully_invoiced"

    caps_ok = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        has_items=True,
        has_remaining_invoice_amount=True,
    )
    assert caps_ok.push_invoice.allowed


def test_assert_raises_on_delete_audited():
    with pytest.raises(BusinessLogicError):
        assert_sales_order_capability(_o(status="已审核", review_status="审核通过"), "delete")


def test_require_audit_before_print_blocks_unapproved():
    caps = derive_sales_order_capabilities(
        _o(status="草稿", review_status="待审核"),
        require_audit_before_print=True,
    )
    assert not caps.print.allowed
    assert caps.print.reason == "sales_order.print.requires_audit"

    caps_ok = derive_sales_order_capabilities(
        _o(status="已审核", review_status="审核通过"),
        require_audit_before_print=True,
    )
    assert caps_ok.print.allowed


def test_require_audit_before_print_default_allows():
    caps = derive_sales_order_capabilities(_o(status="草稿", review_status="待审核"))
    assert caps.print.allowed
