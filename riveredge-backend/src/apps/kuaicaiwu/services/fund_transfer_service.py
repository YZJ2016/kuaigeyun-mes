"""
资金调拨单业务服务
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, List, Optional, Tuple

from tortoise.expressions import Q

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.bank_account import BankAccount
from apps.kuaicaiwu.models.fund_transfer import FundTransfer
from apps.kuaicaiwu.services.fund_transfer_posting_service import FundTransferPostingService
from apps.kuaicaiwu.services.finance_voucher_codes import allocate_fund_transfer_code
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.models.user import User

_TRANSFER_TYPES = frozenset({"internal", "external_out", "external_in"})


class FundTransferService(AppBaseService[FundTransfer]):
    def __init__(self) -> None:
        super().__init__(FundTransfer)
        self._posting = FundTransferPostingService()

    @staticmethod
    def normalize_transfer_type(value: str) -> str:
        key = str(value or "").strip()
        if key not in _TRANSFER_TYPES:
            raise ValidationError("调拨类型须为 internal、external_out 或 external_in")
        return key

    def _validate_payload(
        self,
        *,
        transfer_type: str,
        from_bank_account_id: Optional[int],
        to_bank_account_id: Optional[int],
        external_account_name: Optional[str],
        external_bank_name: Optional[str],
        external_account_number: Optional[str],
        amount: Decimal,
    ) -> None:
        amt = Decimal(str(amount or 0))
        if amt <= 0:
            raise ValidationError("调拨金额必须大于 0")
        t = self.normalize_transfer_type(transfer_type)
        if t == "internal":
            if not from_bank_account_id or not to_bank_account_id:
                raise ValidationError("内部互转须选择调出与调入账户")
            if int(from_bank_account_id) == int(to_bank_account_id):
                raise ValidationError("调出与调入账户不能相同")
        elif t == "external_out":
            if not from_bank_account_id:
                raise ValidationError("调出至外部须选择我方调出账户")
            for label, val in (
                ("外部户名", external_account_name),
                ("外部开户行", external_bank_name),
                ("外部账号", external_account_number),
            ):
                if not str(val or "").strip():
                    raise ValidationError(f"调出至外部须填写{label}")
        else:
            if not to_bank_account_id:
                raise ValidationError("自外部调入须选择我方调入账户")
            for label, val in (
                ("外部户名", external_account_name),
                ("外部开户行", external_bank_name),
                ("外部账号", external_account_number),
            ):
                if not str(val or "").strip():
                    raise ValidationError(f"自外部调入须填写{label}")

    async def _resolve_currency(
        self,
        tenant_id: int,
        *,
        transfer_type: str,
        from_bank_account_id: Optional[int],
        to_bank_account_id: Optional[int],
        currency: Optional[str],
    ) -> str:
        explicit = str(currency or "").strip().upper()
        if explicit:
            return explicit
        account_id = None
        if transfer_type in ("internal", "external_out"):
            account_id = from_bank_account_id
        else:
            account_id = to_bank_account_id
        if not account_id:
            return "CNY"
        acc = await BankAccount.get_or_none(
            tenant_id=tenant_id, id=int(account_id), deleted_at__isnull=True
        )
        if not acc:
            raise ValidationError("银行账户不存在或已删除")
        return str(acc.currency or "CNY").strip().upper() or "CNY"

    async def create(
        self,
        tenant_id: int,
        *,
        transfer_date: date,
        transfer_type: str,
        amount: Decimal,
        from_bank_account_id: Optional[int] = None,
        to_bank_account_id: Optional[int] = None,
        external_account_name: Optional[str] = None,
        external_bank_name: Optional[str] = None,
        external_account_number: Optional[str] = None,
        currency: Optional[str] = None,
        notes: Optional[str] = None,
        attachments: Optional[list] = None,
        current_user: Optional[User] = None,
    ) -> FundTransfer:
        type_norm = self.normalize_transfer_type(transfer_type)
        self._validate_payload(
            transfer_type=type_norm,
            from_bank_account_id=from_bank_account_id,
            to_bank_account_id=to_bank_account_id,
            external_account_name=external_account_name,
            external_bank_name=external_bank_name,
            external_account_number=external_account_number,
            amount=amount,
        )
        cur = await self._resolve_currency(
            tenant_id,
            transfer_type=type_norm,
            from_bank_account_id=from_bank_account_id,
            to_bank_account_id=to_bank_account_id,
            currency=currency,
        )
        transfer_code = await allocate_fund_transfer_code(tenant_id)
        payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "uuid": str(uuid.uuid4()),
            "transfer_code": transfer_code,
            "transfer_date": transfer_date,
            "transfer_type": type_norm,
            "from_bank_account_id": from_bank_account_id,
            "to_bank_account_id": to_bank_account_id,
            "external_account_name": (external_account_name or None),
            "external_bank_name": (external_bank_name or None),
            "external_account_number": (external_account_number or None),
            "amount": Decimal(str(amount)),
            "currency": cur,
            "status": "Draft",
            "review_status": "草稿",
            "notes": notes,
            "attachments": attachments,
        }
        apply_create_audit(payload, current_user)
        return await FundTransfer.create(**payload)

    async def update_draft(
        self,
        tenant_id: int,
        transfer_id: int,
        *,
        data: dict[str, Any],
        current_user: Optional[User] = None,
    ) -> FundTransfer:
        row = await FundTransfer.get_or_none(
            tenant_id=tenant_id, id=int(transfer_id), deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError(f"资金调拨单不存在: {transfer_id}")
        if row.status != "Draft":
            raise ValidationError("仅草稿状态可编辑")
        from apps.kuaicaiwu.services.fund_transfer_audit_service import (
            assert_fund_transfer_review_editable,
        )

        assert_fund_transfer_review_editable(row)

        transfer_type = str(data.get("transfer_type", row.transfer_type) or row.transfer_type)
        from_id = data.get("from_bank_account_id", row.from_bank_account_id)
        to_id = data.get("to_bank_account_id", row.to_bank_account_id)
        amount = Decimal(str(data.get("amount", row.amount)))
        self._validate_payload(
            transfer_type=transfer_type,
            from_bank_account_id=from_id,
            to_bank_account_id=to_id,
            external_account_name=data.get("external_account_name", row.external_account_name),
            external_bank_name=data.get("external_bank_name", row.external_bank_name),
            external_account_number=data.get(
                "external_account_number", row.external_account_number
            ),
            amount=amount,
        )
        cur = await self._resolve_currency(
            tenant_id,
            transfer_type=transfer_type,
            from_bank_account_id=from_id,
            to_bank_account_id=to_id,
            currency=data.get("currency", row.currency),
        )
        update_fields = {
            "transfer_date": data.get("transfer_date", row.transfer_date),
            "transfer_type": self.normalize_transfer_type(transfer_type),
            "from_bank_account_id": from_id,
            "to_bank_account_id": to_id,
            "external_account_name": data.get("external_account_name", row.external_account_name),
            "external_bank_name": data.get("external_bank_name", row.external_bank_name),
            "external_account_number": data.get(
                "external_account_number", row.external_account_number
            ),
            "amount": amount,
            "currency": cur,
            "notes": data.get("notes", row.notes),
            "attachments": data.get("attachments", row.attachments),
        }
        apply_update_audit(update_fields, current_user)
        await FundTransfer.filter(id=row.id).update(**update_fields)
        refreshed = await FundTransfer.get_or_none(
            tenant_id=tenant_id, id=int(transfer_id), deleted_at__isnull=True
        )
        if not refreshed:
            raise NotFoundError(f"资金调拨单不存在: {transfer_id}")
        return refreshed

    async def list(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        keyword: Optional[str] = None,
        transfer_code: Optional[str] = None,
        transfer_type: Optional[str] = None,
        status: Optional[str] = None,
        transfer_date_start: Optional[str] = None,
        transfer_date_end: Optional[str] = None,
        sort_field: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> Tuple[List[FundTransfer], int]:
        q = FundTransfer.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if transfer_type:
            q = q.filter(transfer_type=str(transfer_type).strip())
        if status:
            q = q.filter(status=str(status).strip())
        if transfer_code:
            q = q.filter(transfer_code__icontains=str(transfer_code).strip())
        if keyword:
            kw = str(keyword).strip()
            q = q.filter(
                Q(transfer_code__icontains=kw)
                | Q(notes__icontains=kw)
                | Q(external_account_name__icontains=kw)
                | Q(external_account_number__icontains=kw)
            )
        if transfer_date_start:
            q = q.filter(transfer_date__gte=transfer_date_start)
        if transfer_date_end:
            q = q.filter(transfer_date__lte=transfer_date_end)

        order_field = "transfer_date"
        if sort_field in ("transfer_date", "amount", "status", "transfer_code", "created_at"):
            order_field = sort_field
        descending = str(sort_order or "").lower() == "descend"
        order_expr = f"-{order_field}" if descending else order_field

        total = await q.count()
        rows = await q.order_by(order_expr, "-id").offset(skip).limit(limit)
        return list(rows), total

    async def enrich_rows(self, tenant_id: int, rows: List[FundTransfer]) -> List[dict[str, Any]]:
        account_ids: set[int] = set()
        for row in rows:
            if row.from_bank_account_id:
                account_ids.add(int(row.from_bank_account_id))
            if row.to_bank_account_id:
                account_ids.add(int(row.to_bank_account_id))
        accounts: dict[int, BankAccount] = {}
        if account_ids:
            acc_rows = await BankAccount.filter(
                tenant_id=tenant_id, id__in=list(account_ids), deleted_at__isnull=True
            )
            accounts = {int(a.id): a for a in acc_rows}

        out: list[dict[str, Any]] = []
        for row in rows:
            payload = {
                k: getattr(row, k)
                for k in (
                    "id",
                    "tenant_id",
                    "transfer_code",
                    "transfer_date",
                    "transfer_type",
                    "from_bank_account_id",
                    "to_bank_account_id",
                    "external_account_name",
                    "external_bank_name",
                    "external_account_number",
                    "amount",
                    "currency",
                    "status",
                    "notes",
                    "attachments",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "created_by_name",
                    "updated_by",
                    "updated_by_name",
                )
            }
            from_acc = accounts.get(int(row.from_bank_account_id or 0))
            to_acc = accounts.get(int(row.to_bank_account_id or 0))
            if from_acc:
                payload["from_account_code"] = from_acc.account_code
                payload["from_account_name"] = from_acc.account_name
            if to_acc:
                payload["to_account_code"] = to_acc.account_code
                payload["to_account_name"] = to_acc.account_name
            out.append(payload)
        return out

    async def confirm(
        self,
        tenant_id: int,
        transfer_id: int,
        *,
        operator: Optional[User] = None,
    ) -> FundTransfer:
        return await self._posting.post(tenant_id, transfer_id, operator=operator)

    async def unconfirm(
        self,
        tenant_id: int,
        transfer_id: int,
        *,
        operator: Optional[User] = None,
    ) -> FundTransfer:
        await self._posting.unpost(
            tenant_id, transfer_id, operator_id=getattr(operator, "id", None)
        )
        payload: dict = {"status": "Draft", "review_status": "草稿"}
        apply_update_audit(payload, operator)
        await FundTransfer.filter(
            tenant_id=tenant_id, id=int(transfer_id), deleted_at__isnull=True
        ).update(**payload)
        row = await FundTransfer.get_or_none(
            tenant_id=tenant_id, id=int(transfer_id), deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError(f"资金调拨单不存在: {transfer_id}")
        return row

    async def cancel(
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
        if row.status == "Confirmed":
            await self._posting.unpost(
                tenant_id, transfer_id, operator_id=getattr(operator, "id", None)
            )
        elif row.status != "Draft":
            raise ValidationError(f"当前状态不可作废: {row.status}")
        payload = {"status": "Cancelled"}
        apply_update_audit(payload, operator)
        await FundTransfer.filter(id=row.id).update(**payload)
        refreshed = await FundTransfer.get_or_none(
            tenant_id=tenant_id, id=int(transfer_id), deleted_at__isnull=True
        )
        if not refreshed:
            raise NotFoundError(f"资金调拨单不存在: {transfer_id}")
        return refreshed
