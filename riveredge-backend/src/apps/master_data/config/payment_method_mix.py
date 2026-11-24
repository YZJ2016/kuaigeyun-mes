"""组合付款方式（电汇+承兑）比例校验与展示。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional, Tuple

from apps.master_data.config.partner_settlement_codes import coerce_partner_payment_method_code

PARTNER_MIXED_PAYMENT_METHOD = "bank_transfer_and_acceptance"
_MIX_SUM_TOLERANCE = Decimal("0.01")


def _coerce_percent(value: Optional[object]) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        dec = Decimal(str(value))
    except Exception as exc:
        raise ValueError("无效的付款比例") from exc
    if dec < 0 or dec > 100:
        raise ValueError("付款比例须在 0～100 之间")
    return dec.quantize(Decimal("0.01"))


def normalize_payment_method_mix(
    payment_method_code: Optional[str],
    wire_percent: Optional[object],
    acceptance_percent: Optional[object],
) -> Tuple[Optional[str], Optional[Decimal], Optional[Decimal]]:
    code = coerce_partner_payment_method_code(payment_method_code)
    wire = _coerce_percent(wire_percent)
    acceptance = _coerce_percent(acceptance_percent)
    if code == PARTNER_MIXED_PAYMENT_METHOD:
        if wire is None or acceptance is None:
            raise ValueError("电汇+银行承兑须分别填写电汇与承兑比例")
        total = wire + acceptance
        if abs(total - Decimal("100")) > _MIX_SUM_TOLERANCE:
            raise ValueError("电汇与承兑比例合计须为 100%")
        return code, wire, acceptance
    if wire is not None or acceptance is not None:
        raise ValueError("非组合付款方式不得填写比例")
    return code, None, None


def validate_payment_method_mix(
    payment_method_code: Optional[str],
    wire_percent: Optional[object],
    acceptance_percent: Optional[object],
) -> None:
    normalize_payment_method_mix(payment_method_code, wire_percent, acceptance_percent)


def apply_payment_method_mix_to_mapping(data: Any, *, skip_when_all_missing: bool = False) -> Any:
    """Pydantic mode=before：归一化付款方式组合字段，避免 after 赋值 + validate_assignment 递归。"""
    if not isinstance(data, dict):
        return data
    if skip_when_all_missing and (
        data.get("payment_method_code") is None
        and data.get("payment_wire_percent") is None
        and data.get("payment_acceptance_percent") is None
    ):
        return data
    code, wire, acceptance = normalize_payment_method_mix(
        data.get("payment_method_code"),
        data.get("payment_wire_percent"),
        data.get("payment_acceptance_percent"),
    )
    patched = dict(data)
    patched["payment_method_code"] = code
    patched["payment_wire_percent"] = wire
    patched["payment_acceptance_percent"] = acceptance
    return patched


def format_payment_method_mix_label_zh(
    wire_percent: Optional[object],
    acceptance_percent: Optional[object],
) -> Optional[str]:
    wire = _coerce_percent(wire_percent)
    acceptance = _coerce_percent(acceptance_percent)
    if wire is None or acceptance is None:
        return None
    w = wire.quantize(Decimal("0.01"))
    a = acceptance.quantize(Decimal("0.01"))
    return f"电汇{w:.2f}".rstrip("0").rstrip(".") + f"% 承兑{a:.2f}".rstrip("0").rstrip(".") + "%"