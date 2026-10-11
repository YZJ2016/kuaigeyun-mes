"""报工记录 document_action_policy 单元测试。"""

from types import SimpleNamespace

import pytest

from apps.kuaizhizao.services.document_action_policy.reporting_record import (
    assert_reporting_record_capability,
    derive_reporting_record_capabilities,
)
from infra.exceptions.exceptions import BusinessLogicError


def test_pending_update_delete():
    caps = derive_reporting_record_capabilities(SimpleNamespace(status="pending"))
    assert caps.update.allowed
    assert caps.delete.allowed
    assert caps.approve.allowed
    assert not caps.revoke_approval.allowed


def test_approved_revoke():
    caps = derive_reporting_record_capabilities(SimpleNamespace(status="approved"))
    assert caps.revoke_approval.allowed
    assert not caps.approve.allowed
    assert not caps.update.allowed


def test_assert_revoke_on_pending_raises():
    with pytest.raises(BusinessLogicError):
        assert_reporting_record_capability(SimpleNamespace(status="pending"), "revoke_approval")


def test_approved_revoke_blocked_when_sales_outbound():
    caps = derive_reporting_record_capabilities(
        SimpleNamespace(status="approved"),
        has_posted_sales_outbound=True,
    )
    assert not caps.revoke_approval.allowed
    assert caps.revoke_approval.reason == "reporting_record.revoke_approval.has_sales_outbound"
    assert not caps.delete.allowed
    assert caps.delete.reason == "reporting_record.delete.has_sales_outbound"


def test_approved_revoke_blocked_when_approved_inbound():
    caps = derive_reporting_record_capabilities(
        SimpleNamespace(status="approved"),
        has_approved_inbound_downstream=True,
    )
    assert not caps.revoke_approval.allowed
    assert caps.revoke_approval.reason == "reporting_record.revoke_approval.has_inbound"
    assert not caps.delete.allowed
    assert caps.delete.reason == "reporting_record.delete.has_inbound"


def test_outbound_takes_precedence_over_inbound_reason():
    caps = derive_reporting_record_capabilities(
        SimpleNamespace(status="approved"),
        has_posted_sales_outbound=True,
        has_approved_inbound_downstream=True,
    )
    assert caps.revoke_approval.reason == "reporting_record.revoke_approval.has_sales_outbound"


def test_pending_delete_blocked_when_sales_outbound():
    caps = derive_reporting_record_capabilities(
        SimpleNamespace(status="pending"),
        has_posted_sales_outbound=True,
    )
    assert caps.update.allowed
    assert not caps.delete.allowed
    assert caps.approve.allowed


def test_assert_revoke_raises_when_sales_outbound():
    with pytest.raises(BusinessLogicError, match="已出库"):
        assert_reporting_record_capability(
            SimpleNamespace(status="approved"),
            "revoke_approval",
            has_posted_sales_outbound=True,
        )


def test_assert_revoke_raises_when_approved_inbound():
    with pytest.raises(BusinessLogicError, match="入库"):
        assert_reporting_record_capability(
            SimpleNamespace(status="approved"),
            "revoke_approval",
            has_approved_inbound_downstream=True,
        )


def test_assert_delete_raises_when_sales_outbound():
    with pytest.raises(BusinessLogicError, match="已出库"):
        assert_reporting_record_capability(
            SimpleNamespace(status="draft"),
            "delete",
            has_posted_sales_outbound=True,
        )
