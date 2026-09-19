"""委外结算与应付衔接（含红字差额）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from apps.kuaicaiwu.constants.finance_source_types import (
    PAYABLE_SOURCE_OUTSOURCE_RECEIPT,
    PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT,
    PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT_CREDIT,
)
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.schemas.finance import PayableCreate
from apps.kuaicaiwu.services.finance_due_date import resolve_partner_due_date
from apps.kuaicaiwu.services.finance_integration_hooks import (
    link_finance_document_relation,
    record_finance_accounting_event,
)
from apps.kuaicaiwu.services.finance_service import PayableService
from apps.kuaizhizao.models.outsource_settlement import OutsourceSettlement
from apps.kuaizhizao.utils.outsource_settlement_helpers import SETTLEMENT_KIND_CREDIT
from infra.exceptions.exceptions import BusinessLogicError, ValidationError


class OutsourceSettlementFinanceBridge:
    @classmethod
    async def sum_provisional_payables(
        cls,
        tenant_id: int,
        receipt_ids: Sequence[int],
    ) -> Decimal:
        if not receipt_ids:
            return Decimal("0")
        rows = await Payable.filter(
            tenant_id=tenant_id,
            source_type=PAYABLE_SOURCE_OUTSOURCE_RECEIPT,
            source_id__in=list(receipt_ids),
            deleted_at__isnull=True,
            is_active=True,
        ).all()
        return sum((Decimal(str(r.total_amount or 0)) for r in rows), Decimal("0")).quantize(Decimal("0.01"))

    @classmethod
    async def create_settlement_payable_delta(
        cls,
        *,
        tenant_id: int,
        settlement: OutsourceSettlement,
        receipt_ids: Sequence[int],
        created_by: int,
    ) -> Optional[int]:
        settlement_total = Decimal(str(settlement.total_amount or 0))
        provisional = await cls.sum_provisional_payables(tenant_id, receipt_ids)
        diff = (settlement_total - provisional).quantize(Decimal("0.01"))
        if diff == 0:
            return None

        biz_date = settlement.business_date
        if biz_date is None:
            raise ValidationError("审核前须填写业务日期")

        due_date = await resolve_partner_due_date(
            tenant_id, "supplier", int(settlement.supplier_id), biz_date
        )
        payable_service = PayableService()

        if diff > 0:
            source_type = PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT
            notes = (
                f"委外结算单 {settlement.settlement_code} 差额应付"
                f"（结算 {settlement_total}，暂估 {provisional}）"
            )
        else:
            source_type = PAYABLE_SOURCE_OUTSOURCE_SETTLEMENT_CREDIT
            notes = (
                f"委外结算单 {settlement.settlement_code} 红字差额应付"
                f"（结算 {settlement_total}，暂估 {provisional}）"
            )

        payable_data = PayableCreate(
            source_type=source_type,
            source_id=settlement.id,
            source_code=settlement.settlement_code,
            supplier_id=settlement.supplier_id,
            supplier_name=settlement.supplier_name,
            total_amount=float(diff),
            paid_amount=0.0,
            remaining_amount=float(diff),
            due_date=due_date,
            business_date=biz_date,
            status="未付款" if diff > 0 else "已冲减",
            notes=notes,
        )
        payable = await payable_service.create_payable(
            tenant_id=tenant_id,
            payable_data=payable_data,
            created_by=created_by,
        )
        relation_desc = "委外结算审核生成差额应付" if diff > 0 else "委外结算审核生成红字差额应付"
        await link_finance_document_relation(
            tenant_id=tenant_id,
            source_type="outsource_settlement",
            source_id=settlement.id,
            source_code=settlement.settlement_code,
            target_type="payable",
            target_id=payable.id,
            target_code=getattr(payable, "payable_code", None),
            relation_desc=relation_desc,
            created_by=created_by,
        )
        await record_finance_accounting_event(
            tenant_id=tenant_id,
            event_type="OUTSOURCE_SETTLEMENT_TO_PAYABLE",
            business_type="payable",
            source_doc_type="outsource_settlement",
            source_doc_id=settlement.id,
            source_doc_code=settlement.settlement_code,
            target_doc_type="Payable",
            target_doc_id=payable.id,
            target_doc_code=payable.payable_code,
            amount=diff,
            operator_id=created_by,
            notes=notes,
        )
        return payable.id

    @classmethod
    async def assert_payable_revokable(cls, tenant_id: int, payable_id: Optional[int]) -> None:
        if not payable_id:
            return
        payable = await Payable.filter(
            tenant_id=tenant_id,
            id=payable_id,
            deleted_at__isnull=True,
        ).first()
        if not payable:
            return
        paid = Decimal(str(payable.paid_amount or 0))
        if paid > 0:
            raise BusinessLogicError("关联应付单已有付款，不可撤回审核")

    @classmethod
    async def soft_delete_payable(cls, tenant_id: int, payable_id: Optional[int]) -> None:
        if not payable_id:
            return
        from core.utils.timezone_utils import resolve_business_datetime

        await Payable.filter(id=payable_id, tenant_id=tenant_id).update(
            deleted_at=resolve_business_datetime(),
            is_active=False,
        )

    @classmethod
    def requires_payable_on_audit(
        cls,
        settlement: OutsourceSettlement,
        diff: Decimal,
    ) -> bool:
        if getattr(settlement, "settlement_kind", "normal") == SETTLEMENT_KIND_CREDIT:
            return False
        return diff > 0
