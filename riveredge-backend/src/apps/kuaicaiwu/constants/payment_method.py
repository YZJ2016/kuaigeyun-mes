"""收付款方式常量（与前端 financeSharedOptions 存值一致）。"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from infra.exceptions.exceptions import ValidationError

BANK_TRANSFER_PAYMENT_METHOD = "银行转账"
CASH_PAYMENT_METHOD = "现金"
NOTE_PAYMENT_METHOD = "票据"
PREPAYMENT_OFFSET_PAYMENT_METHOD = "预付抵扣"
EMPLOYEE_ADVANCE_PAYMENT_METHOD = "员工垫付"


def is_employee_advance_payment_method(method: Optional[str]) -> bool:
    return str(method or "").strip() == EMPLOYEE_ADVANCE_PAYMENT_METHOD


def is_prepayment_offset_payment_method(method: Optional[str]) -> bool:
    return str(method or "").strip() == PREPAYMENT_OFFSET_PAYMENT_METHOD


def hides_supplier_payee_account(method: Optional[str]) -> bool:
    """预付抵扣/员工垫付不填供应商收款账户。"""
    return is_employee_advance_payment_method(method) or is_prepayment_offset_payment_method(method)


def normalize_payment_method(method: Optional[str]) -> str:
    return str(method or "").strip()


def assert_payment_voucher_payee_fields(
    *,
    payment_method: Optional[str],
    advance_payee_id: Optional[int],
    advance_payee_name: Optional[str],
    settlement_type: Optional[str] = None,
) -> None:
    method = normalize_payment_method(payment_method)
    if str(settlement_type or "normal") == "refund" and is_employee_advance_payment_method(method):
        raise ValidationError("退款单不可使用员工垫付")

    if is_employee_advance_payment_method(method):
        if not advance_payee_id or not str(advance_payee_name or "").strip():
            raise ValidationError("员工垫付须指定领款人")
        return

    if advance_payee_id or str(advance_payee_name or "").strip():
        raise ValidationError("非员工垫付不可填写领款人")

    if is_prepayment_offset_payment_method(method) and str(settlement_type or "normal") == "prepayment":
        raise ValidationError("预付抵扣不可与预付款结算类型同时使用")


def assert_prepayment_offset_payment_contract(
    *,
    payment_method: Optional[str],
    settlement_type: Optional[str],
    pull_lines: Optional[Sequence[Any]],
) -> None:
    """预付抵扣须普通付款 + 应付/货款申请加载明细，不可选采购订单预付款行。"""
    if not is_prepayment_offset_payment_method(payment_method):
        return
    if str(settlement_type or "normal").strip() != "normal":
        raise ValidationError("预付抵扣须使用普通付款结算类型")
    lines = list(pull_lines or [])
    if not lines:
        raise ValidationError("预付抵扣须加载应付或货款类付款申请明细")
    for line in lines:
        if isinstance(line, dict):
            source_type = str(line.get("source_type") or "").strip()
        else:
            source_type = str(getattr(line, "source_type", "") or "").strip()
        if source_type == "purchase_order":
            raise ValidationError("预付抵扣不可加载采购订单预付款明细")
        if source_type not in ("payable", "payment_application"):
            raise ValidationError(f"预付抵扣不支持的加载来源: {source_type or '未知'}")


def assert_payment_application_payee_fields(
    *,
    payment_method: Optional[str],
    advance_payee_id: Optional[int],
    advance_payee_name: Optional[str],
) -> None:
    if is_employee_advance_payment_method(payment_method):
        if not advance_payee_id or not str(advance_payee_name or "").strip():
            raise ValidationError("员工垫付须指定领款人")
        return
    if advance_payee_id or str(advance_payee_name or "").strip():
        raise ValidationError("非员工垫付不可填写领款人")
