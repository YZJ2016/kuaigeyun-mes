"""销售订单直推采购申请 / 采购订单（按单外购捷径）。

数量按销售明细订单量减已下推占用，不做库存净需求；占用仅计
source_type=sales_order 的采购申请与直推采购订单，避免与需求计算路径重复累计。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from apps.kuaizhizao.utils.material_source_helper import (
    SOURCE_TYPE_BUY,
    resolve_material_purchase_line_unit_price,
)
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.exceptions.exceptions import BusinessLogicError


def _is_sales_order_source(source_type: Any) -> bool:
    raw = str(source_type or "").strip().lower().replace("-", "_")
    return raw in {"sales_order", "salesorder"}


async def require_purchase_requisition_for_tenant(tenant_id: int) -> bool:
    from infra.services.business_config_service import BusinessConfigService

    biz_config = await BusinessConfigService().get_business_config(tenant_id)
    return bool(
        biz_config.get("parameters", {})
        .get("procurement", {})
        .get("require_purchase_requisition", False)
    )


async def batch_pushed_purchase_qty_by_material(
    tenant_id: int,
    sales_order_ids: List[int],
) -> Dict[int, Dict[int, Decimal]]:
    """order_id → material_id → 已占用数量（SO→PR + SO→PO）。"""
    result: Dict[int, Dict[int, Decimal]] = {int(oid): {} for oid in sales_order_ids}
    if not sales_order_ids:
        return result

    from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from apps.kuaizhizao.models.purchase_requisition import (
        PurchaseRequisition,
        PurchaseRequisitionItem,
    )

    prs = await PurchaseRequisition.filter(
        tenant_id=tenant_id,
        source_id__in=sales_order_ids,
        deleted_at__isnull=True,
    ).all()
    pr_ids_by_order: Dict[int, List[int]] = {}
    for pr in prs:
        if not _is_sales_order_source(pr.source_type):
            continue
        oid = int(pr.source_id or 0)
        if oid not in result:
            continue
        pr_ids_by_order.setdefault(oid, []).append(int(pr.id))

    all_pr_ids = [pid for ids in pr_ids_by_order.values() for pid in ids]
    if all_pr_ids:
        pr_items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id,
            requisition_id__in=all_pr_ids,
        ).all()
        pr_order_by_id = {
            pid: oid for oid, ids in pr_ids_by_order.items() for pid in ids
        }
        for item in pr_items:
            oid = pr_order_by_id.get(int(item.requisition_id))
            mid = int(item.material_id or 0)
            if not oid or mid <= 0:
                continue
            bucket = result.setdefault(oid, {})
            bucket[mid] = bucket.get(mid, Decimal("0")) + Decimal(str(item.quantity or 0))

    pos = await PurchaseOrder.filter(
        tenant_id=tenant_id,
        source_id__in=sales_order_ids,
        deleted_at__isnull=True,
    ).all()
    po_ids_by_order: Dict[int, List[int]] = {}
    for po in pos:
        if not _is_sales_order_source(po.source_type):
            continue
        oid = int(po.source_id or 0)
        if oid not in result:
            continue
        po_ids_by_order.setdefault(oid, []).append(int(po.id))

    all_po_ids = [pid for ids in po_ids_by_order.values() for pid in ids]
    if all_po_ids:
        po_items = await PurchaseOrderItem.filter(
            tenant_id=tenant_id,
            order_id__in=all_po_ids,
        ).all()
        po_order_by_id = {
            pid: oid for oid, ids in po_ids_by_order.items() for pid in ids
        }
        for item in po_items:
            oid = po_order_by_id.get(int(item.order_id))
            mid = int(item.material_id or 0)
            if not oid or mid <= 0:
                continue
            bucket = result.setdefault(oid, {})
            bucket[mid] = bucket.get(mid, Decimal("0")) + Decimal(
                str(item.ordered_quantity or 0)
            )

    return result


async def batch_has_purchasable_remaining(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
) -> Dict[int, bool]:
    from apps.master_data.models.material import Material

    if not items_by_order:
        return {}
    all_mids: set[int] = set()
    for items in items_by_order.values():
        for it in items or []:
            mid = int(getattr(it, "material_id", 0) or 0)
            if mid > 0:
                all_mids.add(mid)
    buy_ids: set[int] = set()
    if all_mids:
        mats = await Material.filter(
            tenant_id=tenant_id, id__in=list(all_mids), deleted_at__isnull=True
        ).only("id", "source_type")
        buy_ids = {
            int(m.id) for m in mats if str(m.source_type or "").strip() == SOURCE_TYPE_BUY
        }

    pushed = await batch_pushed_purchase_qty_by_material(
        tenant_id, list(items_by_order.keys())
    )
    out: Dict[int, bool] = {}
    for oid, items in items_by_order.items():
        totals: Dict[int, Decimal] = {}
        for it in items or []:
            mid = int(getattr(it, "material_id", 0) or 0)
            if mid not in buy_ids:
                continue
            totals[mid] = totals.get(mid, Decimal("0")) + Decimal(
                str(getattr(it, "order_quantity", 0) or 0)
            )
        pushed_for = pushed.get(oid) or {}
        out[oid] = any(
            (totals[mid] - pushed_for.get(mid, Decimal("0"))) > 0 for mid in totals
        )
    return out


async def collect_sales_order_buy_push_lines(
    tenant_id: int,
    sales_order_id: int,
    items: List[Any],
    *,
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[int, Decimal]]:
    """返回可下推行与 material 占用映射。"""
    from apps.master_data.models.material import Material

    selected: Optional[set[int]] = None
    if selected_item_ids is not None:
        selected = {int(x) for x in selected_item_ids if x is not None}

    material_ids = sorted(
        {
            int(getattr(it, "material_id", 0) or 0)
            for it in items
            if int(getattr(it, "material_id", 0) or 0) > 0
        }
    )
    materials = (
        await Material.filter(
            tenant_id=tenant_id, id__in=material_ids, deleted_at__isnull=True
        ).all()
        if material_ids
        else []
    )
    material_by_id = {int(m.id): m for m in materials}
    buy_ids = {
        mid
        for mid, m in material_by_id.items()
        if str(m.source_type or "").strip() == SOURCE_TYPE_BUY
    }

    pushed_map = await batch_pushed_purchase_qty_by_material(tenant_id, [sales_order_id])
    pushed_by_material = pushed_map.get(sales_order_id) or {}

    order_total_by_material: Dict[int, Decimal] = {}
    for it in items:
        mid = int(getattr(it, "material_id", 0) or 0)
        if mid not in buy_ids:
            continue
        order_total_by_material[mid] = order_total_by_material.get(mid, Decimal("0")) + Decimal(
            str(getattr(it, "order_quantity", 0) or 0)
        )

    remaining_cursor: Dict[int, Decimal] = {}
    for mid, total_qty in order_total_by_material.items():
        remaining = total_qty - pushed_by_material.get(mid, Decimal("0"))
        remaining_cursor[mid] = remaining if remaining > 0 else Decimal("0")

    lines: List[Dict[str, Any]] = []
    for it in items:
        item_id = int(getattr(it, "id", 0) or 0)
        mid = int(getattr(it, "material_id", 0) or 0)
        if mid not in buy_ids:
            continue
        if selected is not None and item_id not in selected:
            continue
        qty = Decimal(str(getattr(it, "order_quantity", 0) or 0))
        if qty <= 0:
            continue
        remain = remaining_cursor.get(mid, Decimal("0"))
        max_qty = min(qty, remain) if remain > 0 else Decimal("0")
        if selected_quantities and item_id in selected_quantities:
            override = Decimal(str(selected_quantities[item_id]))
            if override < 0:
                override = Decimal("0")
            max_qty = min(max_qty, override)
        if max_qty <= 0:
            continue
        remaining_cursor[mid] = remain - max_qty
        material = material_by_id.get(mid)
        source_config = (
            material.source_config if material and isinstance(material.source_config, dict) else {}
        )
        inner = (
            source_config.get("source_config")
            if isinstance(source_config.get("source_config"), dict)
            else source_config
        )
        supplier_id = inner.get("default_supplier_id") if isinstance(inner, dict) else None
        supplier_name = (
            (inner.get("default_supplier_name") or "") if isinstance(inner, dict) else ""
        )
        unit_price = (
            resolve_material_purchase_line_unit_price(material=material)
            if material
            else Decimal("0")
        )
        lines.append(
            {
                "item_id": item_id,
                "material_id": mid,
                "material_code": str(
                    getattr(it, "material_code", None)
                    or (material.main_code if material else None)
                    or (material.code if material else None)
                    or mid
                ),
                "material_name": str(
                    getattr(it, "material_name", None)
                    or (material.name if material else None)
                    or ""
                ),
                "material_spec": getattr(it, "material_spec", None)
                or (getattr(material, "specification", None) if material else None),
                "unit": str(
                    getattr(it, "material_unit", None)
                    or (material.base_unit if material else None)
                    or "件"
                ),
                "quantity": qty,
                "pushed_quantity": pushed_by_material.get(mid, Decimal("0")),
                "max_push_quantity": max_qty,
                "required_date": getattr(it, "delivery_date", None),
                "supplier_id": int(supplier_id) if supplier_id else None,
                "supplier_name": str(supplier_name or ""),
                "suggested_unit_price": unit_price or Decimal("0"),
                "material": material,
            }
        )
    return lines, pushed_by_material


async def preview_push_to_purchase_requisition(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
) -> Dict[str, Any]:
    lines, _ = await collect_sales_order_buy_push_lines(tenant_id, int(order.id), items)
    preview_items = [
        {
            "item_id": row["item_id"],
            "material_id": row["material_id"],
            "material_code": row["material_code"],
            "material_name": row["material_name"],
            "material_spec": row["material_spec"],
            "unit": row["unit"],
            "quantity": float(row["quantity"]),
            "pushed_quantity": float(row["pushed_quantity"]),
            "max_push_quantity": float(row["max_push_quantity"]),
            "required_date": str(row["required_date"]) if row["required_date"] else None,
            "supplier_id": row["supplier_id"],
            "suggested_unit_price": float(row["suggested_unit_price"] or 0),
        }
        for row in lines
    ]
    pushable = len(preview_items)
    has_blocking = pushable == 0
    return {
        "target_type": "purchase_requisition",
        "sales_order_id": int(order.id),
        "sales_order_code": order.order_code,
        "summary": (
            f"将按销售明细采购件生成采购申请，共 {pushable} 行可下推"
            if not has_blocking
            else "销售订单无可下推采购件"
        ),
        "items": preview_items,
        "has_blocking_issues": has_blocking,
        "blocking_reason": (
            "sales_order.push_purchase_requisition.no_buy_items" if has_blocking else None
        ),
        "tip": "按销售订单数量下推，不做库存抵扣；已通过本单下推采购申请/采购订单的数量不会重复纳入。",
    }


async def push_to_purchase_requisition(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
    created_by: int,
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
) -> Dict[str, Any]:
    from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
    from apps.kuaizhizao.schemas.purchase_requisition import (
        PurchaseRequisitionCreate,
        PurchaseRequisitionItemCreate,
    )
    from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService
    from apps.kuaizhizao.services.purchase_requisition_service import PurchaseRequisitionService

    lines, _ = await collect_sales_order_buy_push_lines(
        tenant_id,
        int(order.id),
        items,
        selected_item_ids=selected_item_ids,
        selected_quantities=selected_quantities,
    )
    if not lines:
        raise BusinessLogicError("销售订单无可下推采购件，无法生成采购申请")

    today = to_site_date(resolve_business_datetime())
    req_items: List[PurchaseRequisitionItemCreate] = []
    required_dates = []
    for row in lines:
        req_date = row["required_date"] or today
        required_dates.append(req_date)
        req_items.append(
            PurchaseRequisitionItemCreate(
                material_id=row["material_id"],
                material_code=row["material_code"],
                material_name=row["material_name"],
                material_spec=row["material_spec"],
                unit=row["unit"],
                quantity=row["max_push_quantity"],
                suggested_unit_price=row["suggested_unit_price"] or Decimal(0),
                required_date=req_date,
                supplier_id=row["supplier_id"],
                notes=f"销售订单 {order.order_code} 明细#{row['item_id']} 直推请购",
            )
        )

    req = await PurchaseRequisitionService().create_requisition(
        tenant_id=tenant_id,
        data=PurchaseRequisitionCreate(
            requisition_code="",
            requisition_name=f"销售订单{order.order_code}请购",
            requisition_date=today,
            required_date=min(required_dates) if required_dates else today,
            source_type="sales_order",
            source_id=int(order.id),
            source_code=order.order_code,
            notes=f"由销售订单 {order.order_code} 直推生成（按单外购，未做库存抵扣）",
            items=req_items,
        ),
        created_by=created_by,
    )

    try:
        await DocumentRelationNewService().create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type="sales_order",
                source_id=int(order.id),
                source_code=order.order_code,
                source_name=getattr(order, "order_name", None) or order.order_code,
                target_type="purchase_requisition",
                target_id=req.id,
                target_code=req.requisition_code,
                target_name=req.requisition_name,
                relation_type="source",
                relation_mode="push",
                relation_desc="销售订单直推采购申请",
            ),
            created_by=created_by,
        )
    except Exception as exc:
        logger.warning("建立销售订单→采购申请关联失败: %s", exc)

    return {
        "success": True,
        "message": "下推成功，已生成采购申请",
        "target_document": {
            "type": "purchase_requisition",
            "id": req.id,
            "code": req.requisition_code,
        },
    }


async def preview_push_to_purchase_order(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
) -> Dict[str, Any]:
    if await require_purchase_requisition_for_tenant(tenant_id):
        return {
            "target_type": "purchase_order",
            "sales_order_id": int(order.id),
            "sales_order_code": order.order_code,
            "summary": "当前组织要求先采购申请后下单",
            "items": [],
            "has_blocking_issues": True,
            "blocking_reason": "sales_order.push_purchase_order.require_requisition",
            "tip": "请改用「从销售订单创建采购申请」。",
        }

    lines, _ = await collect_sales_order_buy_push_lines(tenant_id, int(order.id), items)
    preview_items = []
    has_blocking = False
    for row in lines:
        issues = []
        if not row["supplier_id"]:
            issues.append("缺少默认供应商，将生成待定供应商草稿单")
        preview_items.append(
            {
                "item_id": row["item_id"],
                "material_id": row["material_id"],
                "material_code": row["material_code"],
                "material_name": row["material_name"],
                "material_spec": row["material_spec"],
                "unit": row["unit"],
                "quantity": float(row["quantity"]),
                "pushed_quantity": float(row["pushed_quantity"]),
                "max_push_quantity": float(row["max_push_quantity"]),
                "required_date": str(row["required_date"]) if row["required_date"] else None,
                "supplier_id": row["supplier_id"],
                "supplier_name": row["supplier_name"],
                "suggested_unit_price": float(row["suggested_unit_price"] or 0),
                "issues": issues,
            }
        )
    pushable = len(preview_items)
    if pushable == 0:
        has_blocking = True
    return {
        "target_type": "purchase_order",
        "sales_order_id": int(order.id),
        "sales_order_code": order.order_code,
        "summary": (
            f"将按供应商分组生成采购订单，共 {pushable} 行可下推"
            if not has_blocking
            else "销售订单无可下推采购件"
        ),
        "items": preview_items,
        "has_blocking_issues": has_blocking,
        "blocking_reason": (
            "sales_order.push_purchase_order.no_buy_items" if has_blocking else None
        ),
        "tip": "按销售订单数量下推，不做库存净需求；无默认供应商的行将归入「待定供应商」草稿单。",
    }


async def push_to_purchase_order(
    *,
    tenant_id: int,
    order: Any,
    items: List[Any],
    created_by: int,
    selected_item_ids: Optional[List[int]] = None,
    selected_quantities: Optional[Dict[int, Decimal]] = None,
) -> Dict[str, Any]:
    from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
    from apps.kuaizhizao.schemas.purchase import PurchaseOrderCreate, PurchaseOrderItemCreate
    from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService
    from apps.kuaizhizao.services.purchase_service import PurchaseService
    from apps.kuaizhizao.utils.sales_order_currency_carry import currency_fields_for_purchase_doc
    from apps.master_data.models.supplier import Supplier

    if await require_purchase_requisition_for_tenant(tenant_id):
        raise BusinessLogicError("当前组织要求先采购申请后下单，请下推采购申请")

    so_currency = currency_fields_for_purchase_doc(order)

    lines, _ = await collect_sales_order_buy_push_lines(
        tenant_id,
        int(order.id),
        items,
        selected_item_ids=selected_item_ids,
        selected_quantities=selected_quantities,
    )
    if not lines:
        raise BusinessLogicError("销售订单无可下推采购件，无法生成采购订单")

    today = to_site_date(resolve_business_datetime())
    by_supplier: Dict[int, List[Dict[str, Any]]] = {}
    for row in lines:
        sid = int(row["supplier_id"] or 0)
        by_supplier.setdefault(sid, []).append(row)

    purchase_service = PurchaseService()
    relation_service = DocumentRelationNewService()
    target_documents: List[Dict[str, Any]] = []

    for supplier_id, group in by_supplier.items():
        supplier_name = "待定供应商"
        if supplier_id > 0:
            supplier = await Supplier.get_or_none(tenant_id=tenant_id, id=supplier_id)
            if supplier:
                supplier_name = supplier.name
            else:
                supplier_name = group[0].get("supplier_name") or f"供应商({supplier_id})"
        elif group[0].get("supplier_name"):
            supplier_name = str(group[0]["supplier_name"])

        po_items: List[PurchaseOrderItemCreate] = []
        required_dates = []
        for row in group:
            qty = row["max_push_quantity"]
            unit_price = row["suggested_unit_price"] or Decimal(0)
            req_date = row["required_date"] or today
            required_dates.append(req_date)
            po_items.append(
                PurchaseOrderItemCreate(
                    material_id=row["material_id"],
                    material_code=row["material_code"],
                    material_name=row["material_name"],
                    material_spec=row["material_spec"],
                    ordered_quantity=qty,
                    unit=row["unit"],
                    unit_price=unit_price,
                    total_price=qty * unit_price,
                    received_quantity=Decimal(0),
                    outstanding_quantity=qty,
                    required_date=req_date,
                    source_type="sales_order",
                    source_id=int(order.id),
                    notes=f"销售订单 {order.order_code} 明细#{row['item_id']} 直推采购",
                )
            )

        po = await purchase_service.create_purchase_order(
            tenant_id=tenant_id,
            order_data=PurchaseOrderCreate(
                supplier_id=supplier_id if supplier_id > 0 else 0,
                supplier_name=supplier_name,
                order_date=today,
                delivery_date=min(required_dates) if required_dates else today,
                order_type="标准采购",
                currency=so_currency["currency"],
                exchange_rate=so_currency["exchange_rate"],
                source_type="sales_order",
                source_id=int(order.id),
                notes=f"由销售订单 {order.order_code} 直推生成（按单外购，未做库存抵扣）",
                items=po_items,
            ),
            created_by=created_by,
        )
        target_documents.append(
            {"type": "purchase_order", "id": po.id, "code": po.order_code}
        )
        try:
            await relation_service.create_relation(
                tenant_id=tenant_id,
                relation_data=DocumentRelationCreate(
                    source_type="sales_order",
                    source_id=int(order.id),
                    source_code=order.order_code,
                    source_name=getattr(order, "order_name", None) or order.order_code,
                    target_type="purchase_order",
                    target_id=po.id,
                    target_code=po.order_code,
                    target_name=po.order_code,
                    relation_type="source",
                    relation_mode="push",
                    relation_desc="销售订单直推采购订单",
                ),
                created_by=created_by,
            )
        except Exception as exc:
            logger.warning("建立销售订单→采购订单关联失败: %s", exc)

    return {
        "success": True,
        "message": f"下推成功，共生成 {len(target_documents)} 张采购订单",
        "target_documents": target_documents,
    }
