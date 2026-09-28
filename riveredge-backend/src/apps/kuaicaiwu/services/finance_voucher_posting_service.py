"""
收付款单过账服务。

主流 ERP 统一规则：草稿不产生资金流水与往来核销；确认（过账）后一次性执行。

过账顺序：账户校验 → 余额预检 → 资金流水 → 往来核销 → 状态确认。
任一步失败则回滚本单已写流水，并保持/恢复为草稿，避免「列表仍显示草稿、库内已确认」。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from apps.common.audit_actor import apply_update_audit
from apps.kuaicaiwu.models.payment import Payment
from apps.kuaicaiwu.models.receipt import Receipt
from apps.kuaicaiwu.services.bank_account_service import BankAccountService
from apps.kuaicaiwu.services.payment_pull_service import PaymentPullService
from apps.kuaicaiwu.services.receipt_pull_service import ReceiptPullService
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User


class FinanceVoucherPostingService:
    """收款单 / 付款单确认过账（核销 + 资金流水）。"""

    @staticmethod
    async def _assert_bank_funds_for_voucher(
        bank_svc: BankAccountService,
        tenant_id: int,
        *,
        voucher_type: str,
        row: Payment | Receipt,
    ) -> None:
        """确认前预检出款余额；不足则保持草稿，不改单据状态。"""
        bank_account_id = getattr(row, "bank_account_id", None)
        if not bank_account_id:
            return
        is_refund = str(getattr(row, "settlement_type", "") or "") == "refund"
        if voucher_type == "payment":
            direction = "in" if is_refund else "out"
        else:
            direction = "out" if is_refund else "in"
        if direction != "out":
            return
        amt = Decimal(str(getattr(row, "total_amount", None) or 0))
        if amt <= 0:
            return
        account = await bank_svc.get_by_id(tenant_id, int(bank_account_id))
        current = Decimal(str(account.current_balance or 0))
        if current - amt < 0:
            raise ValidationError(
                f"账户 {account.account_code} 余额不足，当前 {current}，本次出款 {amt}"
            )

    async def _finalize_receipt_confirmed(
        self,
        *,
        tenant_id: int,
        receipt_id: int,
        operator: Optional[User],
    ) -> Receipt:
        receipt = await Receipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            raise NotFoundError(f"收款单不存在: {receipt_id}")
        if receipt.status == "Draft":
            confirm_payload: dict = {"status": "Confirmed"}
            apply_update_audit(confirm_payload, operator)
            await Receipt.filter(id=receipt_id).update(**confirm_payload)
            receipt = await Receipt.get_or_none(
                tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
            )
            if not receipt:
                raise NotFoundError(f"收款单不存在: {receipt_id}")
        return receipt

    async def _finalize_payment_confirmed(
        self,
        *,
        tenant_id: int,
        payment_id: int,
        operator: Optional[User],
    ) -> Payment:
        payment = await Payment.get_or_none(
            tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
        )
        if not payment:
            raise NotFoundError(f"付款单不存在: {payment_id}")
        if payment.status == "Draft":
            confirm_payload: dict = {"status": "Confirmed"}
            apply_update_audit(confirm_payload, operator)
            await Payment.filter(id=payment_id).update(**confirm_payload)
            payment = await Payment.get_or_none(
                tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
            )
            if not payment:
                raise NotFoundError(f"付款单不存在: {payment_id}")
        return payment

    async def post_receipt(
        self,
        tenant_id: int,
        receipt_id: int,
        *,
        operator: Optional[User] = None,
        operator_id: Optional[int] = None,
    ) -> Receipt:
        receipt = await Receipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if not receipt:
            raise NotFoundError(f"收款单不存在: {receipt_id}")
        if receipt.status not in ("Draft", "Confirmed"):
            raise ValidationError("只有草稿或待补流水的收款单可以过账")

        op_id = operator_id or (operator.id if operator else None)
        if op_id is None:
            raise ValidationError("缺少操作人")

        bank_svc = BankAccountService()
        await bank_svc.validate_voucher_account(
            tenant_id,
            payment_method=receipt.payment_method,
            bank_account_id=receipt.bank_account_id,
        )
        await self._assert_bank_funds_for_voucher(
            bank_svc, tenant_id, voucher_type="receipt", row=receipt
        )

        was_draft = receipt.status == "Draft"
        try:
            if receipt.bank_account_id:
                await bank_svc.sync_from_confirmed_voucher(
                    tenant_id,
                    voucher_type="receipt",
                    voucher_id=receipt_id,
                    operator_id=op_id,
                )
            if was_draft:
                pull_svc = ReceiptPullService()
                await pull_svc.settle_draft_receipt_if_linked(
                    tenant_id=tenant_id,
                    receipt_id=receipt_id,
                    operator_id=op_id,
                )
            return await self._finalize_receipt_confirmed(
                tenant_id=tenant_id,
                receipt_id=receipt_id,
                operator=operator,
            )
        except Exception:
            if was_draft:
                await bank_svc.reverse_from_voucher(
                    tenant_id,
                    voucher_type="receipt",
                    voucher_id=receipt_id,
                    operator_id=op_id,
                )
                revert_payload: dict = {"status": "Draft"}
                apply_update_audit(revert_payload, operator)
                await Receipt.filter(id=receipt_id).update(**revert_payload)
            raise

    async def post_payment(
        self,
        tenant_id: int,
        payment_id: int,
        *,
        operator: Optional[User] = None,
        operator_id: Optional[int] = None,
    ) -> Payment:
        payment = await Payment.get_or_none(
            tenant_id=tenant_id, id=payment_id, deleted_at__isnull=True
        )
        if not payment:
            raise NotFoundError(f"付款单不存在: {payment_id}")
        if payment.status not in ("Draft", "Confirmed"):
            raise ValidationError("只有草稿或待补流水的付款单可以过账")

        op_id = operator_id or (operator.id if operator else None)
        if op_id is None:
            raise ValidationError("缺少操作人")

        bank_svc = BankAccountService()
        await bank_svc.validate_voucher_account(
            tenant_id,
            payment_method=payment.payment_method,
            bank_account_id=payment.bank_account_id,
        )
        await self._assert_bank_funds_for_voucher(
            bank_svc, tenant_id, voucher_type="payment", row=payment
        )

        was_draft = payment.status == "Draft"
        try:
            if payment.bank_account_id:
                await bank_svc.sync_from_confirmed_voucher(
                    tenant_id,
                    voucher_type="payment",
                    voucher_id=payment_id,
                    operator_id=op_id,
                )
            if was_draft:
                pull_svc = PaymentPullService()
                await pull_svc.settle_draft_payment_if_linked(
                    tenant_id=tenant_id,
                    payment_id=payment_id,
                    operator_id=op_id,
                )
            return await self._finalize_payment_confirmed(
                tenant_id=tenant_id,
                payment_id=payment_id,
                operator=operator,
            )
        except Exception:
            if was_draft:
                await bank_svc.reverse_from_voucher(
                    tenant_id,
                    voucher_type="payment",
                    voucher_id=payment_id,
                    operator_id=op_id,
                )
                revert_payload: dict = {"status": "Draft"}
                apply_update_audit(revert_payload, operator)
                await Payment.filter(id=payment_id).update(**revert_payload)
            raise
