"""
资金调拨过账：确认写入银行流水，撤回/作废冲回流水。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from tortoise.transactions import in_transaction

from apps.common.audit_actor import apply_update_audit
from apps.kuaicaiwu.models.fund_transfer import FundTransfer
from apps.kuaicaiwu.services.bank_account_service import BankAccountService
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

_SOURCE_DOC_TYPE = "fund_transfer"
_TRANSFER_TYPES = frozenset({"internal", "external_out", "external_in"})


class FundTransferPostingService:
    @staticmethod
    def _summary(row: FundTransfer, *, leg: str) -> str:
        code = str(row.transfer_code or "").strip()
        if leg == "out":
            return f"资金调拨调出 {code}"
        if leg == "in":
            return f"资金调拨调入 {code}"
        return f"资金调拨 {code}"

    @staticmethod
    async def _assert_out_balance(
        bank_svc: BankAccountService,
        tenant_id: int,
        account_id: int,
        amount: Decimal,
    ) -> None:
        await bank_svc.assert_out_funds(tenant_id, int(account_id), amount)

    async def assert_confirmable(self, tenant_id: int, row: FundTransfer) -> None:
        transfer_type = str(row.transfer_type or "").strip()
        if transfer_type not in _TRANSFER_TYPES:
            raise ValidationError(f"未知调拨类型: {transfer_type}")
        amt = Decimal(str(row.amount or 0))
        if amt <= 0:
            raise ValidationError("调拨金额必须大于 0")

        bank_svc = BankAccountService()
        if transfer_type == "internal":
            if not row.from_bank_account_id or not row.to_bank_account_id:
                raise ValidationError("内部互转须选择调出与调入账户")
            if int(row.from_bank_account_id) == int(row.to_bank_account_id):
                raise ValidationError("调出与调入账户不能相同")
            await self._assert_out_balance(
                bank_svc, tenant_id, int(row.from_bank_account_id), amt
            )
        elif transfer_type == "external_out":
            if not row.from_bank_account_id:
                raise ValidationError("调出至外部须选择我方调出账户")
            if not str(row.external_account_name or "").strip():
                raise ValidationError("调出至外部须填写外部户名")
            if not str(row.external_bank_name or "").strip():
                raise ValidationError("调出至外部须填写外部开户行")
            if not str(row.external_account_number or "").strip():
                raise ValidationError("调出至外部须填写外部账号")
            await self._assert_out_balance(
                bank_svc, tenant_id, int(row.from_bank_account_id), amt
            )
        else:
            if not row.to_bank_account_id:
                raise ValidationError("自外部调入须选择我方调入账户")
            if not str(row.external_account_name or "").strip():
                raise ValidationError("自外部调入须填写外部户名")
            if not str(row.external_bank_name or "").strip():
                raise ValidationError("自外部调入须填写外部开户行")
            if not str(row.external_account_number or "").strip():
                raise ValidationError("自外部调入须填写外部账号")

    async def _write_leg_if_missing(
        self,
        bank_svc: BankAccountService,
        tenant_id: int,
        *,
        row: FundTransfer,
        bank_account_id: int,
        direction: str,
        leg: str,
        operator: Optional[User],
    ) -> None:
        from apps.kuaicaiwu.models.bank_transaction import BankTransaction

        exists = await BankTransaction.filter(
            tenant_id=tenant_id,
            source_doc_type=_SOURCE_DOC_TYPE,
            source_doc_id=int(row.id),
            bank_account_id=int(bank_account_id),
            direction=direction,
            deleted_at__isnull=True,
        ).exists()
        if exists:
            return
        await bank_svc.record_transaction(
            tenant_id,
            bank_account_id=int(bank_account_id),
            direction=direction,
            amount=row.amount,
            transaction_date=row.transfer_date,
            source_doc_type=_SOURCE_DOC_TYPE,
            source_doc_id=row.id,
            source_doc_code=row.transfer_code,
            summary=self._summary(row, leg=leg),
            operator=operator,
        )

    async def post(
        self,
        tenant_id: int,
        transfer_id: int,
        *,
        operator: Optional[User] = None,
    ) -> FundTransfer:
        row = await FundTransfer.get_or_none(
            tenant_id=tenant_id, id=int(transfer_id), deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError(f"资金调拨单不存在: {transfer_id}")
        if row.status not in ("Draft", "Confirmed"):
            raise ValidationError(f"当前状态不可确认: {row.status}")
        if row.status == "Draft":
            from apps.kuaicaiwu.services.fund_transfer_audit_service import (
                assert_fund_transfer_review_approved,
            )

            assert_fund_transfer_review_approved(row)

        await self.assert_confirmable(tenant_id, row)
        bank_svc = BankAccountService()
        transfer_type = str(row.transfer_type or "").strip()

        async with in_transaction():
            if transfer_type == "internal":
                await self._write_leg_if_missing(
                    bank_svc,
                    tenant_id,
                    row=row,
                    bank_account_id=int(row.from_bank_account_id),
                    direction="out",
                    leg="out",
                    operator=operator,
                )
                await self._write_leg_if_missing(
                    bank_svc,
                    tenant_id,
                    row=row,
                    bank_account_id=int(row.to_bank_account_id),
                    direction="in",
                    leg="in",
                    operator=operator,
                )
            elif transfer_type == "external_out":
                await self._write_leg_if_missing(
                    bank_svc,
                    tenant_id,
                    row=row,
                    bank_account_id=int(row.from_bank_account_id),
                    direction="out",
                    leg="out",
                    operator=operator,
                )
            else:
                await self._write_leg_if_missing(
                    bank_svc,
                    tenant_id,
                    row=row,
                    bank_account_id=int(row.to_bank_account_id),
                    direction="in",
                    leg="in",
                    operator=operator,
                )

            if row.status == "Draft":
                payload: dict = {"status": "Confirmed"}
                apply_update_audit(payload, operator)
                await FundTransfer.filter(id=row.id).update(**payload)

        refreshed = await FundTransfer.get_or_none(
            tenant_id=tenant_id, id=int(transfer_id), deleted_at__isnull=True
        )
        if not refreshed:
            raise NotFoundError(f"资金调拨单不存在: {transfer_id}")
        return refreshed

    async def unpost(
        self,
        tenant_id: int,
        transfer_id: int,
        *,
        operator_id: Optional[int] = None,
    ) -> None:
        row = await FundTransfer.get_or_none(
            tenant_id=tenant_id, id=int(transfer_id), deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError(f"资金调拨单不存在: {transfer_id}")
        if row.status != "Confirmed":
            raise ValidationError("仅已确认调拨单可冲回流水")
        bank_svc = BankAccountService()
        async with in_transaction():
            await bank_svc.reverse_from_source_doc(
                tenant_id,
                source_doc_type=_SOURCE_DOC_TYPE,
                source_doc_id=int(transfer_id),
                operator_id=operator_id,
            )
