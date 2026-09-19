"""委外退货触发的红字结算单。"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from tortoise.transactions import in_transaction

from apps.common.audit_actor import apply_create_audit
from apps.kuaizhizao.models.outsource_settlement import OutsourceSettlement, OutsourceSettlementItem
from apps.kuaizhizao.models.outsource_work_order import (
    OutsourceMaterialReceipt,
    OutsourceProductReturn,
    OutsourceWorkOrder,
)
from apps.kuaizhizao.services.outsource_settlement_service import OutsourceSettlementService
from apps.kuaizhizao.utils.outsource_settlement_helpers import (
    LINE_TYPE_RETURN_CREDIT,
    SETTLEMENT_KIND_CREDIT,
    SOURCE_DOC_OUTSOURCE_PRODUCT_RETURN,
    receipt_base_qty,
)
from infra.exceptions.exceptions import ValidationError
from infra.models.user import User


class OutsourceSettlementCreditService:
    @classmethod
    async def _find_last_settled_unit_price(
        cls,
        tenant_id: int,
        receipt_id: int,
    ) -> Decimal:
        from apps.kuaizhizao.utils.outsource_settlement_helpers import LINE_TYPE_PROCESSING

        proc_items = await OutsourceSettlementItem.filter(
            tenant_id=tenant_id,
            outsource_material_receipt_id=receipt_id,
            line_type=LINE_TYPE_PROCESSING,
            deleted_at__isnull=True,
        ).order_by("-id").all()
        settlement_ids = {i.settlement_id for i in proc_items}
        if settlement_ids:
            audited = await OutsourceSettlement.filter(
                tenant_id=tenant_id,
                id__in=list(settlement_ids),
                status="已审核",
                deleted_at__isnull=True,
            ).all()
            audited_ids = {s.id for s in audited}
            for item in sorted(proc_items, key=lambda x: x.id, reverse=True):
                if item.settlement_id in audited_ids:
                    return Decimal(str(item.unit_price or 0))

        receipt = await OutsourceMaterialReceipt.get(tenant_id=tenant_id, id=receipt_id)
        return Decimal(str(receipt.unit_price or 0))

    @classmethod
    async def _pending_credit_qty(
        cls,
        tenant_id: int,
        receipt_id: int,
    ) -> Decimal:
        items = await OutsourceSettlementItem.filter(
            tenant_id=tenant_id,
            outsource_material_receipt_id=receipt_id,
            line_type=LINE_TYPE_RETURN_CREDIT,
            deleted_at__isnull=True,
        ).all()
        if not items:
            return Decimal("0")
        settlement_ids = {i.settlement_id for i in items}
        open_settlements = await OutsourceSettlement.filter(
            tenant_id=tenant_id,
            id__in=list(settlement_ids),
            status__in=["草稿", "待审核"],
            deleted_at__isnull=True,
        ).all()
        open_ids = {s.id for s in open_settlements}
        total = Decimal("0")
        for item in items:
            if item.settlement_id in open_ids:
                total += abs(Decimal(str(item.settlement_quantity or 0)))
        return total

    @classmethod
    async def _load_operator(cls, operator_id: int) -> User:
        user = await User.get_or_none(id=operator_id)
        if not user:
            raise ValidationError(f"用户不存在: {operator_id}")
        return user

    @classmethod
    async def create_credit_draft_for_return(
        cls,
        tenant_id: int,
        product_return: OutsourceProductReturn,
        operator_id: int,
    ) -> Optional[OutsourceSettlement]:
        operator = await cls._load_operator(operator_id)
        if product_return.credit_settlement_id:
            existing = await OutsourceSettlement.filter(
                tenant_id=tenant_id,
                id=product_return.credit_settlement_id,
                deleted_at__isnull=True,
            ).first()
            if existing:
                return existing

        receipt_id = int(product_return.outsource_material_receipt_id or 0)
        if receipt_id <= 0:
            return None

        receipt = await OutsourceMaterialReceipt.filter(
            tenant_id=tenant_id,
            id=receipt_id,
            deleted_at__isnull=True,
        ).first()
        if not receipt:
            return None

        settled = Decimal(str(receipt.settled_quantity or 0))
        if settled <= 0:
            return None

        return_qty = Decimal(str(product_return.quantity or 0))
        pending_credit = await cls._pending_credit_qty(tenant_id, receipt_id)
        creditable = min(return_qty, settled - pending_credit)
        if creditable <= 0:
            return None

        work_order = await OutsourceWorkOrder.filter(
            tenant_id=tenant_id,
            id=receipt.outsource_work_order_id,
            deleted_at__isnull=True,
        ).first()
        if not work_order:
            raise ValidationError(f"委外工单不存在: {receipt.outsource_work_order_id}")

        unit_price = await cls._find_last_settled_unit_price(tenant_id, receipt_id)
        credit_qty = -creditable
        amount = (credit_qty * unit_price).quantize(Decimal("0.01"))

        async with in_transaction():
            header_payload = {
                "tenant_id": tenant_id,
                "settlement_code": OutsourceSettlementService._gen_settlement_code(),
                "supplier_id": work_order.supplier_id,
                "supplier_code": work_order.supplier_code,
                "supplier_name": work_order.supplier_name,
                "business_date": None,
                "total_amount": amount,
                "status": "草稿",
                "settlement_kind": SETTLEMENT_KIND_CREDIT,
                "auto_generated": True,
                "source_doc_type": SOURCE_DOC_OUTSOURCE_PRODUCT_RETURN,
                "source_doc_id": product_return.id,
                "notes": f"委外退货 {product_return.code} 自动生成红字结算",
            }
            apply_create_audit(header_payload, operator)
            settlement = await OutsourceSettlement.create(**header_payload)

            item_payload = {
                "tenant_id": tenant_id,
                "settlement_id": settlement.id,
                "line_no": 1,
                "line_type": LINE_TYPE_RETURN_CREDIT,
                "outsource_material_receipt_id": receipt.id,
                "receipt_code": receipt.code,
                "outsource_work_order_id": work_order.id,
                "outsource_work_order_code": work_order.code,
                "product_code": work_order.product_code,
                "product_name": work_order.product_name,
                "unit": receipt.unit,
                "outsource_product_return_id": product_return.id,
                "settlement_quantity": credit_qty,
                "unit_price": unit_price,
                "amount": amount,
                "notes": product_return.return_reason,
            }
            apply_create_audit(item_payload, operator)
            await OutsourceSettlementItem.create(**item_payload)

            await OutsourceProductReturn.filter(
                tenant_id=tenant_id,
                id=product_return.id,
            ).update(credit_settlement_id=settlement.id)

        from loguru import logger

        logger.info(
            "委外退货 {} 已自动生成红字结算单 {}，待财务审核",
            product_return.code,
            settlement.settlement_code,
        )

        return settlement
