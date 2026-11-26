from types import SimpleNamespace

from apps.kuaizhizao.services.document_action_policy.print_unaudited_gate import (
    PRINT_UNAUDITED_DENIED_REASON,
    apply_print_unaudited_gate_to_capabilities,
)
from apps.kuaizhizao.services.document_action_policy.purchase_order import (
    derive_purchase_order_capabilities,
)
from apps.kuaizhizao.services.document_action_policy import (
    derive_quotation_capabilities,
    derive_sales_order_capabilities,
)


def _po(status: str, review_status: str = "") -> SimpleNamespace:
    return SimpleNamespace(status=status, review_status=review_status, tenant_id=1)


def _q(status: str, review_status: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        review_status=review_status,
        tenant_id=1,
        converted_sales_order_id=None,
        converted_contract_id=None,
        converted_sales_review_id=None,
        is_latest_in_series=True,
    )


def _so(status: str, review_status: str = "") -> SimpleNamespace:
    return SimpleNamespace(status=status, review_status=review_status, tenant_id=1)


def test_gate_blocks_unapproved_when_disabled():
    for derive, record, attr in (
        (derive_sales_order_capabilities, _so("待审核", "待审核"), "print"),
        (
            lambda r: derive_quotation_capabilities(r, audit_required=False),
            _q("已发送", "待审核"),
            "print_formal",
        ),
        (derive_purchase_order_capabilities, _po("待审核", "待审核"), "print"),
    ):
        caps = derive(record)
        caps = apply_print_unaudited_gate_to_capabilities(
            caps, record, allow_print_unaudited=False
        )
        cap = getattr(caps, attr)
        assert not cap.allowed
        assert cap.reason == PRINT_UNAUDITED_DENIED_REASON


def test_gate_allows_approved_when_disabled():
    caps = derive_purchase_order_capabilities(_po("已审核", "审核通过"))
    caps = apply_print_unaudited_gate_to_capabilities(
        caps, _po("已审核", "审核通过"), allow_print_unaudited=False
    )
    assert caps.print.allowed


def test_gate_noop_when_allow_unaudited():
    caps = derive_sales_order_capabilities(_so("草稿", "待审核"))
    caps = apply_print_unaudited_gate_to_capabilities(
        caps, _so("草稿", "待审核"), allow_print_unaudited=True
    )
    assert caps.print.allowed