"""其他费用收入/支出过账服务。

与收付款过账的差异：仅写入银行流水，不产生应收应付、不做往来核销。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from apps.common.audit_actor import apply_update_audit
from apps.kuaicaiwu.models.other_voucher import OtherExpense, OtherIncome
from apps.kuaicaiwu.services.bank_account_service import BankAccountService
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

_LABELS = {"other_income": "其他费用收入单", "other_expense": "其他费用支出单"}


def misc_voucher_model(voucher_type: str):
    if voucher_type == "other_income":
        return OtherIncome
    if voucher_type == "other_expense":
        return OtherExpense
    raise ValidationError(f"不支持的其他收支单据类型: {voucher_type}")


def misc_voucher_label(voucher_type: str) -> str:
    return _LABELS.get(voucher_type, voucher_type)


class MiscVoucherPostingService:
    """其他费用收入/支出确认过账（仅银行流水）。"""

    async def post(
        self,
        tenant_id: int,
        *,
        voucher_type: str,
        voucher_id: int,
        operator: Optional[User] = None,
        operator_id: Optional[int] = None,
    ):
        model = misc_voucher_model(voucher_type)
        label = misc_voucher_label(voucher_type)
        row = await model.get_or_none(
            tenant_id=tenant_id, id=voucher_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError(f"{label}不存在: {voucher_id}")
        if row.status not in ("Approved", "Confirmed"):
            raise ValidationError(f"只有已审核的{label}可以确认过账，当前状态: {row.status}")

        op_id = operator_id or (operator.id if operator else None)
        if op_id is None:
            raise ValidationError("缺少操作人")

        bank_svc = BankAccountService()
        await bank_svc.validate_voucher_account(
            tenant_id,
            payment_method=row.payment_method,
            bank_account_id=row.bank_account_id,
        )
        if voucher_type == "other_expense" and row.bank_account_id:
            amt = Decimal(str(row.total_amount or 0))
            if amt > 0:
                account = await bank_svc.get_by_id(tenant_id, int(row.bank_account_id))
                current = Decimal(str(account.current_balance or 0))
                if current - amt < 0:
                    raise ValidationError(
                        f"账户 {account.account_code} 余额不足，当前 {current}，本次出款 {amt}"
                    )

        was_approved = row.status == "Approved"
        try:
            if row.bank_account_id:
                await bank_svc.sync_from_confirmed_voucher(
                    tenant_id,
                    voucher_type=voucher_type,
                    voucher_id=voucher_id,
                    operator_id=op_id,
                )
            if was_approved:
                payload: dict = {"status": "Confirmed"}
                apply_update_audit(payload, operator)
                await model.filter(id=voucher_id).update(**payload)
            return await model.get_or_none(
                tenant_id=tenant_id, id=voucher_id, deleted_at__isnull=True
            )
        except Exception:
            if was_approved:
                await bank_svc.reverse_from_voucher(
                    tenant_id,
                    voucher_type=voucher_type,
                    voucher_id=voucher_id,
                    operator_id=op_id,
                )
            raise

    async def unpost(
        self,
        tenant_id: int,
        *,
        voucher_type: str,
        voucher_id: int,
        operator: Optional[User] = None,
        operator_id: Optional[int] = None,
    ):
        """撤回确认：冲回银行流水并回到已审核。"""
        model = misc_voucher_model(voucher_type)
        label = misc_voucher_label(voucher_type)
        row = await model.get_or_none(
            tenant_id=tenant_id, id=voucher_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError(f"{label}不存在: {voucher_id}")
        if row.status != "Confirmed":
            raise ValidationError("仅已确认单据可撤回确认")

        op_id = operator_id or (operator.id if operator else None)
        bank_svc = BankAccountService()
        await bank_svc.reverse_from_voucher(
            tenant_id,
            voucher_type=voucher_type,
            voucher_id=voucher_id,
            operator_id=op_id,
        )
        payload: dict = {"status": "Approved"}
        apply_update_audit(payload, operator)
        await model.filter(id=voucher_id).update(**payload)
        return await model.get_or_none(
            tenant_id=tenant_id, id=voucher_id, deleted_at__isnull=True
        )
