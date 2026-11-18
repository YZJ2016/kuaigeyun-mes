"""付款单员工垫付台账。"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from apps.kuaicaiwu.constants.payment_method import is_employee_advance_payment_method
from apps.kuaicaiwu.models.payment import Payment
from apps.kuaicaiwu.models.payment_advance_record import PaymentAdvanceRecord
from core.utils.timezone_utils import now_utc
from infra.exceptions.exceptions import ValidationError


class PaymentAdvanceService:
    async def record_on_payment_confirmed(
        self,
        tenant_id: int,
        payment: Payment,
    ) -> Optional[PaymentAdvanceRecord]:
        if not is_employee_advance_payment_method(getattr(payment, "payment_method", None)):
            return None
        payee_id = int(getattr(payment, "advance_payee_id", 0) or 0)
        payee_name = str(getattr(payment, "advance_payee_name", "") or "").strip()
        if not payee_id or not payee_name:
            raise ValidationError("员工垫付付款单缺少领款人")

        existing = await PaymentAdvanceRecord.filter(
            tenant_id=tenant_id,
            payment_id=int(payment.id),
            deleted_at__isnull=True,
        ).first()
        if existing:
            return existing

        amount = Decimal(str(payment.total_amount or 0))
        if amount <= 0:
            raise ValidationError("垫付金额须大于 0")

        return await PaymentAdvanceRecord.create(
            tenant_id=tenant_id,
            payment_id=int(payment.id),
            payment_code=str(payment.payment_code or ""),
            supplier_id=int(payment.supplier_id),
            supplier_name=str(payment.supplier_name or ""),
            payee_id=payee_id,
            payee_name=payee_name,
            amount=amount,
            status="cleared",
            confirmed_at=now_utc(),
        )

    async def void_for_payment(
        self,
        tenant_id: int,
        payment_id: int,
    ) -> None:
        rows = await PaymentAdvanceRecord.filter(
            tenant_id=tenant_id,
            payment_id=int(payment_id),
            deleted_at__isnull=True,
        ).all()
        if not rows:
            return
        ts = now_utc()
        for row in rows:
            row.deleted_at = ts
            await row.save(update_fields=["deleted_at", "updated_at"])
