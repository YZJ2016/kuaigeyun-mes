"""
采购订单预付付款单自动核销至应付（对标销售出库后预收冲应收）。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Optional

from apps.kuaicaiwu.constants.finance_source_types import is_payable_red_total_source
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.models.payment import Payment
from apps.kuaizhizao.models.document_relation import DocumentRelation
from infra.domain.tenant_context import get_current_tenant_id, set_current_tenant_id
from infra.exceptions.exceptions import BusinessLogicError

logger = logging.getLogger(__name__)

_MONEY = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


class PayablePrepaymentApplyService:
    @staticmethod
    def _push_tenant_context(tenant_id: int) -> Optional[int]:
        """核销链路依赖组织上下文；返回进入前的 tenant_id（可能为 None），供 finally 还原。"""
        prev = get_current_tenant_id()
        set_current_tenant_id(int(tenant_id))
        return prev

    @staticmethod
    def _restore_tenant_context(prev: Optional[int]) -> None:
        set_current_tenant_id(prev)

    async def _payment_ids_for_purchase_order(
        self, tenant_id: int, purchase_order_id: int
    ) -> List[int]:
        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_order",
            source_id=int(purchase_order_id),
            target_type="payment",
        ).all()
        return [int(r.target_id) for r in relations if r.target_id]

    async def sum_unused_prepayment_for_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: Optional[int],
    ) -> Decimal:
        """采购订单关联「已确认」预付付款单的未核销余额。"""
        if not purchase_order_id:
            return Decimal("0")
        payment_ids = await self._payment_ids_for_purchase_order(
            tenant_id, int(purchase_order_id)
        )
        if not payment_ids:
            return Decimal("0")
        payments = await Payment.filter(
            tenant_id=tenant_id,
            id__in=payment_ids,
            settlement_type="prepayment",
            status="Confirmed",
            deleted_at__isnull=True,
        ).all()
        total = Decimal("0")
        for row in payments:
            total += _money(row.unsettled_amount)
        return max(Decimal("0"), total)

    async def apply_prepayment_to_payable(
        self,
        tenant_id: int,
        *,
        payable_id: int,
        purchase_order_id: Optional[int],
        amount: Decimal,
        operator_id: int,
    ) -> Decimal:
        """按 FIFO 将采购订单已确认预付付款单核销到应付单，返回实际核销金额。"""
        apply_total = _money(amount)
        if apply_total <= 0 or not purchase_order_id:
            return Decimal("0.00")

        from apps.kuaicaiwu.services.prepayment_service import PrepaymentService

        payment_ids = await self._payment_ids_for_purchase_order(
            tenant_id, int(purchase_order_id)
        )
        if not payment_ids:
            logger.warning(
                "apply_prepayment_to_payable no po→payment relation tenant_id=%s po_id=%s payable_id=%s",
                tenant_id,
                purchase_order_id,
                payable_id,
            )
            return Decimal("0.00")

        payments = await Payment.filter(
            tenant_id=tenant_id,
            id__in=payment_ids,
            settlement_type="prepayment",
            status="Confirmed",
            unsettled_amount__gt=0,
            deleted_at__isnull=True,
        ).order_by("id").all()
        if not payments:
            logger.warning(
                "apply_prepayment_to_payable no confirmed unsettled prepayment "
                "tenant_id=%s po_id=%s payable_id=%s payment_ids=%s",
                tenant_id,
                purchase_order_id,
                payable_id,
                payment_ids,
            )
            return Decimal("0.00")

        remaining = apply_total
        applied = Decimal("0.00")
        prep_svc = PrepaymentService()
        prev_tenant = self._push_tenant_context(tenant_id)
        try:
            for payment in payments:
                if remaining <= 0:
                    break
                payable = await Payable.get_or_none(
                    tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
                )
                if not payable:
                    break
                pay_remaining = _money(payable.remaining_amount)
                if pay_remaining <= 0:
                    break
                # 每笔前重读付款余额，避免同批 FIFO 使用过期 unsettled
                fresh_payment = await Payment.get_or_none(
                    tenant_id=tenant_id, id=int(payment.id), deleted_at__isnull=True
                )
                if not fresh_payment:
                    continue
                unsettled = _money(fresh_payment.unsettled_amount)
                if unsettled <= 0:
                    continue
                chunk = min(remaining, unsettled, pay_remaining)
                if chunk <= 0:
                    continue
                await prep_svc.apply_payment_to_payable(
                    tenant_id,
                    payment_id=int(payment.id),
                    payable_id=int(payable_id),
                    amount=chunk,
                    operator_id=operator_id,
                )
                applied += chunk
                remaining -= chunk
        finally:
            self._restore_tenant_context(prev_tenant)
        return applied.quantize(_MONEY)

    async def resolve_purchase_order_id_for_payable(
        self,
        tenant_id: int,
        payable_id: int,
    ) -> Optional[int]:
        """解析应付单关联的采购订单。有订单时预付抵扣须用同订单预付；没有订单时不限制预付池。"""
        payable = await Payable.get_or_none(
            tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
        )
        if not payable:
            return None
        source_type = str(getattr(payable, "source_type", "") or "").strip()
        source_id = getattr(payable, "source_id", None)
        if source_type == "purchase_order" and source_id:
            return int(source_id)
        if source_type == "purchase_receipt" and source_id:
            from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

            receipt = await PurchaseReceipt.get_or_none(
                tenant_id=tenant_id, id=int(source_id), deleted_at__isnull=True
            )
            if receipt and receipt.purchase_order_id:
                return int(receipt.purchase_order_id)
        rel = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_order",
            target_type="payable",
            target_id=int(payable_id),
        ).first()
        if rel and rel.source_id:
            return int(rel.source_id)
        return None

    async def list_open_payable_ids_for_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
    ) -> List[int]:
        """同 PO 下仍有待付余额的应付单（入库立账 + 里程碑），FIFO 按 id。"""
        payable_ids: set[int] = set()

        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipt_ids = await PurchaseReceipt.filter(
            tenant_id=tenant_id,
            purchase_order_id=int(purchase_order_id),
            deleted_at__isnull=True,
        ).values_list("id", flat=True)
        if receipt_ids:
            rows = await Payable.filter(
                tenant_id=tenant_id,
                source_id__in=list(receipt_ids),
                remaining_amount__gt=0,
                deleted_at__isnull=True,
            ).order_by("id").all()
            for row in rows:
                if is_payable_red_total_source(getattr(row, "source_type", None)):
                    continue
                payable_ids.add(int(row.id))

        try:
            from apps.kuaizhizao.models.purchase_order_milestone import PurchaseOrderMilestone

            milestones = await PurchaseOrderMilestone.filter(
                tenant_id=tenant_id,
                purchase_order_id=int(purchase_order_id),
                payable_id__isnull=False,
            ).all()
            ms_payable_ids = [int(m.payable_id) for m in milestones if m.payable_id]
            if ms_payable_ids:
                rows = await Payable.filter(
                    tenant_id=tenant_id,
                    id__in=ms_payable_ids,
                    remaining_amount__gt=0,
                    deleted_at__isnull=True,
                ).all()
                for row in rows:
                    if is_payable_red_total_source(getattr(row, "source_type", None)):
                        continue
                    payable_ids.add(int(row.id))
        except Exception:
            logger.debug("list open payables: milestone model unavailable", exc_info=True)

        rel_payables = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_order",
            source_id=int(purchase_order_id),
            target_type="payable",
        ).all()
        rel_ids = [int(r.target_id) for r in rel_payables if r.target_id]
        if rel_ids:
            rows = await Payable.filter(
                tenant_id=tenant_id,
                id__in=rel_ids,
                remaining_amount__gt=0,
                deleted_at__isnull=True,
            ).all()
            for row in rows:
                if is_payable_red_total_source(getattr(row, "source_type", None)):
                    continue
                payable_ids.add(int(row.id))

        return sorted(payable_ids)

    async def auto_apply_after_payable_created(
        self,
        tenant_id: int,
        *,
        payable_id: int,
        purchase_order_id: Optional[int],
        operator_id: int,
    ) -> Decimal:
        """应付开立后按组织参数自动冲减同 PO 未核销预付。"""
        from apps.common.app_orm import finance_orm_ready

        if not finance_orm_ready():
            logger.warning(
                "auto_apply_after_payable_created skip: finance_orm not ready "
                "tenant_id=%s payable_id=%s",
                tenant_id,
                payable_id,
            )
            return Decimal("0.00")
        if not purchase_order_id:
            logger.warning(
                "auto_apply_after_payable_created skip: no purchase_order_id "
                "tenant_id=%s payable_id=%s",
                tenant_id,
                payable_id,
            )
            return Decimal("0.00")

        from infra.services.business_config_service import BusinessConfigService

        enabled = await BusinessConfigService().get_finance_auto_apply_supplier_prepayment_to_payable(
            tenant_id
        )
        if not enabled:
            logger.info(
                "auto_apply_after_payable_created skip: config disabled "
                "tenant_id=%s payable_id=%s",
                tenant_id,
                payable_id,
            )
            return Decimal("0.00")

        payable = await Payable.get_or_none(
            tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
        )
        if not payable:
            logger.warning(
                "auto_apply_after_payable_created skip: payable missing "
                "tenant_id=%s payable_id=%s",
                tenant_id,
                payable_id,
            )
            return Decimal("0.00")
        if is_payable_red_total_source(getattr(payable, "source_type", None)):
            return Decimal("0.00")
        remaining = _money(payable.remaining_amount)
        if remaining <= 0:
            return Decimal("0.00")

        prepaid_avail = await self.sum_unused_prepayment_for_purchase_order(
            tenant_id, int(purchase_order_id)
        )
        apply_amount = min(remaining, prepaid_avail)
        if apply_amount <= 0:
            logger.info(
                "auto_apply_after_payable_created skip: no prepaid balance "
                "tenant_id=%s payable_id=%s po_id=%s remaining=%s prepaid=%s",
                tenant_id,
                payable_id,
                purchase_order_id,
                remaining,
                prepaid_avail,
            )
            return Decimal("0.00")

        applied = await self.apply_prepayment_to_payable(
            tenant_id,
            payable_id=int(payable_id),
            purchase_order_id=int(purchase_order_id),
            amount=apply_amount,
            operator_id=operator_id,
        )
        if applied <= 0:
            # 有可冲余额却写成 0：不得静默，入库确认侧会记 exception，便于立刻发现
            raise BusinessLogicError(
                f"采购预付自动冲应付未写入核销：应付单 {payable_id} 应对冲 {apply_amount}，"
                f"实际核销 0（采购订单 {purchase_order_id}）"
            )
        if applied < apply_amount:
            logger.warning(
                "auto_apply_prepayment_after_payable partial tenant_id=%s payable_id=%s "
                "po_id=%s expected=%s applied=%s",
                tenant_id,
                payable_id,
                purchase_order_id,
                apply_amount,
                applied,
            )
        else:
            logger.info(
                "auto_apply_prepayment_after_payable tenant_id=%s payable_id=%s po_id=%s applied=%s",
                tenant_id,
                payable_id,
                purchase_order_id,
                applied,
            )
        return applied

    async def auto_apply_after_prepayment_confirmed(
        self,
        tenant_id: int,
        *,
        payment_id: int,
        operator_id: int,
    ) -> Decimal:
        """
        预付付款单确认后：若同 PO 已有未付清应付，按 FIFO 冲减。
        覆盖「先立应付、后确认预付」时序。
        """
        from apps.common.app_orm import finance_orm_ready

        if not finance_orm_ready():
            logger.warning(
                "auto_apply_after_prepayment_confirmed skip: finance_orm not ready "
                "tenant_id=%s payment_id=%s",
                tenant_id,
                payment_id,
            )
            return Decimal("0.00")

        from infra.services.business_config_service import BusinessConfigService

        enabled = await BusinessConfigService().get_finance_auto_apply_supplier_prepayment_to_payable(
            tenant_id
        )
        if not enabled:
            return Decimal("0.00")

        payment = await Payment.get_or_none(
            tenant_id=tenant_id, id=int(payment_id), deleted_at__isnull=True
        )
        if not payment:
            return Decimal("0.00")
        if str(getattr(payment, "settlement_type", "") or "") != "prepayment":
            return Decimal("0.00")
        if str(getattr(payment, "status", "") or "") != "Confirmed":
            return Decimal("0.00")
        if _money(payment.unsettled_amount) <= 0:
            return Decimal("0.00")

        relations = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_order",
            target_type="payment",
            target_id=int(payment_id),
        ).all()
        po_ids = sorted({int(r.source_id) for r in relations if r.source_id})
        if not po_ids:
            logger.info(
                "auto_apply_after_prepayment_confirmed skip: no po relation "
                "tenant_id=%s payment_id=%s",
                tenant_id,
                payment_id,
            )
            return Decimal("0.00")

        total_applied = Decimal("0.00")
        for po_id in po_ids:
            payable_ids = await self.list_open_payable_ids_for_purchase_order(tenant_id, po_id)
            for payable_id in payable_ids:
                fresh = await Payment.get_or_none(
                    tenant_id=tenant_id, id=int(payment_id), deleted_at__isnull=True
                )
                unsettled = _money(fresh.unsettled_amount if fresh else 0)
                if unsettled <= 0:
                    break
                payable = await Payable.get_or_none(
                    tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
                )
                if not payable:
                    continue
                remaining = _money(payable.remaining_amount)
                if remaining <= 0:
                    continue
                chunk = min(unsettled, remaining)
                applied = await self.apply_prepayment_to_payable(
                    tenant_id,
                    payable_id=int(payable_id),
                    purchase_order_id=int(po_id),
                    amount=chunk,
                    operator_id=operator_id,
                )
                total_applied += applied
        if total_applied > 0:
            logger.info(
                "auto_apply_prepayment_after_confirm tenant_id=%s payment_id=%s applied=%s",
                tenant_id,
                payment_id,
                total_applied,
            )
        else:
            fresh_payment = await Payment.get_or_none(
                tenant_id=tenant_id, id=int(payment_id), deleted_at__isnull=True
            )
            if fresh_payment and _money(fresh_payment.unsettled_amount) > 0:
                for po_id in po_ids:
                    open_ids = await self.list_open_payable_ids_for_purchase_order(
                        tenant_id, po_id
                    )
                    if open_ids:
                        raise BusinessLogicError(
                            f"预付确认后自动冲应付未写入核销：付款单 {payment_id} 仍有待核销余额，"
                            f"采购订单 {po_id} 存在未结清应付"
                        )
        return total_applied.quantize(_MONEY)

    async def enrich_purchase_order_prepayment_snapshot(
        self,
        tenant_id: int,
        *,
        purchase_order_id: int,
        order_total_amount: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """返回 (未核销预付余额, 预计待付扣预付)。"""
        from apps.common.app_orm import finance_orm_ready

        if not finance_orm_ready():
            return Decimal("0.00"), Decimal("0.00")
        unsettled = await self.sum_unused_prepayment_for_purchase_order(
            tenant_id, purchase_order_id
        )
        gross = _money(order_total_amount)
        estimated_net = max(Decimal("0.00"), (gross - unsettled).quantize(_MONEY))
        return unsettled, estimated_net
