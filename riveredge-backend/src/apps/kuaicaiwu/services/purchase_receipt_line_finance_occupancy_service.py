"""
采购入库行财务占用：写入时 FIFO 分摊（按明细 id 升序），报表只读汇总。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Mapping

from tortoise.functions import Sum

from apps.common.base_service import AppBaseService
from apps.kuaicaiwu.models.purchase_receipt_line_finance_occupancy import (
    PurchaseReceiptLineFinanceOccupancy,
)
from infra.exceptions.exceptions import BusinessLogicError, ValidationError

_MONEY = Decimal("0.01")
_QTY = Decimal("0.0001")
_KIND_PAYABLE = "payable"
_KIND_INVOICE = "invoice"
_KIND_PAID = "paid"


def _q_money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


def _q_qty(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(_QTY)


class PurchaseReceiptLineFinanceOccupancyService(AppBaseService):
    async def _sum_occupied_by_item(
        self,
        tenant_id: int,
        receipt_id: int,
        occupancy_kind: str,
    ) -> Dict[int, Decimal]:
        rows = await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            purchase_receipt_id=receipt_id,
            occupancy_kind=occupancy_kind,
            deleted_at__isnull=True,
        ).annotate(total=Sum("amount")).group_by("purchase_receipt_item_id").values(
            "purchase_receipt_item_id", "total"
        )
        return {int(r["purchase_receipt_item_id"]): _q_money(r["total"]) for r in rows}

    async def _fifo_slices(
        self,
        tenant_id: int,
        receipt_id: int,
        amount: Decimal,
        occupancy_kind: str,
        line_amount_caps: Optional[Mapping[int, Decimal]] = None,
    ) -> List[Tuple[int, Decimal, Decimal]]:
        from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

        amt = _q_money(amount)
        if amt <= 0:
            return []

        items = await PurchaseReceiptItem.filter(
            tenant_id=tenant_id,
            receipt_id=receipt_id,
            deleted_at__isnull=True,
        ).order_by("id").all()
        if not items:
            raise ValidationError("采购入库单无明细，无法分摊财务占用")

        occupied = await self._sum_occupied_by_item(tenant_id, receipt_id, occupancy_kind)
        remaining = amt
        slices: List[Tuple[int, Decimal, Decimal]] = []

        for item in items:
            if remaining <= 0:
                break
            if line_amount_caps is not None:
                line_cap = _q_money(line_amount_caps.get(int(item.id), Decimal("0")))
            else:
                line_cap = _q_money(item.total_amount or 0)
            if line_cap <= 0:
                continue
            used = occupied.get(int(item.id), Decimal("0"))
            cap = line_cap - used
            if cap <= 0:
                continue
            take = min(cap, remaining)
            line_qty = Decimal(str(item.receipt_quantity or 0))
            if line_amount_caps is not None and line_cap > 0:
                take_qty = _q_qty((take / line_cap) * line_qty)
            else:
                unit_price = Decimal(str(item.unit_price or 0))
                if unit_price > 0:
                    take_qty = (take / unit_price).quantize(_QTY)
                    if take_qty > line_qty:
                        take_qty = _q_qty(line_qty)
                elif take == cap:
                    take_qty = _q_qty(line_qty)
                else:
                    take_qty = Decimal("0")
            slices.append((int(item.id), take_qty, take))
            remaining -= take

        if remaining > _MONEY:
            raise BusinessLogicError(
                f"入库单可分摊{occupancy_kind}金额不足，剩余 {remaining} 无法按行占用"
            )
        return slices

    async def record_receipt_finance_occupancy(
        self,
        tenant_id: int,
        receipt_id: int,
        *,
        occupancy_kind: str,
        amount: Decimal,
        target_doc_type: str,
        target_doc_id: int,
        created_by: Optional[int] = None,
        line_amount_caps: Optional[Mapping[int, Decimal]] = None,
    ) -> None:
        """按 FIFO 写入行占用（同一 target 重复调用前应由调用方保证幂等）。"""
        existing = await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            occupancy_kind=occupancy_kind,
            target_doc_type=target_doc_type,
            target_doc_id=int(target_doc_id),
            deleted_at__isnull=True,
        ).count()
        if existing > 0:
            return

        slices = await self._fifo_slices(
            tenant_id,
            receipt_id,
            amount,
            occupancy_kind,
            line_amount_caps=line_amount_caps,
        )
        if not slices:
            return

        await self._persist_slices(
            tenant_id,
            receipt_id,
            occupancy_kind=occupancy_kind,
            target_doc_type=target_doc_type,
            target_doc_id=target_doc_id,
            slices=slices,
            created_by=created_by,
        )

    async def record_receipt_finance_occupancy_explicit(
        self,
        tenant_id: int,
        receipt_id: int,
        *,
        occupancy_kind: str,
        target_doc_type: str,
        target_doc_id: int,
        slices: List[Tuple[int, Decimal, Decimal]],
        created_by: Optional[int] = None,
        allow_append: bool = False,
    ) -> None:
        """按用户勾选的入库行写入占用（须先通过 pull_lines 校验）。"""
        if not allow_append:
            existing = await PurchaseReceiptLineFinanceOccupancy.filter(
                tenant_id=tenant_id,
                occupancy_kind=occupancy_kind,
                target_doc_type=target_doc_type,
                target_doc_id=int(target_doc_id),
                deleted_at__isnull=True,
            ).count()
            if existing > 0:
                return
        if not slices:
            return
        await self._persist_slices(
            tenant_id,
            receipt_id,
            occupancy_kind=occupancy_kind,
            target_doc_type=target_doc_type,
            target_doc_id=target_doc_id,
            slices=slices,
            created_by=created_by,
        )

    async def _persist_slices(
        self,
        tenant_id: int,
        receipt_id: int,
        *,
        occupancy_kind: str,
        target_doc_type: str,
        target_doc_id: int,
        slices: List[Tuple[int, Decimal, Decimal]],
        created_by: Optional[int] = None,
    ) -> None:
        user_name = None
        if created_by:
            user_name = (await self.get_user_info(created_by)).get("name")

        for item_id, qty, slice_amt in slices:
            await PurchaseReceiptLineFinanceOccupancy.create(
                tenant_id=tenant_id,
                purchase_receipt_id=int(receipt_id),
                purchase_receipt_item_id=item_id,
                occupancy_kind=occupancy_kind,
                quantity=qty,
                amount=slice_amt,
                target_doc_type=target_doc_type,
                target_doc_id=int(target_doc_id),
                created_by=created_by,
                created_by_name=user_name,
                updated_by=created_by,
                updated_by_name=user_name,
            )

    async def record_invoice_from_payable_to_receipt_lines(
        self,
        tenant_id: int,
        payable_id: int,
        invoice_id: int,
        invoice_amount: Decimal,
        *,
        created_by: Optional[int] = None,
        allow_append: bool = False,
    ) -> None:
        """从应付开进项：按应付行占用比例分摊收票占用；无应付行占用则对该入库单 FIFO。"""
        from apps.kuaicaiwu.models.payable import Payable
        from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
            resolve_purchase_receipt_id_from_payable,
        )
        from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

        amt = _q_money(invoice_amount)
        if amt <= 0:
            return

        if not allow_append:
            existing = await PurchaseReceiptLineFinanceOccupancy.filter(
                tenant_id=tenant_id,
                occupancy_kind=_KIND_INVOICE,
                target_doc_type="PurchaseInvoice",
                target_doc_id=int(invoice_id),
                deleted_at__isnull=True,
            ).count()
            if existing > 0:
                return

        payable = await Payable.get_or_none(
            tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
        )
        if not payable:
            return

        receipt_id = resolve_purchase_receipt_id_from_payable(
            str(getattr(payable, "source_type", "") or ""),
            getattr(payable, "source_id", None),
        )
        if not receipt_id:
            return

        base_rows = await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            occupancy_kind=_KIND_PAYABLE,
            target_doc_type="Payable",
            target_doc_id=int(payable_id),
            deleted_at__isnull=True,
        ).all()
        if not base_rows:
            if allow_append:
                slices = await self._fifo_slices(
                    tenant_id, receipt_id, amt, _KIND_INVOICE
                )
                if slices:
                    await self._persist_slices(
                        tenant_id,
                        receipt_id,
                        occupancy_kind=_KIND_INVOICE,
                        target_doc_type="PurchaseInvoice",
                        target_doc_id=int(invoice_id),
                        slices=slices,
                        created_by=created_by,
                    )
            else:
                await self.record_receipt_finance_occupancy(
                    tenant_id,
                    receipt_id,
                    occupancy_kind=_KIND_INVOICE,
                    amount=amt,
                    target_doc_type="PurchaseInvoice",
                    target_doc_id=int(invoice_id),
                    created_by=created_by,
                )
            return

        invoice_occupied = await self._sum_occupied_by_item(
            tenant_id, receipt_id, _KIND_INVOICE
        )
        item_ids = [int(r.purchase_receipt_item_id) for r in base_rows]
        items = await PurchaseReceiptItem.filter(
            tenant_id=tenant_id,
            id__in=item_ids,
            deleted_at__isnull=True,
        ).all()
        line_cap_by_item = {
            int(i.id): _q_money(i.total_amount or 0) for i in items
        }

        total_base = sum(_q_money(r.amount) for r in base_rows)
        if total_base <= 0:
            return

        allocated = Decimal("0")
        ordered = sorted(base_rows, key=lambda r: int(r.purchase_receipt_item_id))
        slices: List[Tuple[int, Decimal, Decimal]] = []

        for idx, row in enumerate(ordered):
            if idx == len(ordered) - 1:
                share = amt - allocated
            else:
                share = _q_money(amt * _q_money(row.amount) / total_base)
                allocated += share
            if share <= 0:
                continue
            item_id = int(row.purchase_receipt_item_id)
            line_cap = line_cap_by_item.get(item_id, Decimal("0"))
            used = invoice_occupied.get(item_id, Decimal("0"))
            remain = _q_money(line_cap - used)
            if remain <= 0:
                raise BusinessLogicError(
                    f"入库明细 {item_id} 可收票金额不足，无法从应付单分摊"
                )
            if share > remain + _MONEY:
                raise BusinessLogicError(
                    f"入库明细 {item_id} 收票分摊 {share} 超过行可收票余量 {remain}"
                )
            invoice_occupied[item_id] = _q_money(used + share)

            base_qty = _q_qty(row.quantity)
            inv_qty = (
                _q_qty(base_qty * share / _q_money(row.amount))
                if _q_money(row.amount) > 0
                else Decimal("0")
            )
            slices.append((item_id, inv_qty, share))

        if not slices:
            return
        await self.record_receipt_finance_occupancy_explicit(
            tenant_id,
            receipt_id,
            occupancy_kind=_KIND_INVOICE,
            target_doc_type="PurchaseInvoice",
            target_doc_id=int(invoice_id),
            slices=slices,
            created_by=created_by,
            allow_append=allow_append,
        )

    async def record_payable_settlement_to_lines(
        self,
        tenant_id: int,
        payable_id: int,
        settlement_amount: Decimal,
        settlement_id: int,
        *,
        created_by: Optional[int] = None,
    ) -> None:
        """付款核销：按该行应付占用比例分摊到入库行（写入时落库，非报表猜测）。"""
        amt = _q_money(settlement_amount)
        if amt <= 0:
            return

        base_rows = await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            occupancy_kind=_KIND_PAYABLE,
            target_doc_type="Payable",
            target_doc_id=int(payable_id),
            deleted_at__isnull=True,
        ).all()
        if not base_rows:
            return

        total_base = sum(_q_money(r.amount) for r in base_rows)
        if total_base <= 0:
            return

        user_name = None
        if created_by:
            user_name = (await self.get_user_info(created_by)).get("name")

        allocated = Decimal("0")
        ordered = sorted(base_rows, key=lambda r: int(r.purchase_receipt_item_id))
        for idx, row in enumerate(ordered):
            if idx == len(ordered) - 1:
                share = amt - allocated
            else:
                share = _q_money(amt * _q_money(row.amount) / total_base)
                allocated += share
            if share <= 0:
                continue
            base_qty = _q_qty(row.quantity)
            paid_qty = (
                _q_qty(base_qty * share / _q_money(row.amount))
                if _q_money(row.amount) > 0
                else Decimal("0")
            )
            await PurchaseReceiptLineFinanceOccupancy.create(
                tenant_id=tenant_id,
                purchase_receipt_id=int(row.purchase_receipt_id),
                purchase_receipt_item_id=int(row.purchase_receipt_item_id),
                occupancy_kind=_KIND_PAID,
                quantity=paid_qty,
                amount=share,
                target_doc_type="SettlementRecord",
                target_doc_id=int(settlement_id),
                created_by=created_by,
                created_by_name=user_name,
                updated_by=created_by,
                updated_by_name=user_name,
            )

    async def release_occupancy_for_purchase_return(
        self,
        tenant_id: int,
        purchase_return_id: int,
        *,
        created_by: Optional[int] = None,
    ) -> None:
        """采购退货确认后按明细回退入库行应付/收票/付款占用（负向占用行，幂等）。"""
        from apps.kuaizhizao.models.purchase_return import PurchaseReturn
        from apps.kuaizhizao.models.purchase_return_item import PurchaseReturnItem

        ret = await PurchaseReturn.get_or_none(
            tenant_id=tenant_id, id=int(purchase_return_id), deleted_at__isnull=True
        )
        if not ret:
            return
        existing = await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            target_doc_type="PurchaseReturn",
            target_doc_id=int(purchase_return_id),
            deleted_at__isnull=True,
        ).count()
        if existing > 0:
            return

        items = await PurchaseReturnItem.filter(
            tenant_id=tenant_id, return_id=int(purchase_return_id)
        ).all()
        user_name = None
        if created_by:
            user_name = (await self.get_user_info(created_by)).get("name")

        for item in items:
            item_id = getattr(item, "purchase_receipt_item_id", None)
            if not item_id:
                continue
            try:
                receipt_item_id = int(item_id)
            except (TypeError, ValueError):
                continue
            qty = _q_qty(item.return_quantity or 0)
            line_amt = _q_money(item.total_amount or 0)
            if line_amt <= 0 and qty > 0:
                line_amt = _q_money(qty * Decimal(str(item.unit_price or 0)))
            if line_amt <= 0:
                continue

            receipt_id = int(ret.purchase_receipt_id or 0)
            if receipt_id <= 0:
                from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

                pri = await PurchaseReceiptItem.get_or_none(
                    tenant_id=tenant_id, id=receipt_item_id, deleted_at__isnull=True
                )
                if not pri:
                    continue
                receipt_id = int(pri.receipt_id)

            for kind in (_KIND_PAYABLE, _KIND_INVOICE, _KIND_PAID):
                used = await self._sum_occupied_by_item(tenant_id, receipt_id, kind)
                cap = _q_money(used.get(receipt_item_id, Decimal("0")))
                release_amt = min(line_amt, cap)
                if release_amt <= 0:
                    continue
                unit_price = Decimal(str(item.unit_price or 0))
                release_qty = Decimal("0")
                if unit_price > 0:
                    release_qty = (release_amt / unit_price).quantize(_QTY)
                    if release_qty > qty:
                        release_qty = qty
                elif release_amt == cap:
                    release_qty = qty
                await PurchaseReceiptLineFinanceOccupancy.create(
                    tenant_id=tenant_id,
                    purchase_receipt_id=receipt_id,
                    purchase_receipt_item_id=receipt_item_id,
                    occupancy_kind=kind,
                    quantity=-release_qty,
                    amount=-release_amt,
                    target_doc_type="PurchaseReturn",
                    target_doc_id=int(purchase_return_id),
                    created_by=created_by,
                    created_by_name=user_name,
                    updated_by=created_by,
                    updated_by_name=user_name,
                )

    async def soft_delete_by_target(
        self,
        tenant_id: int,
        target_doc_type: str,
        target_doc_id: int,
    ) -> None:
        from core.utils.timezone_utils import resolve_business_datetime

        now = resolve_business_datetime()
        await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            target_doc_type=target_doc_type,
            target_doc_id=int(target_doc_id),
            deleted_at__isnull=True,
        ).update(deleted_at=now)

    async def sums_by_receipt_item_ids(
        self,
        tenant_id: int,
        item_ids: List[int],
    ) -> Dict[int, Dict[str, float]]:
        ids = [int(i) for i in item_ids if int(i) > 0]
        if not ids:
            return {}

        rows = await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            purchase_receipt_item_id__in=ids,
            deleted_at__isnull=True,
        ).annotate(
            qty_sum=Sum("quantity"),
            amt_sum=Sum("amount"),
        ).group_by("purchase_receipt_item_id", "occupancy_kind").values(
            "purchase_receipt_item_id", "occupancy_kind", "qty_sum", "amt_sum"
        )

        out: Dict[int, Dict[str, float]] = {}
        for r in rows:
            iid = int(r["purchase_receipt_item_id"])
            kind = str(r["occupancy_kind"] or "")
            bucket = out.setdefault(
                iid,
                {
                    "payable_quantity": 0.0,
                    "payable_amount": 0.0,
                    "invoice_quantity": 0.0,
                    "invoice_amount": 0.0,
                    "paid_quantity": 0.0,
                    "paid_amount": 0.0,
                },
            )
            qty = float(r.get("qty_sum") or 0)
            amt = float(r.get("amt_sum") or 0)
            if kind == _KIND_PAYABLE:
                bucket["payable_quantity"] = qty
                bucket["payable_amount"] = amt
            elif kind == _KIND_INVOICE:
                bucket["invoice_quantity"] = qty
                bucket["invoice_amount"] = amt
            elif kind == _KIND_PAID:
                bucket["paid_quantity"] = qty
                bucket["paid_amount"] = amt
        return out


async def _line_gross_caps_for_receipt(
    tenant_id: int,
    receipt_id: int,
) -> Dict[int, Decimal]:
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
    from apps.kuaicaiwu.services.purchase_settlement import (
        compute_purchase_receipt_line_settlement_amounts,
    )
    from apps.kuaizhizao.models.purchase_order import PurchaseOrderItem

    receipt = await PurchaseReceipt.get_or_none(tenant_id=tenant_id, id=receipt_id)
    if not receipt:
        return {}
    items = await PurchaseReceiptItem.filter(
        tenant_id=tenant_id, receipt_id=receipt_id, deleted_at__isnull=True
    ).all()
    poi_ids = {
        int(i.purchase_order_item_id or 0)
        for i in items
        if int(i.purchase_order_item_id or 0) > 0
    }
    poi_by_id: Dict[int, PurchaseOrderItem] = {}
    if poi_ids:
        for poi in await PurchaseOrderItem.filter(tenant_id=tenant_id, id__in=list(poi_ids)):
            poi_by_id[int(poi.id)] = poi
    caps: Dict[int, Decimal] = {}
    for item in items:
        _, _, line_gross = compute_purchase_receipt_line_settlement_amounts(
            receipt,
            item,
            poi_by_id,
        )
        caps[int(item.id)] = line_gross
    return caps


async def record_purchase_receipt_payable_occupancy(
    tenant_id: int,
    receipt_id: int,
    payable_id: int,
    amount: Decimal,
    *,
    line_selections: Optional[List[Any]] = None,
    created_by: Optional[int] = None,
    settlement_gross: bool = False,
) -> None:
    from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
        build_slices_from_pull_receipt_line_selections,
    )

    svc = PurchaseReceiptLineFinanceOccupancyService()
    if line_selections:
        slices = await build_slices_from_pull_receipt_line_selections(
            tenant_id,
            receipt_id,
            "payable",
            line_selections,
            header_amount=amount,
        )
        await svc.record_receipt_finance_occupancy_explicit(
            tenant_id,
            receipt_id,
            occupancy_kind=_KIND_PAYABLE,
            target_doc_type="Payable",
            target_doc_id=payable_id,
            slices=slices,
            created_by=created_by,
        )
        return
    line_caps = await _line_gross_caps_for_receipt(tenant_id, receipt_id) if settlement_gross else None
    await svc.record_receipt_finance_occupancy(
        tenant_id,
        receipt_id,
        occupancy_kind=_KIND_PAYABLE,
        amount=amount,
        target_doc_type="Payable",
        target_doc_id=payable_id,
        created_by=created_by,
        line_amount_caps=line_caps,
    )


async def record_purchase_receipt_invoice_from_payable(
    tenant_id: int,
    payable_id: int,
    invoice_id: int,
    amount: Decimal,
    *,
    line_selections: Optional[List[Any]] = None,
    created_by: Optional[int] = None,
    allow_append: bool = False,
) -> None:
    from apps.kuaicaiwu.models.payable import Payable
    from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
        build_slices_from_pull_receipt_line_selections,
        resolve_purchase_receipt_id_from_payable,
    )

    payable = await Payable.get_or_none(
        tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
    )
    if not payable:
        return
    receipt_id = resolve_purchase_receipt_id_from_payable(
        str(getattr(payable, "source_type", "") or ""),
        getattr(payable, "source_id", None),
    )
    if not receipt_id:
        return

    svc = PurchaseReceiptLineFinanceOccupancyService()
    if line_selections:
        slices = await build_slices_from_pull_receipt_line_selections(
            tenant_id,
            receipt_id,
            "invoice",
            line_selections,
            header_amount=amount,
        )
        await svc.record_receipt_finance_occupancy_explicit(
            tenant_id,
            receipt_id,
            occupancy_kind=_KIND_INVOICE,
            target_doc_type="PurchaseInvoice",
            target_doc_id=invoice_id,
            slices=slices,
            created_by=created_by,
            allow_append=allow_append,
        )
        return
    await svc.record_invoice_from_payable_to_receipt_lines(
        tenant_id,
        payable_id,
        invoice_id,
        amount,
        created_by=created_by,
        allow_append=allow_append,
    )


async def record_purchase_receipt_invoice_occupancy(
    tenant_id: int,
    receipt_id: int,
    invoice_id: int,
    amount: Decimal,
    *,
    line_selections: Optional[List[Any]] = None,
    created_by: Optional[int] = None,
) -> None:
    from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
        build_slices_from_pull_receipt_line_selections,
    )

    svc = PurchaseReceiptLineFinanceOccupancyService()
    if line_selections:
        slices = await build_slices_from_pull_receipt_line_selections(
            tenant_id,
            receipt_id,
            "invoice",
            line_selections,
            header_amount=amount,
        )
        await svc.record_receipt_finance_occupancy_explicit(
            tenant_id,
            receipt_id,
            occupancy_kind=_KIND_INVOICE,
            target_doc_type="PurchaseInvoice",
            target_doc_id=invoice_id,
            slices=slices,
            created_by=created_by,
        )
        return
    await svc.record_receipt_finance_occupancy(
        tenant_id,
        receipt_id,
        occupancy_kind=_KIND_INVOICE,
        amount=amount,
        target_doc_type="PurchaseInvoice",
        target_doc_id=invoice_id,
        created_by=created_by,
    )
