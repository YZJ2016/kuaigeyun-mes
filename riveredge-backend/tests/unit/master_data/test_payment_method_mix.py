from decimal import Decimal

import pytest

from apps.master_data.config.payment_method_mix import (
    PARTNER_MIXED_PAYMENT_METHOD,
    apply_payment_method_mix_to_mapping,
    format_payment_method_mix_label_zh,
    normalize_payment_method_mix,
    validate_payment_method_mix,
)


def test_mixed_requires_percents_sum_100():
    code, wire, acc = normalize_payment_method_mix(
        PARTNER_MIXED_PAYMENT_METHOD, 60, 40
    )
    assert code == PARTNER_MIXED_PAYMENT_METHOD
    assert wire == Decimal("60.00")
    assert acc == Decimal("40.00")


def test_mixed_rejects_incomplete():
    with pytest.raises(ValueError, match="须分别填写"):
        normalize_payment_method_mix(PARTNER_MIXED_PAYMENT_METHOD, 60, None)


def test_mixed_rejects_sum_not_100():
    with pytest.raises(ValueError, match="合计须为 100"):
        normalize_payment_method_mix(PARTNER_MIXED_PAYMENT_METHOD, 60, 30)


def test_single_method_clears_percents():
    code, wire, acc = normalize_payment_method_mix("bank_transfer", None, None)
    assert code == "bank_transfer"
    assert wire is None
    assert acc is None


def test_single_method_rejects_percents():
    with pytest.raises(ValueError, match="不得填写比例"):
        validate_payment_method_mix("cash", 50, 50)


def test_format_mix_label():
    assert format_payment_method_mix_label_zh(60, 40) == "电汇60% 承兑40%"


def test_apply_mapping_before_validator():
    patched = apply_payment_method_mix_to_mapping(
        {"payment_method_code": PARTNER_MIXED_PAYMENT_METHOD, "payment_wire_percent": 70, "payment_acceptance_percent": 30}
    )
    assert patched["payment_wire_percent"] == Decimal("70.00")


def test_sales_order_response_construct_no_recursion():
    from datetime import date, datetime, timezone

    from apps.kuaizhizao.schemas.sales_order import SalesOrderResponse

    now = datetime.now(timezone.utc)
    row = SalesOrderResponse.model_construct(
        id=1,
        uuid="u",
        tenant_id=1,
        customer_id=1,
        customer_name="c",
        order_date=date.today(),
        delivery_date=date.today(),
        created_at=now,
        updated_at=now,
        payment_method_code="bank_transfer",
    )
    row.delivery_progress = 12.5
    row.items = []
    row.model_dump()
    SalesOrderResponse.model_validate(
        {
            "id": 1,
            "uuid": "u",
            "tenant_id": 1,
            "customer_id": 1,
            "customer_name": "c",
            "order_date": date.today(),
            "delivery_date": date.today(),
            "created_at": now,
            "updated_at": now,
            "payment_method_code": "bank_transfer",
        }
    )


def test_purchase_order_list_construct_assignment_no_recursion():
    from datetime import date, datetime, timezone

    from apps.kuaizhizao.schemas.purchase import PurchaseOrderListResponse

    now = datetime.now(timezone.utc)
    row = PurchaseOrderListResponse.model_construct(
        id=1,
        tenant_id=1,
        supplier_id=1,
        supplier_name="s",
        order_date=date.today(),
        delivery_date=date.today(),
        review_status="PENDING",
        created_at=now,
        updated_at=now,
        payment_method_code="bank_transfer",
    )
    row.items = []
    row.lifecycle = {"stage": "draft"}
    row.model_dump()