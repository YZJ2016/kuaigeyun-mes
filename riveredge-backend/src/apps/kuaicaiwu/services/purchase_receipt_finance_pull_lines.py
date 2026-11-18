"""
采购入库单加载应付/收票：行级可推余量与显式行选择校验。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
    PurchaseReceiptLineFinanceOccupancyService,
    _KIND_INVOICE,
    _KIND_PAYABLE,
    _q_money,
    _q_qty,
)
from apps.kuaicaiwu.constants.finance_source_types import PAYABLE_SOURCE_PURCHASE_RECEIPT
from infra.exceptions.exceptions import ValidationError

_PAYABLE_RECEIPT_SOURCE_TYPES = frozenset(
    {
        "purchase_receipt",
        "采购入库",
        "PurchaseReceipt",
        PAYABLE_SOURCE_PURCHASE_RECEIPT,
    }
)


def resolve_purchase_receipt_id_from_payable(source_type: str, source_id: Any) -> Optional[int]:
    st = str(source_type or "").strip()
    if source_id is None:
        return None
    if st not in _PAYABLE_RECEIPT_SOURCE_TYPES:
        return None
    rid = int(source_id)
    return rid if rid > 0 else None


def enrich_standard_invoice_line_fields(
    *,
    line_excl: Decimal,
    tax_rate_percent: Decimal,
    quantity: Decimal,
    stored_unit_price_excl: Optional[Decimal] = None,
    tax_amount: Optional[Decimal] = None,
) -> Dict[str, float]:
    """标准发票行：未税单价/金额 + 税率% + 税额（与票面明细列一致）。

    采购入库行必须传入已按数量×录入单价算出的税额，禁止在这里用未税再乘税率。
    """
    from apps.kuaicaiwu.services.purchase_settlement import quantize_money

    excl = quantize_money(line_excl)
    pct = Decimal(str(tax_rate_percent or 0))
    if tax_amount is None:
        raise ValidationError("采购入库取单行税额须由数量×录入单价拆分，禁止未税×税率")
    tax_amt = quantize_money(tax_amount)
    qty = Decimal(str(quantity or 0))
    if stored_unit_price_excl is not None and stored_unit_price_excl > 0:
        unit_excl = quantize_money(stored_unit_price_excl)
    elif qty > 0:
        unit_excl = quantize_money(excl / qty)
    else:
        unit_excl = excl
    return {
        "unit_price": float(unit_excl),
        "amount": float(excl),
        "tax_rate": float(pct),
        "tax_amount": float(tax_amt),
    }


def _kind_for_pull(occupancy_kind: str) -> str:
    k = str(occupancy_kind or "").strip()
    if k == "payable":
        return _KIND_PAYABLE
    if k == "invoice":
        return _KIND_INVOICE
    raise ValidationError(f"不支持的行占用类型: {occupancy_kind}")


async def _purchase_receipt_line_gross_by_item_id(
    tenant_id: int,
    receipt_id: int,
) -> Tuple[Any, List[Any], Dict[int, Decimal], Dict[int, Decimal]]:
    """入库行未税与价税合计分摊（与 purchase_settlement / 应付上限同源）。"""
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
    from apps.kuaizhizao.models.purchase_order import PurchaseOrderItem
    from apps.kuaicaiwu.services.purchase_settlement import (
        compute_purchase_receipt_line_settlement_amounts,
    )

    receipt = await PurchaseReceipt.get_or_none(tenant_id=tenant_id, id=receipt_id)
    items = await PurchaseReceiptItem.filter(
        tenant_id=tenant_id,
        receipt_id=receipt_id,
        deleted_at__isnull=True,
    ).order_by("id").all()
    poi_ids = {
        int(i.purchase_order_item_id or 0)
        for i in items
        if int(i.purchase_order_item_id or 0) > 0
    }
    poi_by_id: Dict[int, Any] = {}
    if poi_ids:
        for poi in await PurchaseOrderItem.filter(tenant_id=tenant_id, id__in=list(poi_ids)):
            poi_by_id[int(poi.id)] = poi

    line_excl_by_id: Dict[int, Decimal] = {}
    line_gross_by_id: Dict[int, Decimal] = {}
    for item in items:
        if receipt is None:
            line_excl_by_id[int(item.id)] = Decimal("0.00")
            line_gross_by_id[int(item.id)] = Decimal("0.00")
            continue
        line_excl, _, line_gross = compute_purchase_receipt_line_settlement_amounts(
            receipt,
            item,
            poi_by_id,
        )
        line_excl_by_id[int(item.id)] = line_excl
        line_gross_by_id[int(item.id)] = line_gross

    return receipt, items, line_excl_by_id, line_gross_by_id


async def build_purchase_receipt_finance_detail_lines(
    tenant_id: int,
    receipt_id: int,
    occupancy_kind: str,
) -> List[Dict[str, Any]]:
    from apps.kuaizhizao.models.purchase_order import PurchaseOrderItem
    from apps.kuaicaiwu.services.purchase_settlement import (
        resolve_receipt_line_tax_rate_percent,
    )

    receipt, items, line_excl_by_id, line_gross_by_id = await _purchase_receipt_line_gross_by_item_id(
        tenant_id, receipt_id
    )
    poi_ids = {
        int(i.purchase_order_item_id or 0)
        for i in items
        if int(i.purchase_order_item_id or 0) > 0
    }
    poi_by_id: Dict[int, Any] = {}
    if poi_ids:
        for poi in await PurchaseOrderItem.filter(tenant_id=tenant_id, id__in=list(poi_ids)):
            poi_by_id[int(poi.id)] = poi

    kind = _kind_for_pull(occupancy_kind)
    svc = PurchaseReceiptLineFinanceOccupancyService()
    occupied = await svc._sum_occupied_by_item(tenant_id, receipt_id, kind)

    lines: List[Dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        item_id = int(item.id)
        line_excl = line_excl_by_id[item_id]
        line_gross = line_gross_by_id[item_id]
        occ = occupied.get(item_id, Decimal("0"))
        max_push = _q_money(line_gross - occ)
        if max_push < 0:
            max_push = Decimal("0")
        line_qty = _q_qty(item.receipt_quantity or 0)
        stored_unit = Decimal(str(item.unit_price or 0))
        poi_id = int(item.purchase_order_item_id or 0) or None
        tax_pct = (
            resolve_receipt_line_tax_rate_percent(
                receipt=receipt,
                purchase_order_item_id=poi_id,
                poi_by_id=poi_by_id,
                receipt_line=item,
            )
            if receipt is not None
            else Decimal("0")
        )
        inv = enrich_standard_invoice_line_fields(
            line_excl=line_excl,
            tax_rate_percent=tax_pct,
            quantity=line_qty,
            stored_unit_price_excl=stored_unit if stored_unit > 0 else None,
            tax_amount=line_gross - line_excl,
        )
        if line_gross > 0 and max_push > 0 and line_qty > 0:
            max_push_qty = _q_qty((max_push / line_gross) * line_qty)
            if max_push_qty > line_qty:
                max_push_qty = line_qty
        elif max_push == line_gross and line_gross > 0:
            max_push_qty = line_qty
        else:
            max_push_qty = Decimal("0")

        lines.append(
            {
                "line_no": idx,
                "purchase_receipt_item_id": int(item.id),
                "material_code": str(item.material_code or ""),
                "material_name": str(item.material_name or ""),
                "material_spec": getattr(item, "material_spec", None),
                "unit": str(item.material_unit or ""),
                "quantity": float(line_qty),
                **inv,
                "occupied_amount": float(occ),
                "max_push_amount": float(max_push),
                "max_push_quantity": float(max_push_qty),
            }
        )
    return lines


async def build_slices_from_pull_receipt_line_selections(
    tenant_id: int,
    receipt_id: int,
    occupancy_kind: str,
    selections: Sequence[Any],
    *,
    header_amount: Decimal,
    max_push_by_item: Optional[Dict[int, Decimal]] = None,
) -> List[Tuple[int, Decimal, Decimal]]:
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

    if not selections:
        raise ValidationError("请选择至少一行入库明细")

    kind = _kind_for_pull(occupancy_kind)
    if max_push_by_item is not None:
        max_by_item = {int(k): _q_money(v) for k, v in max_push_by_item.items()}
    else:
        detail = await build_purchase_receipt_finance_detail_lines(tenant_id, receipt_id, kind)
        max_by_item = {
            int(d["purchase_receipt_item_id"]): _q_money(d["max_push_amount"]) for d in detail
        }

    item_ids = [
        int(i)
        for i in await PurchaseReceiptItem.filter(
            tenant_id=tenant_id,
            receipt_id=receipt_id,
            deleted_at__isnull=True,
        ).values_list("id", flat=True)
    ]
    valid_ids = set(item_ids)

    slices: List[Tuple[int, Decimal, Decimal]] = []
    total_sel = Decimal("0")
    seen: set[int] = set()

    for raw in selections:
        if hasattr(raw, "purchase_receipt_item_id"):
            item_id = int(raw.purchase_receipt_item_id)
            amt = _q_money(raw.amount)
        elif isinstance(raw, dict):
            item_id = int(raw["purchase_receipt_item_id"])
            amt = _q_money(raw["amount"])
        else:
            raise ValidationError("行选择格式无效")

        if item_id in seen:
            raise ValidationError("同一入库行不可重复选择")
        seen.add(item_id)

        if item_id not in valid_ids:
            raise ValidationError(f"入库明细 {item_id} 不属于该入库单")

        cap = max_by_item.get(item_id, Decimal("0"))
        if amt <= 0:
            raise ValidationError("行应付/开票金额须大于 0")
        if amt > cap:
            raise ValidationError(f"行 {item_id} 金额 {amt} 超过可分摊上限 {cap}")

        item = await PurchaseReceiptItem.get_or_none(
            tenant_id=tenant_id, id=item_id, deleted_at__isnull=True
        )
        if not item:
            raise ValidationError(f"入库明细不存在: {item_id}")

        line_qty = _q_qty(item.receipt_quantity or 0)
        if cap > 0 and amt > 0 and line_qty > 0:
            take_qty = _q_qty((amt / cap) * line_qty)
            if take_qty > line_qty:
                take_qty = line_qty
        elif amt == cap and line_qty > 0:
            take_qty = line_qty
        else:
            take_qty = Decimal("0")

        slices.append((item_id, take_qty, amt))
        total_sel += amt

    header = _q_money(header_amount)
    if abs(total_sel - header) > _q_money("0.01"):
        raise ValidationError(
            f"所选入库行金额合计 {total_sel} 与单据金额 {header} 不一致"
        )
    return slices


async def build_purchase_order_invoice_detail_lines(
    tenant_id: int,
    order_id: int,
    *,
    header_pushed: Decimal,
) -> List[Dict[str, Any]]:
    """采购订单直开进项发票：行价税与 calc_document_line_amounts 同源，并按已开票头额比例展示行占用。"""
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from apps.kuaicaiwu.services.purchase_settlement import (
        purchase_order_settlement_gross,
        quantize_money,
        resolve_purchase_line_tax_rate_percent,
    )
    from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts

    order = await PurchaseOrder.get_or_none(
        tenant_id=tenant_id, id=int(order_id), deleted_at__isnull=True
    )
    if not order:
        return []
    items = await PurchaseOrderItem.filter(
        tenant_id=tenant_id,
        order_id=int(order_id),
        deleted_at__isnull=True,
    ).order_by("id").all()
    if not items:
        return []

    header_gross = purchase_order_settlement_gross(order)
    pushed = _q_money(header_pushed)
    if pushed < 0:
        pushed = Decimal("0")

    header_price_type = str(getattr(order, "price_type", None) or "tax_exclusive")
    lines: List[Dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        line_qty = _q_qty(getattr(item, "ordered_quantity", 0) or 0)
        stored_unit = Decimal(str(getattr(item, "unit_price", 0) or 0))
        display_raw = getattr(item, "display_unit_price", None)
        tax_pct = resolve_purchase_line_tax_rate_percent(
            line_tax_rate=getattr(item, "tax_rate", None),
            header_tax_rate=getattr(order, "tax_rate", None),
        )
        if (
            header_price_type == "tax_inclusive"
            and display_raw is not None
            and Decimal(str(display_raw or 0)) > 0
            and line_qty > 0
        ):
            line_excl, line_tax, line_gross = calc_document_line_amounts(
                line_qty,
                Decimal(str(display_raw)),
                tax_pct,
                "tax_inclusive",
            )
        elif line_qty > 0 and stored_unit > 0:
            line_excl, line_tax, line_gross = calc_document_line_amounts(
                line_qty,
                stored_unit,
                tax_pct,
                "tax_exclusive",
            )
        else:
            line_excl = line_tax = line_gross = Decimal("0")
        line_excl = quantize_money(line_excl)
        line_gross = quantize_money(line_gross)
        if header_gross > 0 and pushed > 0:
            occupied = _q_money((line_gross / header_gross) * pushed)
        else:
            occupied = Decimal("0")
        max_push = _q_money(line_gross - occupied)
        if max_push < 0:
            max_push = Decimal("0")
        inv = enrich_standard_invoice_line_fields(
            line_excl=line_excl,
            tax_rate_percent=tax_pct,
            quantity=line_qty,
            stored_unit_price_excl=stored_unit if stored_unit > 0 else None,
            tax_amount=line_gross - line_excl,
        )
        item_id = int(item.id)
        lines.append(
            {
                "line_no": idx,
                "purchase_order_item_id": item_id,
                "purchase_receipt_item_id": item_id,
                "material_code": str(getattr(item, "material_code", "") or ""),
                "material_name": str(getattr(item, "material_name", "") or ""),
                "material_spec": getattr(item, "material_spec", None),
                "unit": str(getattr(item, "unit", "") or ""),
                "quantity": float(line_qty),
                **inv,
                "occupied_amount": float(occupied),
                "max_push_amount": float(max_push),
                "max_push_quantity": float(line_qty),
            }
        )
    return lines


async def build_invoice_detail_lines_from_payable(
    tenant_id: int,
    payable_id: int,
) -> tuple[Optional[int], List[Dict[str, Any]]]:
    """从应付单解析入库单，并按应付行占用生成收票可选明细（可推上限受应付行与行已收票约束）。"""
    from apps.kuaicaiwu.models.payable import Payable
    from apps.kuaicaiwu.models.purchase_receipt_line_finance_occupancy import (
        PurchaseReceiptLineFinanceOccupancy,
    )
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem

    payable = await Payable.get_or_none(
        tenant_id=tenant_id, id=int(payable_id), deleted_at__isnull=True
    )
    if not payable:
        return None, []

    receipt_id = resolve_purchase_receipt_id_from_payable(
        str(getattr(payable, "source_type", "") or ""),
        getattr(payable, "source_id", None),
    )
    if not receipt_id:
        return None, []

    from apps.kuaizhizao.models.purchase_order import PurchaseOrderItem
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaicaiwu.services.purchase_settlement import (
        resolve_receipt_line_tax_rate_percent,
    )

    _, _all_items, line_excl_by_id, line_gross_by_id = await _purchase_receipt_line_gross_by_item_id(
        tenant_id, receipt_id
    )
    receipt = await PurchaseReceipt.get_or_none(tenant_id=tenant_id, id=receipt_id)

    base_rows = await PurchaseReceiptLineFinanceOccupancy.filter(
        tenant_id=tenant_id,
        occupancy_kind=_KIND_PAYABLE,
        target_doc_type="Payable",
        target_doc_id=int(payable_id),
        deleted_at__isnull=True,
    ).order_by("purchase_receipt_item_id").all()

    if not base_rows:
        lines = await build_purchase_receipt_finance_detail_lines(
            tenant_id, receipt_id, "invoice"
        )
        return receipt_id, lines

    svc = PurchaseReceiptLineFinanceOccupancyService()
    invoice_occupied = await svc._sum_occupied_by_item(tenant_id, receipt_id, _KIND_INVOICE)
    item_ids = [int(r.purchase_receipt_item_id) for r in base_rows]
    items = await PurchaseReceiptItem.filter(
        tenant_id=tenant_id,
        id__in=item_ids,
        deleted_at__isnull=True,
    ).all()
    item_by_id = {int(i.id): i for i in items}
    poi_ids = {
        int(i.purchase_order_item_id or 0)
        for i in items
        if int(i.purchase_order_item_id or 0) > 0
    }
    poi_by_id: Dict[int, Any] = {}
    if poi_ids:
        for poi in await PurchaseOrderItem.filter(tenant_id=tenant_id, id__in=list(poi_ids)):
            poi_by_id[int(poi.id)] = poi

    lines: List[Dict[str, Any]] = []
    for idx, row in enumerate(base_rows, start=1):
        item_id = int(row.purchase_receipt_item_id)
        item = item_by_id.get(item_id)
        if not item:
            continue
        line_excl = line_excl_by_id.get(item_id, Decimal("0"))
        line_gross = line_gross_by_id.get(item_id, Decimal("0"))
        occ_inv = invoice_occupied.get(item_id, Decimal("0"))
        payable_slice = _q_money(row.amount)
        line_remain = _q_money(line_gross - occ_inv)
        if line_remain < 0:
            line_remain = Decimal("0")
        max_push = payable_slice if payable_slice <= line_remain else line_remain
        line_qty = _q_qty(item.receipt_quantity or 0)
        stored_unit = Decimal(str(item.unit_price or 0))
        poi_id = int(item.purchase_order_item_id or 0) or None
        tax_pct = (
            resolve_receipt_line_tax_rate_percent(
                receipt=receipt,
                purchase_order_item_id=poi_id,
                poi_by_id=poi_by_id,
                receipt_line=item,
            )
            if receipt is not None
            else Decimal("0")
        )
        inv = enrich_standard_invoice_line_fields(
            line_excl=line_excl,
            tax_rate_percent=tax_pct,
            quantity=line_qty,
            stored_unit_price_excl=stored_unit if stored_unit > 0 else None,
            tax_amount=line_gross - line_excl,
        )
        if line_gross > 0 and max_push > 0 and line_qty > 0:
            max_push_qty = _q_qty((max_push / line_gross) * line_qty)
            if max_push_qty > line_qty:
                max_push_qty = line_qty
        elif max_push == line_gross and line_gross > 0:
            max_push_qty = line_qty
        else:
            max_push_qty = Decimal("0")

        lines.append(
            {
                "line_no": idx,
                "purchase_receipt_item_id": item_id,
                "material_code": str(item.material_code or ""),
                "material_name": str(item.material_name or ""),
                "material_spec": getattr(item, "material_spec", None),
                "unit": str(item.material_unit or ""),
                "quantity": float(line_qty),
                **inv,
                "occupied_amount": float(occ_inv),
                "payable_line_amount": float(payable_slice),
                "max_push_amount": float(max_push),
                "max_push_quantity": float(max_push_qty),
            }
        )
    return receipt_id, lines
