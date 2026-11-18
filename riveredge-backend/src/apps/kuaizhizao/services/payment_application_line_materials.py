"""付款申请行：从来源单据明细带出品名/规格/数量快照。"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from apps.kuaicaiwu.models.payable import Payable
from apps.kuaizhizao.models.purchase_order import PurchaseOrder
from apps.kuaizhizao.models.sales_order import SalesOrder
from apps.kuaizhizao.schemas.payment_application import PaymentApplicationLineCreate
from apps.kuaizhizao.utils.document_amount_write import allocate_amount_by_weights


def allocate_by_weights(total: Decimal, weights: List[Decimal]) -> List[Decimal]:
    """按权重分摊金额；末行吃尾差，保证合计等于 total。"""
    return allocate_amount_by_weights(total, weights)


async def lines_from_purchase_receipt_items(
    *,
    tenant_id: int,
    receipt_id: int,
    receipt_code: str,
    payable: Payable,
    request_amount: Decimal,
    line_kind: str = "goods",
    source_type: str = "purchase_receipt",
) -> List[PaymentApplicationLineCreate]:
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

    items = (
        await PurchaseReceiptItem.filter(
            tenant_id=tenant_id,
            receipt_id=receipt_id,
            deleted_at__isnull=True,
        )
        .order_by("id")
        .all()
    )
    if not items:
        return [
            PaymentApplicationLineCreate(
                source_type=source_type,
                source_id=receipt_id,
                source_code=receipt_code,
                payable_id=int(payable.id),
                payable_code=payable.payable_code,
                line_kind=line_kind,
                request_amount=request_amount,
            )
        ]
    amount_weights = [Decimal(str(it.total_amount or 0)) for it in items]
    if sum(amount_weights) <= 0:
        amount_weights = [Decimal(str(it.receipt_quantity or 0)) for it in items]
    amounts = allocate_by_weights(request_amount, amount_weights)
    lines: List[PaymentApplicationLineCreate] = []
    for it, amt in zip(items, amounts):
        if amt <= 0:
            continue
        lines.append(
            PaymentApplicationLineCreate(
                source_type=source_type,
                source_id=receipt_id,
                source_code=receipt_code,
                payable_id=int(payable.id),
                payable_code=payable.payable_code,
                line_kind=line_kind,
                request_amount=amt,
                material_name=it.material_name,
                material_spec=it.material_spec,
                quantity=it.receipt_quantity,
                material_unit=it.material_unit,
                source_line_id=int(it.id),
            )
        )
    if not lines:
        return [
            PaymentApplicationLineCreate(
                source_type=source_type,
                source_id=receipt_id,
                source_code=receipt_code,
                payable_id=int(payable.id),
                payable_code=payable.payable_code,
                line_kind=line_kind,
                request_amount=request_amount,
            )
        ]
    return lines


async def lines_from_purchase_order_items(
    *,
    tenant_id: int,
    order: PurchaseOrder,
    request_amount: Decimal,
    line_kind: str = "prepayment",
) -> List[PaymentApplicationLineCreate]:
    if line_kind == "prepayment":
        return [
            PaymentApplicationLineCreate(
                source_type="purchase_order",
                source_id=int(order.id),
                source_code=order.order_code,
                line_kind=line_kind,
                request_amount=request_amount,
            )
        ]

    from apps.kuaizhizao.models.purchase_order import PurchaseOrderItem

    items = (
        await PurchaseOrderItem.filter(tenant_id=tenant_id, order_id=int(order.id))
        .order_by("id")
        .all()
    )
    if not items:
        return [
            PaymentApplicationLineCreate(
                source_type="purchase_order",
                source_id=int(order.id),
                source_code=order.order_code,
                line_kind=line_kind,
                request_amount=request_amount,
            )
        ]
    amount_weights = [Decimal(str(it.total_price or 0)) for it in items]
    if sum(amount_weights) <= 0:
        amount_weights = [Decimal(str(it.ordered_quantity or 0)) for it in items]
    amounts = allocate_by_weights(request_amount, amount_weights)
    lines: List[PaymentApplicationLineCreate] = []
    for it, amt in zip(items, amounts):
        if amt <= 0:
            continue
        lines.append(
            PaymentApplicationLineCreate(
                source_type="purchase_order",
                source_id=int(order.id),
                source_code=order.order_code,
                line_kind=line_kind,
                request_amount=amt,
                material_name=it.material_name,
                material_spec=it.material_spec,
                quantity=it.ordered_quantity,
                material_unit=it.unit,
                source_line_id=int(it.id),
            )
        )
    if not lines:
        return [
            PaymentApplicationLineCreate(
                source_type="purchase_order",
                source_id=int(order.id),
                source_code=order.order_code,
                line_kind=line_kind,
                request_amount=request_amount,
            )
        ]
    return lines


async def lines_from_sales_order_items(
    *,
    tenant_id: int,
    order: SalesOrder,
    request_amount: Decimal,
    line_kind: str = "prepayment",
) -> List[PaymentApplicationLineCreate]:
    """按销售订单行权分摊预收金额（与采购订单预付款行规则对齐）。"""
    if line_kind == "prepayment":
        from apps.kuaizhizao.models.sales_order import SalesOrderItem

        items = (
            await SalesOrderItem.filter(tenant_id=tenant_id, sales_order_id=int(order.id))
            .order_by("id")
            .all()
        )
        if not items:
            return [
                PaymentApplicationLineCreate(
                    source_type="sales_order",
                    source_id=int(order.id),
                    source_code=order.order_code,
                    line_kind=line_kind,
                    request_amount=request_amount,
                )
            ]
        amount_weights = [Decimal(str(it.total_amount or 0)) for it in items]
        if sum(amount_weights) <= 0:
            amount_weights = [Decimal(str(it.order_quantity or 0)) for it in items]
        amounts = allocate_by_weights(request_amount, amount_weights)
        lines: List[PaymentApplicationLineCreate] = []
        for it, amt in zip(items, amounts):
            if amt <= 0:
                continue
            lines.append(
                PaymentApplicationLineCreate(
                    source_type="sales_order",
                    source_id=int(order.id),
                    source_code=order.order_code,
                    line_kind=line_kind,
                    request_amount=amt,
                    material_name=it.material_name,
                    material_spec=it.material_spec,
                    quantity=it.order_quantity,
                    material_unit=it.material_unit,
                    source_line_id=int(it.id),
                )
            )
        if not lines:
            return [
                PaymentApplicationLineCreate(
                    source_type="sales_order",
                    source_id=int(order.id),
                    source_code=order.order_code,
                    line_kind=line_kind,
                    request_amount=request_amount,
                )
            ]
        return lines

    return [
        PaymentApplicationLineCreate(
            source_type="sales_order",
            source_id=int(order.id),
            source_code=order.order_code,
            line_kind=line_kind,
            request_amount=request_amount,
        )
    ]


async def lines_for_payable(
    *,
    tenant_id: int,
    payable: Payable,
    request_amount: Decimal,
    source_type: str,
    source_id: Optional[int] = None,
    source_code: Optional[str] = None,
    line_kind: str = "goods",
) -> List[PaymentApplicationLineCreate]:
    """应付来源若是采购入库，展开入库明细；否则单行。"""
    src_type = str(payable.source_type or "").strip().lower().replace("-", "_")
    src_id = int(payable.source_id or 0)
    if src_type in ("purchase_receipt", "purchasereceipt") and src_id > 0:
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=src_id, deleted_at__isnull=True
        )
        code = (
            (receipt.receipt_code if receipt else None)
            or source_code
            or payable.source_code
            or str(src_id)
        )
        # 展开入库明细时来源类型固定为采购入库，便于表单展示
        display_source = (
            source_type
            if source_type in ("purchase_receipt", "document_reconciliation")
            else "purchase_receipt"
        )
        return await lines_from_purchase_receipt_items(
            tenant_id=tenant_id,
            receipt_id=src_id,
            receipt_code=str(code),
            payable=payable,
            request_amount=request_amount,
            line_kind=line_kind,
            source_type=display_source,
        )
    return [
        PaymentApplicationLineCreate(
            source_type=source_type,
            source_id=source_id if source_id is not None else int(payable.id),
            source_code=source_code or payable.payable_code,
            payable_id=int(payable.id),
            payable_code=payable.payable_code,
            line_kind=line_kind,
            request_amount=request_amount,
        )
    ]
