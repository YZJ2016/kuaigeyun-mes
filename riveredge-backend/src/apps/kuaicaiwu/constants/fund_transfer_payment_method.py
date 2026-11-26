"""资金调拨付款方式（固定三项）"""

from __future__ import annotations

FUND_TRANSFER_PAYMENT_METHODS: tuple[str, ...] = ("转账", "承兑", "现金")
FUND_TRANSFER_PAYMENT_METHOD_DEFAULT = "转账"


def normalize_fund_transfer_payment_method(value: str | None) -> str:
    from infra.exceptions.exceptions import ValidationError

    raw = str(value or "").strip() or FUND_TRANSFER_PAYMENT_METHOD_DEFAULT
    if raw in FUND_TRANSFER_PAYMENT_METHODS:
        return raw
    raise ValidationError(f"付款方式须为：{'、'.join(FUND_TRANSFER_PAYMENT_METHODS)}")