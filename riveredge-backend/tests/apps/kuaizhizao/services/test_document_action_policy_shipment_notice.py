"""发货通知单 document_action_policy 单元测试。"""

from types import SimpleNamespace

import pytest

from apps.kuaizhizao.services.document_action_policy.shipment_notice import (
    assert_shipment_notice_capability,
    derive_shipment_notice_capabilities,
)
from infra.exceptions.exceptions import BusinessLogicError


def _n(**kwargs):
    defaults = {"status": "待发货", "review_status": "草稿", "warehouse_id": 1}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_pending_update_delete_notify():
    caps = derive_shipment_notice_capabilities(_n(), has_items=True, has_warehouse=True)
    assert caps.update.allowed
    assert caps.delete.allowed
    assert not caps.notify.allowed
    assert caps.notify.reason == "shipment_notice.notify.not_audited"
    assert not caps.withdraw.allowed


def test_notify_requires_approved_review():
    caps = derive_shipment_notice_capabilities(
        _n(review_status="已通过"),
        has_items=True,
        has_warehouse=True,
    )
    assert caps.notify.allowed
    assert not caps.update.allowed
    assert caps.approve.allowed is False
    assert caps.revoke_approval.allowed


def test_notify_allowed_without_warehouse_on_notice():
    caps = derive_shipment_notice_capabilities(
        _n(warehouse_id=None, review_status="已通过"),
        has_items=True,
        has_warehouse=False,
    )
    assert caps.notify.allowed


def test_notify_requires_items():
    caps = derive_shipment_notice_capabilities(_n(review_status="已通过"), has_items=False)
    assert not caps.notify.allowed
    assert caps.notify.reason == "shipment_notice.notify.no_items"


def test_pending_review_can_approve_not_notify():
    caps = derive_shipment_notice_capabilities(_n(status="待审核", review_status="待审核"))
    assert caps.approve.allowed
    assert caps.withdraw_submit.allowed
    assert not caps.notify.allowed
    assert not caps.update.allowed
    assert not caps.submit.allowed


def test_rejected_can_edit_and_resubmit():
    caps = derive_shipment_notice_capabilities(_n(status="草稿", review_status="已驳回"))
    assert caps.update.allowed
    assert caps.submit.allowed
    assert not caps.notify.allowed
    assert not caps.approve.allowed


def test_draft_withdraw_cannot_notify():
    caps = derive_shipment_notice_capabilities(_n(status="草稿", review_status="草稿"))
    assert caps.submit.allowed
    assert not caps.notify.allowed
    assert caps.notify.reason == "shipment_notice.notify.not_pending"


def test_notified_withdraw():
    caps = derive_shipment_notice_capabilities(
        _n(status="已通知", sales_delivery_id=10),
        delivery_withdrawable=True,
    )
    assert caps.withdraw.allowed
    assert not caps.update.allowed


def test_withdraw_blocked_when_delivery_processing():
    caps = derive_shipment_notice_capabilities(
        _n(status="已通知", sales_delivery_id=10),
        delivery_withdrawable=False,
    )
    assert not caps.withdraw.allowed


def test_assert_delete_notified_raises():
    with pytest.raises(BusinessLogicError):
        assert_shipment_notice_capability(_n(status="已通知"), "delete")
