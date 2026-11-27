"""销售出库加载销项发票：行级可推余量（镜像采购入库 detail_lines）。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from apps.kuaicaiwu.constants.finance_source_types import RECEIVABLE_SOURCE_SALES_DELIVERY
from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
    _q_money,
    _q_qty,
    enrich_standard_invoice_line_fields,
)
from apps.kuaicaiwu.services.sales_delivery_line_finance_occupancy_service import (
    sum_invoice_occupied_by_delivery_item,
)

_RECEIVABLE_DELIVERY_SOURCE_TYPES = frozenset(
    {
        "sales_delivery",
        "SalesDelivery",
        "销售出库",
        RECEIVABLE_SOURCE_SALES_DELIVERY,
    }
)


def resolve_sales_delivery_id_from_receivable(source_type: str, source_id: Any) -> Optional[int]:
    st = str(source_type or "").strip()
    if source_id is None:
        return None
    if st not in _RECEIVABLE_DELIVERY_SOURCE_TYPES:
        return None
    did = int(source_id)
    return did if did > 0 else None


async def build_sales_delivery_finance_detail_lines(
    tenant_id: int,
    delivery_id: int,
) -> List[Dict[str, Any]]:
    from apps.kuaizhizao.models.sales_delivery import SalesDelivery
    from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem

    delivery = await SalesDelivery.get_or_none(
        tenant_id=tenant_id, id=int(delivery_id), deleted_at__isnull=True
    )
    if not delivery:
        return []

    items = await SalesDeliveryItem.filter(
        tenant_id=tenant_id,
        delivery_id=int(delivery_id),
        deleted_at__isnull=True,
    ).order_by("id").all()
    if not items:
        return []

    occupied = await sum_invoice_occupied_by_delivery_item(tenant_id, int(delivery_id))
    lines: List[Dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        item_id = int(item.id)
        line_gross = _q_money(item.total_amount or 0)
        if line_gross <= 0:
            continue
        tax_pct = Decimal(str(item.tax_rate or getattr(delivery, "tax_rate", 0) or 0))
        line_qty = _q_qty(item.delivery_quantity or 0)
        stored_unit = Decimal(str(item.unit_price or 0))
        if tax_pct > 0:
            rate_dec = tax_pct / Decimal("100")
            line_excl = _q_money(line_gross / (Decimal("1") + rate_dec))
        else:
            line_excl = line_gross
        occ = occupied.get(item_id, Decimal("0"))
        max_push = _q_money(line_gross - occ)
        if max_push < 0:
            max_push = Decimal("0")
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
                "source_doc_code": str(getattr(delivery, "delivery_code", None) or ""),
                "sales_delivery_item_id": item_id,
                "purchase_receipt_item_id": item_id,
                "sales_delivery_id": int(delivery_id),
                "gross_amount": float(line_gross),
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


async def batch_sales_delivery_invoice_line_stats(
    tenant_id: int,
    deliveries: Sequence[Any],
) -> Dict[int, Dict[str, int]]:
    """取单列表：出库明细行数、已开票占用行数（批量）。"""
    from tortoise.functions import Sum

    from apps.kuaicaiwu.models.sales_delivery_line_finance_occupancy import (
        SalesDeliveryLineFinanceOccupancy,
    )
    from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem

    if not deliveries:
        return {}
    delivery_ids = [
        int(getattr(d, "id", 0) or 0) for d in deliveries if int(getattr(d, "id", 0) or 0) > 0
    ]
    if not delivery_ids:
        return {}

    items = await SalesDeliveryItem.filter(
        tenant_id=tenant_id,
        delivery_id__in=delivery_ids,
        deleted_at__isnull=True,
    ).all()
    items_by_delivery: Dict[int, List[Any]] = {}
    for item in items:
        did = int(item.delivery_id)
        items_by_delivery.setdefault(did, []).append(item)

    occ_rows = (
        await SalesDeliveryLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            sales_delivery_id__in=delivery_ids,
            occupancy_kind="invoice",
            deleted_at__isnull=True,
        )
        .annotate(total=Sum("amount"))
        .group_by("sales_delivery_id", "sales_delivery_item_id")
        .values("sales_delivery_id", "sales_delivery_item_id", "total")
    )
    occ_positive_item_ids: Dict[int, set[int]] = {}
    for row in occ_rows:
        amt = _q_money(row["total"])
        if amt <= Decimal("0"):
            continue
        did = int(row["sales_delivery_id"])
        iid = int(row["sales_delivery_item_id"])
        occ_positive_item_ids.setdefault(did, set()).add(iid)

    out: Dict[int, Dict[str, int]] = {}
    for did in delivery_ids:
        valid_items = [
            it
            for it in items_by_delivery.get(did, [])
            if _q_money(getattr(it, "total_amount", 0) or 0) > 0
        ]
        invoiced = occ_positive_item_ids.get(did, set())
        out[did] = {
            "detail_line_count": len(valid_items),
            "invoiced_line_count": sum(1 for it in valid_items if int(it.id) in invoiced),
        }
    return out


async def batch_sales_order_invoice_line_stats(
    tenant_id: int,
    orders: Sequence[Any],
    pushed_by_order_id: Mapping[int, Decimal],
) -> Dict[int, Dict[str, int]]:
    """销售订单直开具单列表：明细行数、已全部开完的行数（按头额比例分摊）。"""
    from apps.kuaizhizao.models.sales_order_item import SalesOrderItem

    if not orders:
        return {}
    order_ids = [int(o.id) for o in orders]
    items = await SalesOrderItem.filter(
        tenant_id=tenant_id,
        sales_order_id__in=order_ids,
        deleted_at__isnull=True,
    ).all()
    by_order: Dict[int, List[Any]] = {}
    for item in items:
        by_order.setdefault(int(item.sales_order_id), []).append(item)

    out: Dict[int, Dict[str, int]] = {}
    for order in orders:
        oid = int(order.id)
        pushed = _q_money(pushed_by_order_id.get(oid, Decimal("0")))
        header_gross = _q_money(getattr(order, "total_amount", 0) or 0)
        detail = 0
        invoiced = 0
        for item in by_order.get(oid, []):
            line_gross = _q_money(item.total_amount or 0)
            if line_gross <= 0:
                continue
            detail += 1
            if header_gross > 0 and pushed > 0:
                occupied = _q_money((line_gross / header_gross) * pushed)
            else:
                occupied = Decimal("0")
            max_push = _q_money(line_gross - occupied)
            if max_push <= Decimal("0.01") and occupied > 0:
                invoiced += 1
        out[oid] = {"detail_line_count": detail, "invoiced_line_count": invoiced}
    return out


async def batch_receivable_invoice_line_stats(
    tenant_id: int,
    receivables: Sequence[Any],
) -> Dict[int, Dict[str, int]]:
    """应收单取单：透传关联销售出库的行统计。"""
    from apps.kuaizhizao.models.sales_delivery import SalesDelivery

    if not receivables:
        return {}
    delivery_id_by_receivable: Dict[int, int] = {}
    delivery_ids: set[int] = set()
    for receivable in receivables:
        rid = int(receivable.id)
        delivery_id = resolve_sales_delivery_id_from_receivable(
            str(getattr(receivable, "source_type", "") or ""),
            getattr(receivable, "source_id", None),
        )
        if not delivery_id:
            continue
        delivery_id_by_receivable[rid] = int(delivery_id)
        delivery_ids.add(int(delivery_id))

    if not delivery_ids:
        return {int(r.id): {"detail_line_count": 0, "invoiced_line_count": 0} for r in receivables}

    deliveries = await SalesDelivery.filter(
        tenant_id=tenant_id,
        id__in=list(delivery_ids),
        deleted_at__isnull=True,
    ).all()
    delivery_stats = await batch_sales_delivery_invoice_line_stats(tenant_id, deliveries)
    stats_by_delivery = {int(d.id): delivery_stats.get(int(d.id), {}) for d in deliveries}

    out: Dict[int, Dict[str, int]] = {}
    for receivable in receivables:
        rid = int(receivable.id)
        did = delivery_id_by_receivable.get(rid)
        if did and did in stats_by_delivery:
            st = stats_by_delivery[did]
            out[rid] = {
                "detail_line_count": int(st.get("detail_line_count") or 0),
                "invoiced_line_count": int(st.get("invoiced_line_count") or 0),
            }
        else:
            out[rid] = {"detail_line_count": 0, "invoiced_line_count": 0}
    return out


async def build_sales_order_invoice_detail_lines(
    tenant_id: int,
    order_id: int,
    *,
    header_pushed: Decimal,
) -> List[Dict[str, Any]]:
    """销售订单直开销项：按行价税与头表已开票比例展示行占用（镜像采购订单）。"""
    from apps.kuaizhizao.models.sales_order import SalesOrder
    from apps.kuaizhizao.models.sales_order_item import SalesOrderItem

    order = await SalesOrder.get_or_none(
        tenant_id=tenant_id, id=int(order_id), deleted_at__isnull=True
    )
    if not order:
        return []
    items = await SalesOrderItem.filter(
        tenant_id=tenant_id,
        sales_order_id=int(order_id),
        deleted_at__isnull=True,
    ).order_by("id").all()
    if not items:
        return []

    header_gross = _q_money(order.total_amount or 0)
    pushed = _q_money(header_pushed)
    if pushed < 0:
        pushed = Decimal("0")

    lines: List[Dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        item_id = int(item.id)
        line_gross = _q_money(item.total_amount or 0)
        if line_gross <= 0:
            continue
        tax_pct = Decimal(str(item.tax_rate or getattr(order, "tax_rate", 0) or 0))
        line_qty = _q_qty(item.order_quantity or 0)
        stored_unit = Decimal(str(item.unit_price or 0))
        if tax_pct > 0:
            rate_dec = tax_pct / Decimal("100")
            line_excl = _q_money(line_gross / (Decimal("1") + rate_dec))
        else:
            line_excl = line_gross
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
                "sales_order_item_id": item_id,
                "purchase_receipt_item_id": item_id,
                "sales_order_id": int(order_id),
                "material_code": str(item.material_code or ""),
                "material_name": str(item.material_name or ""),
                "material_spec": getattr(item, "material_spec", None),
                "unit": str(item.material_unit or ""),
                "quantity": float(line_qty),
                **inv,
                "occupied_amount": float(occupied),
                "max_push_amount": float(max_push),
                "max_push_quantity": float(max_push_qty),
            }
        )
    return lines


async def build_invoice_detail_lines_from_receivable(
    tenant_id: int,
    receivable_id: int,
) -> Tuple[Optional[int], List[Dict[str, Any]]]:
    from apps.kuaicaiwu.models.receivable import Receivable

    receivable = await Receivable.get_or_none(
        tenant_id=tenant_id, id=int(receivable_id), deleted_at__isnull=True
    )
    if not receivable:
        return None, []
    delivery_id = resolve_sales_delivery_id_from_receivable(
        str(getattr(receivable, "source_type", "") or ""),
        getattr(receivable, "source_id", None),
    )
    if not delivery_id:
        return None, []
    lines = await build_sales_delivery_finance_detail_lines(tenant_id, delivery_id)
    return delivery_id, lines