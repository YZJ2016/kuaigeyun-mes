"""付款单加载明细校验（单元）。"""

import pytest

from decimal import Decimal
from types import SimpleNamespace

from apps.kuaicaiwu.constants.payment_method import (
    assert_prepayment_offset_payment_contract,
)
from apps.kuaicaiwu.services.payment_pull_service import PaymentPullService
from apps.kuaicaiwu.services.receipt_pull_service import ReceiptPullService
from infra.exceptions.exceptions import BusinessLogicError, ValidationError


def test_prepayment_offset_contract_requires_normal_and_payable_lines():
    with pytest.raises(ValidationError, match="普通付款"):
        assert_prepayment_offset_payment_contract(
            payment_method="预付抵扣",
            settlement_type="prepayment",
            pull_lines=[],
        )
    with pytest.raises(ValidationError, match="须加载"):
        assert_prepayment_offset_payment_contract(
            payment_method="预付抵扣",
            settlement_type="normal",
            pull_lines=[],
            offset_prepayment_lines=[{"prepayment_payment_id": 1, "amount": 1}],
        )
    with pytest.raises(ValidationError, match="预付款明细"):
        assert_prepayment_offset_payment_contract(
            payment_method="预付抵扣",
            settlement_type="normal",
            pull_lines=[{"source_type": "payable", "source_id": 1}],
            offset_prepayment_lines=[],
        )
    with pytest.raises(ValidationError, match="采购订单"):
        assert_prepayment_offset_payment_contract(
            payment_method="预付抵扣",
            settlement_type="normal",
            pull_lines=[{"source_type": "purchase_order", "source_id": 1}],
            offset_prepayment_lines=[{"prepayment_payment_id": 1, "amount": 1}],
        )
    with pytest.raises(ValidationError, match="仅支持应付"):
        assert_prepayment_offset_payment_contract(
            payment_method="预付抵扣",
            settlement_type="normal",
            pull_lines=[{"source_type": "payment_application", "source_id": 1}],
            offset_prepayment_lines=[{"prepayment_payment_id": 1, "amount": 1}],
        )


def test_normalize_source_ids_dedupes():
    svc = PaymentPullService()
    assert svc._normalize_source_ids([3, 3, 5]) == [3, 5]


def test_normalize_source_ids_requires_one():
    svc = PaymentPullService()
    with pytest.raises(BusinessLogicError):
        svc._normalize_source_ids([])


@pytest.mark.asyncio
async def test_validate_pull_lines_rejects_mixed_sources():
    svc = PaymentPullService()
    lines = [
        SimpleNamespace(source_type="payable", source_id=1, amount=Decimal("10")),
        SimpleNamespace(source_type="payment_application", source_id=2, amount=Decimal("10")),
    ]
    with pytest.raises(BusinessLogicError, match="不可混选"):
        await svc.validate_pull_lines_for_create(
            1,
            pull_lines=lines,
            total_amount=Decimal("20"),
        )


@pytest.mark.asyncio
async def test_validate_pull_lines_total_must_match(monkeypatch):
    svc = PaymentPullService()

    async def _allow(**_kwargs):
        return {}

    monkeypatch.setattr(svc, "assert_pull_create_allowed", _allow)

    lines = [
        SimpleNamespace(source_type="payable", source_id=1, amount=Decimal("10")),
    ]
    with pytest.raises(BusinessLogicError, match="明细合计"):
        await svc.validate_pull_lines_for_create(
            1,
            pull_lines=lines,
            total_amount=Decimal("15"),
        )


@pytest.mark.asyncio
async def test_validate_pull_lines_purchase_order_requires_prepayment():
    svc = PaymentPullService()
    lines = [
        SimpleNamespace(source_type="purchase_order", source_id=1, amount=Decimal("10")),
    ]
    with pytest.raises(BusinessLogicError, match="预付款"):
        await svc.validate_pull_lines_for_create(
            1,
            pull_lines=lines,
            total_amount=Decimal("10"),
            settlement_type="normal",
        )


@pytest.mark.asyncio
async def test_validate_pull_lines_accepts_dict_payable_line(monkeypatch):
    svc = PaymentPullService()

    async def _allow(**_kwargs):
        return {}

    monkeypatch.setattr(svc, "assert_pull_create_allowed", _allow)

    lines = [{"source_type": "payable", "source_id": 101, "amount": Decimal("80.00")}]
    preview = await svc.validate_pull_lines_for_create(
        1,
        pull_lines=lines,
        total_amount=Decimal("80.00"),
    )
    assert preview == {}


@pytest.mark.asyncio
async def test_validate_pull_lines_accepts_multi_payable_total(monkeypatch):
    svc = PaymentPullService()

    async def _allow(**_kwargs):
        return {}

    monkeypatch.setattr(svc, "assert_pull_create_allowed", _allow)

    lines = [
        SimpleNamespace(source_type="payable", source_id=101, amount=Decimal("50.00")),
        SimpleNamespace(source_type="payable", source_id=102, amount=Decimal("30.00")),
    ]
    preview = await svc.validate_pull_lines_for_create(
        1,
        pull_lines=lines,
        total_amount=Decimal("80.00"),
    )
    assert preview == {}


def test_normal_payment_requires_settlement_source_flags():
    svc = PaymentPullService()
    prepay = SimpleNamespace(settlement_type="prepayment", unsettled_amount=Decimal("100"), settled_amount=Decimal("0"))
    assert svc.normal_payment_requires_settlement_source_before_confirm(prepay) is False

    merged = SimpleNamespace(settlement_type="normal", unsettled_amount=Decimal("0"), settled_amount=Decimal("100"))
    assert svc.normal_payment_requires_settlement_source_before_confirm(merged) is False

    draft = SimpleNamespace(settlement_type="normal", unsettled_amount=Decimal("100"), settled_amount=Decimal("0"))
    assert svc.normal_payment_requires_settlement_source_before_confirm(draft) is True


@pytest.mark.asyncio
async def test_resolve_payable_settlement_fallback_when_application_lines_marked_paid(
    monkeypatch,
):
    """补核销：申请行 paid 已满但应付未核销时，仍按待核销与应付剩余分摊。"""
    svc = PaymentPullService()
    payment = SimpleNamespace(
        settlement_type="normal",
        unsettled_amount=Decimal("10000"),
        total_amount=Decimal("10000"),
    )
    app_line = SimpleNamespace(
        id=1,
        payable_id=99,
        line_kind="goods",
        request_amount=Decimal("10000"),
        paid_amount=Decimal("10000"),
    )

    async def _payable_get(**_kwargs):
        return SimpleNamespace(remaining_amount=Decimal("10000"))

    monkeypatch.setattr(
        "apps.kuaicaiwu.services.payment_pull_service.Payable.get_or_none",
        _payable_get,
    )

    amounts = await svc._resolve_payable_settlement_amounts_from_application(
        1,
        lines=[app_line],
        pay_basis=Decimal("10000"),
        payment=payment,
    )
    assert amounts == {99: Decimal("10000")}


def test_normal_receipt_requires_settlement_source_flags():
    svc = ReceiptPullService()
    prepay = SimpleNamespace(settlement_type="prepayment", unsettled_amount=Decimal("50"), settled_amount=Decimal("0"))
    assert svc.normal_receipt_requires_settlement_source_before_confirm(prepay) is False

    merged = SimpleNamespace(settlement_type="normal", unsettled_amount=Decimal("0"), settled_amount=Decimal("50"))
    assert svc.normal_receipt_requires_settlement_source_before_confirm(merged) is False

    draft = SimpleNamespace(settlement_type="normal", unsettled_amount=Decimal("50"), settled_amount=Decimal("0"))
    assert svc.normal_receipt_requires_settlement_source_before_confirm(draft) is True
