"""客商付款方式「员工垫付」与领款人字段校验。"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from apps.master_data.config.partner_settlement_codes import (
    is_partner_employee_advance_payment_method,
)


def normalize_partner_payment_advance_payee(
    payment_method_code: Optional[str],
    advance_payee_id: Optional[int],
    advance_payee_name: Optional[str],
) -> Tuple[Optional[int], Optional[str]]:
    """员工垫付须指定领款人；其它付款方式不得携带领款人。"""
    payee_id = int(advance_payee_id) if advance_payee_id is not None else None
    if payee_id is not None and payee_id <= 0:
        payee_id = None
    payee_name = str(advance_payee_name or "").strip() or None

    if is_partner_employee_advance_payment_method(payment_method_code):
        if not payee_id or not payee_name:
            raise ValueError("员工垫付须选择领款人")
        return payee_id, payee_name

    if payee_id or payee_name:
        raise ValueError("非员工垫付不得填写领款人")
    return None, None


def apply_partner_payment_advance_payee_to_mapping(
    data: Any,
    *,
    method_key: str = "payment_method_code",
    payee_id_key: str = "advance_payee_id",
    payee_name_key: str = "advance_payee_name",
) -> Any:
    if not isinstance(data, dict):
        return data
    payee_id, payee_name = normalize_partner_payment_advance_payee(
        data.get(method_key),
        data.get(payee_id_key),
        data.get(payee_name_key),
    )
    patched = dict(data)
    patched[payee_id_key] = payee_id
    patched[payee_name_key] = payee_name
    return patched