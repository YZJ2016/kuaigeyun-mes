"""采购入库价税汇总：未税行合计 → 头 tax_amount / net_amount（财务结算含税真源）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Sequence

from apps.kuaicaiwu.services.finance_tax import compute_tax_from_excluding, quantize_money


def normalize_po_tax_rate_to_percent(tax_rate: Any) -> Decimal:
    """
    采购订单 tax_rate 为小数（0.13）；入库单 tax_rate 存百分比（13）。
    已大于 1 的视为已是百分比。
    """
    rate = Decimal(str(tax_rate or 0))
    if rate <= 0:
        return Decimal("0")
    if rate <= 1:
        return (rate * Decimal("100")).quantize(Decimal("0.01"))
    return rate.quantize(Decimal("0.01"))


def rollup_purchase_receipt_header_tax(
    excl_total: Decimal | float | str,
    tax_rate_percent: Decimal | float | str,
) -> tuple[Decimal, Decimal, Decimal]:
    """由未税合计与税率（百分比）计算 tax_amount、net_amount。"""
    excl, tax, gross = compute_tax_from_excluding(
        quantize_money(Decimal(str(excl_total))),
        Decimal(str(tax_rate_percent)),
    )
    return excl, tax, gross


def purchase_order_settlement_gross(order: Any) -> Decimal:
    """采购订单财务上限（预付/应付/开票）：价税合计；与前端 resolvePurchaseOrderDisplayAmount 同源。"""
    stored_net = Decimal(str(getattr(order, "net_amount", 0) or 0))
    if stored_net > 0:
        return quantize_money(stored_net)
    excl = quantize_money(Decimal(str(getattr(order, "total_amount", 0) or 0)))
    tax_amt_raw = getattr(order, "tax_amount", None)
    if tax_amt_raw is not None:
        tax_amt = Decimal(str(tax_amt_raw or 0))
        if excl > 0 or tax_amt > 0:
            return quantize_money(excl + tax_amt)
    if excl <= 0:
        return Decimal("0.00")
    _, _, gross = rollup_purchase_receipt_header_tax(
        excl,
        normalize_po_tax_rate_to_percent(getattr(order, "tax_rate", None)),
    )
    return gross


def resolve_purchase_receipt_line_excl_amount(
    *,
    receipt_quantity: Decimal,
    unit_price: Decimal,
    purchase_order_item_id: Optional[int] = None,
    line_total_amount: Optional[Decimal] = None,
    poi_by_id: Optional[Mapping[int, Any]] = None,
) -> Decimal:
    """
    入库行未税：关联采购订单行时按 PO 行 total_price 比例分摊（与订单行价税真源一致）；
    否则用显式行未税或 qty×单价（分位量化）。
    """
    qty = Decimal(str(receipt_quantity or 0))
    poi_id = int(purchase_order_item_id or 0)
    if poi_id > 0 and poi_by_id and poi_id in poi_by_id:
        poi = poi_by_id[poi_id]
        ordered = Decimal(str(getattr(poi, "ordered_quantity", 0) or 0))
        line_price = Decimal(str(getattr(poi, "total_price", 0) or 0))
        if ordered > 0 and line_price > 0 and qty > 0:
            return quantize_money(line_price * qty / ordered)
    if line_total_amount is not None:
        return quantize_money(line_total_amount)
    return quantize_money(qty * unit_price)


def compute_purchase_receipt_settlement_gross_from_lines(
    receipt: Any,
    lines: Sequence[Any],
    poi_by_id: Mapping[int, Any],
) -> Decimal:
    """按明细行（含 PO 比例分摊未税）rollup 价税合计；与列表 settlement_gross、写路径一致。"""
    excl_sum = Decimal("0")
    for line in lines:
        qty = Decimal(str(getattr(line, "receipt_quantity", 0) or 0))
        unit_price = Decimal(str(getattr(line, "unit_price", 0) or 0))
        poi_id = int(getattr(line, "purchase_order_item_id", 0) or 0) or None
        line_total_raw = getattr(line, "total_amount", None)
        line_total = (
            Decimal(str(line_total_raw)) if line_total_raw is not None else None
        )
        excl_sum += resolve_purchase_receipt_line_excl_amount(
            receipt_quantity=qty,
            unit_price=unit_price,
            purchase_order_item_id=poi_id,
            line_total_amount=line_total,
            poi_by_id=poi_by_id,
        )
    tax_pct = normalize_po_tax_rate_to_percent(getattr(receipt, "tax_rate", None))
    _, _, gross = rollup_purchase_receipt_header_tax(excl_sum, tax_pct)
    return gross


async def purchase_receipt_settlement_gross_async(
    tenant_id: int,
    receipt: Any,
) -> Decimal:
    """应付/开票上限：按入库明细与 PO 行比例重算价税合计。"""
    rid = int(getattr(receipt, "id", 0) or 0)
    if rid <= 0:
        return purchase_receipt_settlement_gross(receipt)
    gross_map = await batch_purchase_receipt_settlement_gross(tenant_id, [receipt])
    if rid in gross_map:
        return gross_map[rid]
    return purchase_receipt_settlement_gross(receipt)


async def batch_purchase_receipt_settlement_gross(
    tenant_id: int,
    receipts: Sequence[Any],
) -> Dict[int, Decimal]:
    """批量按明细 + PO 行重算价税合计（列表/详情展示与应付上限）。"""
    if not receipts:
        return {}
    receipt_ids = [int(getattr(r, "id", 0) or 0) for r in receipts]
    receipt_ids = [rid for rid in receipt_ids if rid > 0]
    if not receipt_ids:
        return {}

    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

    items = await PurchaseReceiptItem.filter(
        tenant_id=tenant_id,
        receipt_id__in=receipt_ids,
        deleted_at__isnull=True,
    ).all()
    items_by_receipt: Dict[int, list] = {}
    poi_ids: set[int] = set()
    for item in items:
        rid = int(item.receipt_id)
        items_by_receipt.setdefault(rid, []).append(item)
        poi_id = int(item.purchase_order_item_id or 0)
        if poi_id > 0:
            poi_ids.add(poi_id)

    poi_by_id: Dict[int, Any] = {}
    if poi_ids:
        from apps.kuaizhizao.models.purchase_order import PurchaseOrderItem

        po_items = await PurchaseOrderItem.filter(
            tenant_id=tenant_id, id__in=list(poi_ids)
        ).all()
        poi_by_id = {int(p.id): p for p in po_items}

    receipt_by_id = {int(getattr(r, "id", 0) or 0): r for r in receipts}
    out: Dict[int, Decimal] = {}
    for rid, lines in items_by_receipt.items():
        receipt = receipt_by_id.get(rid)
        if receipt is None:
            continue
        out[rid] = compute_purchase_receipt_settlement_gross_from_lines(
            receipt, lines, poi_by_id
        )
    return out


def purchase_receipt_settlement_gross(
    receipt: Any,
    *,
    lines: Optional[Sequence[Any]] = None,
    poi_by_id: Optional[Mapping[int, Any]] = None,
) -> Decimal:
    """应付/开票上限：价税合计；传入 lines 时按 PO 比例重算，否则读头表 net / 未税 rollup。"""
    if lines is not None:
        return compute_purchase_receipt_settlement_gross_from_lines(
            receipt, lines, poi_by_id or {}
        )
    net = getattr(receipt, "net_amount", None)
    if net is not None and Decimal(str(net)) > 0:
        return quantize_money(Decimal(str(net)))
    excl = quantize_money(Decimal(str(getattr(receipt, "total_amount", 0) or 0)))
    tax_amt_raw = getattr(receipt, "tax_amount", None)
    if tax_amt_raw is not None:
        tax_amt = Decimal(str(tax_amt_raw or 0))
        if excl > 0 or tax_amt > 0:
            return quantize_money(excl + tax_amt)
    rate_raw = getattr(receipt, "tax_rate", None)
    pct = normalize_po_tax_rate_to_percent(rate_raw)
    if excl <= 0:
        return Decimal("0.00")
    _, _, gross = rollup_purchase_receipt_header_tax(excl, pct)
    return gross


def is_purchase_receipt_payable_source(source_type: Any) -> bool:
    from apps.kuaicaiwu.constants.finance_source_types import (
        PAYABLE_SOURCE_PURCHASE_RECEIPT,
    )

    st = str(source_type or "").strip()
    return st in (PAYABLE_SOURCE_PURCHASE_RECEIPT, "purchase_receipt", "PurchaseReceipt")


async def align_payables_from_purchase_receipt_settlement(
    tenant_id: int,
    payables: Sequence[Any],
) -> None:
    """
    来源为采购入库、且尚未付款的应付：按 settlement 重算价税合计并回写头表（修正 10000.05 类尾差）。
    已有付款/退款或剩余与总额不一致（如预付占用）时不改。
    """
    if not payables:
        return
    from apps.kuaicaiwu.models.payable import Payable
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

    receipt_ids: list[int] = []
    payables_by_receipt: Dict[int, list[Any]] = {}
    for payable in payables:
        if not is_purchase_receipt_payable_source(getattr(payable, "source_type", None)):
            continue
        rid = int(getattr(payable, "source_id", 0) or 0)
        if rid <= 0:
            continue
        paid = quantize_money(Decimal(str(getattr(payable, "paid_amount", 0) or 0)))
        refunded = quantize_money(Decimal(str(getattr(payable, "refunded_amount", 0) or 0)))
        if paid > 0 or refunded > 0:
            continue
        total = quantize_money(Decimal(str(getattr(payable, "total_amount", 0) or 0)))
        remaining = quantize_money(Decimal(str(getattr(payable, "remaining_amount", 0) or 0)))
        if total != remaining:
            continue
        receipt_ids.append(rid)
        payables_by_receipt.setdefault(rid, []).append(payable)

    if not receipt_ids:
        return

    unique_receipt_ids = sorted(set(receipt_ids))
    receipts = await PurchaseReceipt.filter(
        tenant_id=tenant_id, id__in=unique_receipt_ids, deleted_at__isnull=True
    ).all()
    gross_map = await batch_purchase_receipt_settlement_gross(tenant_id, receipts)

    for receipt in receipts:
        rid = int(receipt.id)
        canonical = gross_map.get(rid)
        if canonical is None:
            continue
        canonical = quantize_money(canonical)
        for payable in payables_by_receipt.get(rid, []):
            current = quantize_money(Decimal(str(getattr(payable, "total_amount", 0) or 0)))
            if current == canonical:
                continue
            pid = int(getattr(payable, "id", 0) or 0)
            if pid <= 0:
                continue
            await Payable.filter(tenant_id=tenant_id, id=pid).update(
                total_amount=canonical,
                remaining_amount=canonical,
            )
            payable.total_amount = canonical
            payable.remaining_amount = canonical


def proportional_line_gross(
    line_excl: Decimal,
    header_excl: Decimal,
    header_gross: Decimal,
) -> Decimal:
    """行级含税分摊（头未税为 0 时返回 0）。"""
    line = quantize_money(line_excl)
    head_excl = quantize_money(header_excl)
    head_gross = quantize_money(header_gross)
    if line <= 0 or head_excl <= 0 or head_gross <= 0:
        return Decimal("0.00")
    return quantize_money((line / head_excl) * head_gross)
