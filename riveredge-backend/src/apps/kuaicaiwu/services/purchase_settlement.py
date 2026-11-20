"""采购价税汇总：订单/入库明细 → 头未税、税额、价税（财务结算唯一真源）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from apps.kuaicaiwu.services.finance_tax import quantize_money

# 头表金额只能由明细 rollup 写入，禁止接受前端/外推 payload
PURCHASE_RECEIPT_COMPUTED_HEADER_FIELDS = frozenset(
    {"total_amount", "tax_amount", "net_amount", "total_quantity"}
)

PURCHASE_ORDER_COMPUTED_HEADER_FIELDS = frozenset(
    {"total_amount", "tax_amount", "net_amount", "total_quantity"}
)

_QTY_SCALE = Decimal("0.0001")


def quantize_receipt_quantity(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(_QTY_SCALE)


def normalize_po_tax_rate_to_percent(tax_rate: Any) -> Decimal:
    """
    采购订单头 tax_rate 为小数（0.13）；订单行 / 入库单 / 价本 tax_rate 存百分比（13）。

    约定（禁止把百分数 1 当成小数 1.0）：
    - (0, 1) → 小数比率，×100 得百分比（0.13→13，0.01→1）
    - >= 1 → 已是百分比（1→1%，13→13%）；不可再用 <=1 把 1% 抬成 100%
    """
    rate = Decimal(str(tax_rate or 0))
    if rate <= 0:
        return Decimal("0")
    if rate < 1:
        return (rate * Decimal("100")).quantize(Decimal("0.01"))
    return rate.quantize(Decimal("0.01"))


def resolve_purchase_line_tax_rate_percent(
    *,
    line_tax_rate: Any = None,
    header_tax_rate: Any = None,
) -> Decimal:
    """行税率优先（百分比或小数均可）；否则头税率。"""
    line_raw = Decimal(str(line_tax_rate or 0)) if line_tax_rate is not None else Decimal("0")
    if line_raw > 0:
        return normalize_po_tax_rate_to_percent(line_raw)
    return normalize_po_tax_rate_to_percent(header_tax_rate)


def coerce_purchase_order_display_unit_price(raw: Any, price_places: int) -> Decimal | None:
    """表单录入单价原样量化。未传则 None，禁止由未税单价推导。"""
    if raw is None or raw == "":
        return None
    from core.utils.price_precision import quantize_business_price

    return quantize_business_price(Decimal(str(raw)), price_places)


def compute_purchase_order_header_rollup(
    order: Any,
    items: Sequence[Any],
    *,
    amount_places: int = 2,
) -> Tuple[Decimal, Decimal, Decimal, Decimal, Decimal] | None:
    """按录入单价与价类正向拆分汇总。含税且缺 display_unit_price 时返回 None，禁止从未税单价回推。"""
    from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts
    from core.utils.amount_precision import quantize_business_amount

    total_qty = Decimal("0")
    header_fallback = getattr(order, "tax_rate", None)
    total_excl = Decimal("0")
    total_tax = Decimal("0")
    total_incl = Decimal("0")
    first_pct = Decimal("0")
    header_price_type = str(getattr(order, "price_type", None) or "tax_exclusive")
    for it in items:
        qty = Decimal(str(getattr(it, "ordered_quantity", 0) or 0))
        total_qty += qty
        stored_unit = Decimal(str(getattr(it, "unit_price", 0) or 0))
        display_raw = getattr(it, "display_unit_price", None)
        pct = resolve_purchase_line_tax_rate_percent(
            line_tax_rate=getattr(it, "tax_rate", None),
            header_tax_rate=header_fallback,
        )
        if header_price_type == "tax_inclusive":
            if display_raw is None:
                if qty > 0 and stored_unit > 0:
                    return None
                excl = tax = incl = Decimal("0")
            else:
                excl, tax, incl = calc_document_line_amounts(
                    qty, Decimal(str(display_raw)), pct, "tax_inclusive", amount_places
                )
        elif qty > 0 and stored_unit > 0:
            excl, tax, incl = calc_document_line_amounts(
                qty, stored_unit, pct, "tax_exclusive", amount_places
            )
        else:
            excl = tax = incl = Decimal("0")
        total_excl += excl
        total_tax += tax
        total_incl += incl
        if first_pct <= 0 and pct > 0:
            first_pct = pct
    total_qty = quantize_receipt_quantity(total_qty)

    if total_qty > 0 or total_incl > 0:
        excl = quantize_business_amount(total_excl, amount_places)
        tax = quantize_business_amount(total_tax, amount_places)
        net = quantize_business_amount(total_incl, amount_places)
        header_rate = (
            (first_pct / Decimal("100")).quantize(Decimal("0.01"))
            if first_pct > 0
            else Decimal("0")
        )
    else:
        excl = tax = net = Decimal("0")
        header_rate = Decimal("0")
    return total_qty, excl, tax, net, header_rate


def purchase_order_item_settlement_gross(
    order: Any,
    item: Any,
    *,
    amount_places: int = 2,
) -> Decimal:
    """单行价税合计，与 compute_purchase_order_header_rollup / 订单列表 net_amount 同源。"""
    rolled = compute_purchase_order_header_rollup(order, [item], amount_places=amount_places)
    if rolled is None:
        # 含税且没有录入单价时禁止用未税×税率正算价税（2×55 会得到 110.01）。
        return Decimal("0.00")
    _, _, _, net, _ = rolled
    return quantize_money(net)


def purchase_order_line_print_exclusive_amount(
    order: Any,
    item: Any,
    *,
    amount_places: int = 2,
) -> Decimal | None:
    """打印用行不含税金额，与订单列表「不含税金额」同源。"""
    from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts
    from core.utils.amount_precision import quantize_business_amount

    qty = Decimal(str(getattr(item, "ordered_quantity", 0) or 0))
    stored_unit = Decimal(str(getattr(item, "unit_price", 0) or 0))
    display_raw = getattr(item, "display_unit_price", None)
    pct = resolve_purchase_line_tax_rate_percent(
        line_tax_rate=getattr(item, "tax_rate", None),
        header_tax_rate=getattr(order, "tax_rate", None),
    )
    header_price_type = str(getattr(order, "price_type", None) or "tax_exclusive")
    if header_price_type == "tax_inclusive":
        if display_raw is None:
            if qty > 0 and stored_unit > 0:
                return None
            return Decimal("0")
        excl, _, _ = calc_document_line_amounts(
            qty, Decimal(str(display_raw)), pct, "tax_inclusive", amount_places
        )
    elif qty > 0 and stored_unit > 0:
        excl, _, _ = calc_document_line_amounts(
            qty, stored_unit, pct, "tax_exclusive", amount_places
        )
    else:
        excl = Decimal("0")
    return quantize_business_amount(excl, amount_places)


def purchase_order_line_print_inclusive_amount(
    order: Any,
    item: Any,
    *,
    amount_places: int = 2,
) -> Decimal | None:
    """打印用行含税金额。含税且没有录入单价时返回 None，禁止从未税单价回推。"""
    from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts
    from core.utils.amount_precision import quantize_business_amount

    qty = Decimal(str(getattr(item, "ordered_quantity", 0) or 0))
    stored_unit = Decimal(str(getattr(item, "unit_price", 0) or 0))
    display_raw = getattr(item, "display_unit_price", None)
    pct = resolve_purchase_line_tax_rate_percent(
        line_tax_rate=getattr(item, "tax_rate", None),
        header_tax_rate=getattr(order, "tax_rate", None),
    )
    header_price_type = str(getattr(order, "price_type", None) or "tax_exclusive")
    if header_price_type == "tax_inclusive":
        if display_raw is None:
            if qty > 0 and stored_unit > 0:
                return None
            return Decimal("0")
        _, _, incl = calc_document_line_amounts(
            qty, Decimal(str(display_raw)), pct, "tax_inclusive", amount_places
        )
    elif qty > 0 and stored_unit > 0:
        _, _, incl = calc_document_line_amounts(
            qty, stored_unit, pct, "tax_exclusive", amount_places
        )
    else:
        incl = Decimal("0")
    return quantize_business_amount(incl, amount_places)


def purchase_order_line_print_inclusive_unit_price(
    order: Any,
    item: Any,
    *,
    price_places: int = 4,
    amount_places: int = 2,
) -> Decimal | None:
    """打印用行含税单价。含税价类只认 display_unit_price；未税价类用行含税金额÷数量。"""
    from core.utils.price_precision import quantize_business_price

    qty = Decimal(str(getattr(item, "ordered_quantity", 0) or 0))
    stored_unit = Decimal(str(getattr(item, "unit_price", 0) or 0))
    display_raw = getattr(item, "display_unit_price", None)
    header_price_type = str(getattr(order, "price_type", None) or "tax_exclusive")
    if header_price_type == "tax_inclusive":
        if display_raw is None:
            if qty > 0 and stored_unit > 0:
                return None
            return Decimal("0")
        return quantize_business_price(Decimal(str(display_raw)), price_places)
    incl = purchase_order_line_print_inclusive_amount(
        order, item, amount_places=amount_places
    )
    if incl is None:
        return None
    if qty <= 0:
        return Decimal("0")
    return quantize_business_price(incl / qty, price_places)


def purchase_order_header_out_of_sync(
    order: Any,
    *,
    total_qty: Decimal,
    excl: Decimal,
    tax_amt: Decimal,
    net_amt: Decimal,
    header_tax_rate: Decimal,
) -> bool:
    stored_rate = Decimal(str(getattr(order, "tax_rate", 0) or 0))
    rate_mismatch = stored_rate.quantize(Decimal("0.01")) != header_tax_rate.quantize(
        Decimal("0.01")
    )
    return (
        quantize_money(getattr(order, "total_amount", 0)) != quantize_money(excl)
        or quantize_money(getattr(order, "tax_amount", 0)) != quantize_money(tax_amt)
        or quantize_money(getattr(order, "net_amount", 0)) != quantize_money(net_amt)
        or quantize_receipt_quantity(getattr(order, "total_quantity", 0))
        != quantize_receipt_quantity(total_qty)
        or (header_tax_rate > 0 and rate_mismatch)
    )


async def sync_purchase_order_header_amounts(
    tenant_id: int,
    order_id: int,
    *,
    order: Any | None = None,
    items: Sequence[Any] | None = None,
    persist: bool = True,
) -> Tuple[Decimal, Decimal, Decimal, bool]:
    """以采购订单明细为唯一真源写回头表价税与合计数量。"""
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem

    if order is None:
        order = await PurchaseOrder.get_or_none(
            tenant_id=tenant_id, id=order_id, deleted_at__isnull=True
        )
        if order is None:
            return Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False

    if items is None:
        items = await PurchaseOrderItem.filter(
            tenant_id=tenant_id, order_id=order_id, deleted_at__isnull=True
        ).all()

    from infra.services.business_config_service import BusinessConfigService

    amount_places = await BusinessConfigService().get_amount_decimal_places(tenant_id)
    rolled = compute_purchase_order_header_rollup(
        order, items, amount_places=amount_places
    )
    if rolled is None:
        return (
            quantize_money(getattr(order, "total_amount", 0)),
            quantize_money(getattr(order, "tax_amount", 0)),
            quantize_money(getattr(order, "net_amount", 0)),
            False,
        )
    total_qty, excl, tax_amt, net_amt, header_rate = rolled
    changed = purchase_order_header_out_of_sync(
        order,
        total_qty=total_qty,
        excl=excl,
        tax_amt=tax_amt,
        net_amt=net_amt,
        header_tax_rate=header_rate,
    )
    if persist and changed:
        upd: Dict[str, Any] = {
            "total_quantity": total_qty,
            "total_amount": excl,
            "tax_amount": tax_amt,
            "net_amount": net_amt,
        }
        if header_rate > 0:
            upd["tax_rate"] = header_rate
        await PurchaseOrder.filter(tenant_id=tenant_id, id=order_id).update(**upd)
        order.total_quantity = total_qty
        order.total_amount = excl
        order.tax_amount = tax_amt
        order.net_amount = net_amt
        if header_rate > 0:
            order.tax_rate = header_rate

    return excl, tax_amt, net_amt, changed


def purchase_order_settlement_gross(order: Any) -> Decimal:
    """采购订单财务上限（预付/应付/开票）：价税合计；与前端 resolveDocumentStoredNetGrossAmount 同源。"""
    stored_net = Decimal(str(getattr(order, "net_amount", 0) or 0))
    if stored_net > 0:
        return quantize_money(stored_net)
    excl = quantize_money(Decimal(str(getattr(order, "total_amount", 0) or 0)))
    tax_amt_raw = getattr(order, "tax_amount", None)
    if tax_amt_raw is not None:
        tax_amt = Decimal(str(tax_amt_raw or 0))
        if excl > 0 or tax_amt > 0:
            return quantize_money(excl + tax_amt)
    return Decimal("0.00")


def resolve_receipt_line_tax_rate_percent(
    *,
    receipt: Any,
    purchase_order_item_id: Optional[int],
    poi_by_id: Mapping[int, Any],
    receipt_line: Any = None,
) -> Decimal:
    """入库行税率：本行 → 关联采购订单行 → 入库单头。"""
    if receipt_line is not None:
        own_pct = normalize_po_tax_rate_to_percent(getattr(receipt_line, "tax_rate", None))
        if own_pct > 0:
            return own_pct
    header_pct = normalize_po_tax_rate_to_percent(getattr(receipt, "tax_rate", None))
    poi_id = int(purchase_order_item_id or 0)
    if poi_id > 0 and poi_id in poi_by_id:
        return resolve_purchase_line_tax_rate_percent(
            line_tax_rate=getattr(poi_by_id[poi_id], "tax_rate", None),
            header_tax_rate=getattr(receipt, "tax_rate", None),
        )
    return header_pct


def _first_positive_line_tax_percent(lines: Sequence[Any]) -> Optional[Decimal]:
    for it in lines:
        pct = normalize_po_tax_rate_to_percent(getattr(it, "tax_rate", None))
        if pct > 0:
            return pct
    return None


def compute_purchase_receipt_header_rollup(
    receipt: Any,
    lines: Sequence[Any],
    poi_by_id: Mapping[int, Any],
    *,
    purchase_order_by_id: Optional[Mapping[int, Any]] = None,
    amount_places: int = 2,
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    按明细汇总头表：入库数量合计、未税、税额、价税合计。
    无明细时价税均为 0（税率仅保留在头表 tax_rate）。
    """
    total_qty = Decimal("0")
    for line in lines:
        total_qty += Decimal(str(getattr(line, "receipt_quantity", 0) or 0))
    total_qty = quantize_receipt_quantity(total_qty)

    if lines:
        excl, tax_amt, net_amt = rollup_purchase_receipt_amounts_from_lines(
            receipt,
            lines,
            poi_by_id,
            purchase_order_by_id=purchase_order_by_id,
            amount_places=amount_places,
        )
    else:
        excl, tax_amt, net_amt = (
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("0.00"),
        )
    return total_qty, excl, tax_amt, net_amt


def purchase_receipt_header_out_of_sync(
    receipt: Any,
    *,
    total_qty: Decimal,
    excl: Decimal,
    tax_amt: Decimal,
    net_amt: Decimal,
) -> bool:
    """头表金额/数量与 rollup 是否不一致（分位比较）。"""
    return (
        quantize_money(getattr(receipt, "total_amount", 0)) != quantize_money(excl)
        or quantize_money(getattr(receipt, "tax_amount", 0)) != quantize_money(tax_amt)
        or quantize_money(getattr(receipt, "net_amount", 0)) != quantize_money(net_amt)
        or quantize_receipt_quantity(getattr(receipt, "total_quantity", 0))
        != quantize_receipt_quantity(total_qty)
    )


def compute_purchase_receipt_line_settlement_amounts(
    receipt: Any,
    line: Any,
    poi_by_id: Mapping[int, Any],
    *,
    purchase_order_by_id: Optional[Mapping[int, Any]] = None,
    amount_places: int = 2,
) -> Tuple[Decimal, Decimal, Decimal]:
    """单行未税/税额/价税。唯一公式是 calc_document_line_amounts。

    有 display_unit_price：含税，价税合计 = round(数量 × 录入单价)，税额 = 价税合计 − 未税。
    无 display_unit_price：不含税，未税 = round(数量 × 单价)，税额 = round(未税 × 税率)。
    禁止按采购订单行比例改写，禁止用未税金额再乘税率得到价税合计。
    """
    del purchase_order_by_id
    qty = Decimal(str(getattr(line, "receipt_quantity", 0) or 0))
    unit_price = Decimal(str(getattr(line, "unit_price", 0) or 0))
    poi_id = int(getattr(line, "purchase_order_item_id", 0) or 0) or None
    tax_pct = resolve_receipt_line_tax_rate_percent(
        receipt=receipt,
        purchase_order_item_id=poi_id,
        poi_by_id=poi_by_id,
        receipt_line=line,
    )
    from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts

    display_raw = getattr(line, "display_unit_price", None)
    has_display = display_raw is not None and Decimal(str(display_raw or 0)) > 0
    if has_display:
        return calc_document_line_amounts(
            qty,
            Decimal(str(display_raw)),
            tax_pct,
            "tax_inclusive",
            amount_places,
        )
    return calc_document_line_amounts(
        qty,
        unit_price,
        tax_pct,
        "tax_exclusive",
        amount_places,
    )


async def sync_purchase_receipt_line_settlement_amounts(
    tenant_id: int,
    receipt: Any,
    lines: Sequence[Any],
    poi_by_id: Mapping[int, Any],
    *,
    persist: bool = True,
    purchase_order_by_id: Optional[Mapping[int, Any]] = None,
    amount_places: int = 2,
) -> bool:
    """将行未税/税额/价税写回 calc_document_line_amounts 的结果（详情只读真源）。"""
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

    any_changed = False
    for line in lines:
        line_excl, line_tax, line_gross = compute_purchase_receipt_line_settlement_amounts(
            receipt,
            line,
            poi_by_id,
            purchase_order_by_id=purchase_order_by_id,
            amount_places=amount_places,
        )
        stored_excl = quantize_money(getattr(line, "total_amount", 0) or 0)
        stored_tax = quantize_money(getattr(line, "tax_amount", 0) or 0)
        stored_net = quantize_money(getattr(line, "net_amount", 0) or 0)
        if stored_excl == line_excl and stored_tax == line_tax and stored_net == line_gross:
            continue
        any_changed = True
        if persist:
            line_id = int(getattr(line, "id"))
            await PurchaseReceiptItem.filter(tenant_id=tenant_id, id=line_id).update(
                total_amount=line_excl,
                tax_amount=line_tax,
                net_amount=line_gross,
            )
            line.total_amount = line_excl
            line.tax_amount = line_tax
            line.net_amount = line_gross
    return any_changed


async def sync_purchase_receipt_header_amounts(
    tenant_id: int,
    receipt_id: int,
    *,
    receipt: Any | None = None,
    lines: Sequence[Any] | None = None,
    poi_by_id: Mapping[int, Any] | None = None,
    persist: bool = True,
) -> Tuple[Decimal, Decimal, Decimal, bool]:
    """
    以明细为唯一真源写回头表未税/税额/价税/合计数量。
    返回 (未税, 税额, 价税合计, 是否发生过持久化修正)。
    """
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

    if receipt is None:
        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
        )
        if receipt is None:
            return Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False

    if lines is None:
        lines = await PurchaseReceiptItem.filter(
            tenant_id=tenant_id,
            receipt_id=receipt_id,
            deleted_at__isnull=True,
        ).all()

    if poi_by_id is None:
        poi_ids = {
            int(getattr(i, "purchase_order_item_id", 0) or 0)
            for i in lines
            if int(getattr(i, "purchase_order_item_id", 0) or 0) > 0
        }
        poi_by_id = {}
        if poi_ids:
            from apps.kuaizhizao.models.purchase_order import PurchaseOrderItem

            for poi in await PurchaseOrderItem.filter(
                tenant_id=tenant_id, id__in=list(poi_ids)
            ):
                poi_by_id[int(poi.id)] = poi

    purchase_order_by_id = await load_purchase_order_by_id_for_poi_by_id(
        tenant_id, poi_by_id
    )

    from infra.services.business_config_service import BusinessConfigService

    amount_places = await BusinessConfigService().get_amount_decimal_places(tenant_id)

    line_excl_changed = await sync_purchase_receipt_line_settlement_amounts(
        tenant_id,
        receipt,
        lines,
        poi_by_id,
        persist=persist,
        purchase_order_by_id=purchase_order_by_id,
        amount_places=amount_places,
    )

    total_qty, excl, tax_amt, net_amt = compute_purchase_receipt_header_rollup(
        receipt, lines, poi_by_id, purchase_order_by_id=purchase_order_by_id, amount_places=amount_places
    )
    changed = line_excl_changed or purchase_receipt_header_out_of_sync(
        receipt, total_qty=total_qty, excl=excl, tax_amt=tax_amt, net_amt=net_amt
    )
    line_tax_pct = _first_positive_line_tax_percent(lines)

    if persist and changed:
        upd: Dict[str, Any] = {
            "total_quantity": total_qty,
            "total_amount": excl,
            "tax_amount": tax_amt,
            "net_amount": net_amt,
        }
        if line_tax_pct is not None:
            upd["tax_rate"] = float(line_tax_pct)
        await PurchaseReceipt.filter(tenant_id=tenant_id, id=receipt_id).update(**upd)
        receipt.total_quantity = total_qty
        receipt.total_amount = excl
        receipt.tax_amount = tax_amt
        receipt.net_amount = net_amt
        if line_tax_pct is not None:
            receipt.tax_rate = line_tax_pct

    return excl, tax_amt, net_amt, changed


def rollup_purchase_receipt_amounts_from_lines(
    receipt: Any,
    lines: Sequence[Any],
    poi_by_id: Mapping[int, Any],
    *,
    purchase_order_by_id: Optional[Mapping[int, Any]] = None,
    amount_places: int = 2,
) -> tuple[Decimal, Decimal, Decimal]:
    """按明细行唯一公式汇总未税/税额/价税合计。"""
    excl_sum = Decimal("0")
    tax_sum = Decimal("0")
    gross_sum = Decimal("0")
    for line in lines:
        line_excl, tax, gross = compute_purchase_receipt_line_settlement_amounts(
            receipt,
            line,
            poi_by_id,
            purchase_order_by_id=purchase_order_by_id,
            amount_places=amount_places,
        )
        excl_sum += line_excl
        tax_sum += tax
        gross_sum += gross
    excl_sum = quantize_money(excl_sum)
    tax_sum = quantize_money(tax_sum)
    return excl_sum, tax_sum, quantize_money(gross_sum)


def compute_purchase_receipt_settlement_gross_from_lines(
    receipt: Any,
    lines: Sequence[Any],
    poi_by_id: Mapping[int, Any],
    *,
    purchase_order_by_id: Optional[Mapping[int, Any]] = None,
    amount_places: int = 2,
) -> Decimal:
    """按明细行唯一公式 rollup 价税合计；与列表 settlement_gross、写路径一致。"""
    _, _, gross = rollup_purchase_receipt_amounts_from_lines(
        receipt,
        lines,
        poi_by_id,
        purchase_order_by_id=purchase_order_by_id,
        amount_places=amount_places,
    )
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


async def _batch_purchase_receipt_settlement_rollup_context(
    tenant_id: int,
    receipts: Sequence[Any],
) -> tuple[
    Dict[int, Any],
    Dict[int, list],
    Dict[int, Any],
    Dict[int, Any],
    int,
]:
    """批量加载入库单明细与 PO 上下文，供未税/价税 rollup 共用。"""
    receipt_ids = [int(getattr(r, "id", 0) or 0) for r in receipts]
    receipt_ids = [rid for rid in receipt_ids if rid > 0]
    if not receipt_ids:
        return {}, {}, {}, {}, 2

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

    order_ids = {
        int(getattr(p, "order_id", 0) or 0)
        for p in poi_by_id.values()
        if int(getattr(p, "order_id", 0) or 0) > 0
    }
    purchase_order_by_id: Dict[int, Any] = {}
    if order_ids:
        from apps.kuaizhizao.models.purchase_order import PurchaseOrder

        for order in await PurchaseOrder.filter(
            tenant_id=tenant_id, id__in=list(order_ids), deleted_at__isnull=True
        ):
            purchase_order_by_id[int(order.id)] = order

    from infra.services.business_config_service import BusinessConfigService

    amount_places = await BusinessConfigService().get_amount_decimal_places(tenant_id)

    receipt_by_id = {int(getattr(r, "id", 0) or 0): r for r in receipts}
    return (
        receipt_by_id,
        items_by_receipt,
        poi_by_id,
        purchase_order_by_id,
        amount_places,
    )


async def batch_purchase_receipt_settlement_excl(
    tenant_id: int,
    receipts: Sequence[Any],
) -> Dict[int, Decimal]:
    """批量按明细唯一公式重算未税合计（展示与财务 rollup 同源）。"""
    if not receipts:
        return {}
    (
        receipt_by_id,
        items_by_receipt,
        poi_by_id,
        purchase_order_by_id,
        amount_places,
    ) = await _batch_purchase_receipt_settlement_rollup_context(tenant_id, receipts)
    if not receipt_by_id:
        return {}
    out: Dict[int, Decimal] = {}
    for rid, lines in items_by_receipt.items():
        receipt = receipt_by_id.get(rid)
        if receipt is None:
            continue
        excl, _, _ = rollup_purchase_receipt_amounts_from_lines(
            receipt,
            lines,
            poi_by_id,
            purchase_order_by_id=purchase_order_by_id,
            amount_places=amount_places,
        )
        out[rid] = excl
    return out


async def batch_purchase_receipt_settlement_gross(
    tenant_id: int,
    receipts: Sequence[Any],
) -> Dict[int, Decimal]:
    """批量按明细 + PO 行重算价税合计（列表/详情展示与应付上限）。"""
    if not receipts:
        return {}
    (
        receipt_by_id,
        items_by_receipt,
        poi_by_id,
        purchase_order_by_id,
        amount_places,
    ) = await _batch_purchase_receipt_settlement_rollup_context(tenant_id, receipts)
    if not receipt_by_id:
        return {}
    out: Dict[int, Decimal] = {}
    for rid, lines in items_by_receipt.items():
        receipt = receipt_by_id.get(rid)
        if receipt is None:
            continue
        out[rid] = compute_purchase_receipt_settlement_gross_from_lines(
            receipt,
            lines,
            poi_by_id,
            purchase_order_by_id=purchase_order_by_id,
            amount_places=amount_places,
        )
    return out


def purchase_receipt_settlement_gross(
    receipt: Any,
    *,
    lines: Optional[Sequence[Any]] = None,
    poi_by_id: Optional[Mapping[int, Any]] = None,
) -> Decimal:
    """应付/开票上限：价税合计；传 lines 时按明细唯一公式 rollup，否则只读头表已落库字段。"""
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
    return Decimal("0.00")


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
        await sync_purchase_receipt_header_amounts(
            tenant_id, rid, receipt=receipt, persist=True
        )
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


async def load_purchase_order_by_id_for_poi_by_id(
    tenant_id: int,
    poi_by_id: Mapping[int, Any],
) -> Dict[int, Any]:
    """由采购订单行 order_id 批量加载订单头（入库价税 PO 比例分摊唯一真源）。"""
    order_ids = {
        int(getattr(p, "order_id", 0) or 0)
        for p in poi_by_id.values()
        if int(getattr(p, "order_id", 0) or 0) > 0
    }
    if not order_ids:
        return {}
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder

    purchase_order_by_id: Dict[int, Any] = {}
    for order in await PurchaseOrder.filter(
        tenant_id=tenant_id, id__in=list(order_ids), deleted_at__isnull=True
    ):
        purchase_order_by_id[int(order.id)] = order
    return purchase_order_by_id
