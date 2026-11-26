"""计划/销售来源行占用：MRP 已分析、工单已转单（均含转采购）。"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple

from apps.kuaizhizao.services.sales_order_purchase_push import (
    batch_pushed_purchase_qty_by_sales_order_item,
    batch_pushed_work_order_qty_by_sales_order_item,
)

PullTarget = Literal["mrp", "work_order"]


def _dec(v: Any) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


async def batch_mrp_seeds_consumed_by_demand_item(
    tenant_id: int, demand_item_ids: List[int]
) -> Dict[int, Decimal]:
    """各 DemandItem 已纳入需求计算的累计数量（来自 computation_params.pull_line_seeds）。"""
    if not demand_item_ids:
        return {}
    from apps.kuaizhizao.models.demand_computation import DemandComputation

    item_set = {int(i) for i in demand_item_ids if int(i) > 0}
    consumed: Dict[int, Decimal] = {i: Decimal("0") for i in item_set}
    comp_rows = await DemandComputation.filter(tenant_id=tenant_id).values_list(
        "computation_params", flat=True
    )
    for params in comp_rows:
        if not isinstance(params, dict):
            continue
        seeds = params.get("pull_line_seeds") or []
        if not isinstance(seeds, list):
            continue
        for seed in seeds:
            if not isinstance(seed, dict):
                continue
            if str(seed.get("kind") or "") != "demand_item":
                continue
            lid = int(seed.get("line_id") or seed.get("demand_item_id") or 0)
            if lid not in item_set:
                continue
            consumed[lid] = consumed.get(lid, Decimal("0")) + _dec(seed.get("quantity"))

    # 历史整单下推无 seeds：需求已 pushed 且存在计算时，该行全量计入
    from apps.kuaizhizao.models.demand import Demand
    from apps.kuaizhizao.models.demand_item import DemandItem

    items = await DemandItem.filter(tenant_id=tenant_id, id__in=list(item_set)).all()
    demand_ids = {int(it.demand_id) for it in items}
    if demand_ids:
        demands = await Demand.filter(
            tenant_id=tenant_id, id__in=list(demand_ids), deleted_at__isnull=True
        ).all()
        pushed_demands = {
            int(d.id) for d in demands if bool(getattr(d, "pushed_to_computation", False))
        }
        has_comp = set()
        if pushed_demands:
            comps = await DemandComputation.filter(
                tenant_id=tenant_id, demand_id__in=list(pushed_demands)
            ).values_list("demand_id", flat=True)
            has_comp = {int(x) for x in comps if x}
        for it in items:
            did = int(it.demand_id)
            if did in pushed_demands and did in has_comp:
                # 若已有 seeds 记账则不再整单加满
                if consumed.get(int(it.id), Decimal("0")) > 0:
                    continue
                consumed[int(it.id)] = _dec(it.required_quantity)
    return consumed


async def batch_work_order_qty_by_demand_item(
    tenant_id: int, demand_item_ids: List[int]
) -> Dict[int, Decimal]:
    from apps.kuaizhizao.models.work_order import WorkOrder

    ids = [int(i) for i in demand_item_ids if int(i) > 0]
    out = {i: Decimal("0") for i in ids}
    if not ids:
        return out
    rows = await WorkOrder.filter(
        tenant_id=tenant_id,
        demand_item_id__in=ids,
        deleted_at__isnull=True,
    ).exclude(status__in=["cancelled", "CANCELLED", "已取消"]).values_list(
        "demand_item_id", "quantity"
    )
    for di_id, qty in rows:
        lid = int(di_id or 0)
        if lid in out:
            out[lid] = out[lid] + _dec(qty)
    return out


async def batch_purchase_qty_by_demand(
    tenant_id: int, demand_ids: List[int]
) -> Dict[int, Dict[int, Decimal]]:
    """demand_id -> material_id -> 采购占用（PR+PO）。"""
    result: Dict[int, Dict[int, Decimal]] = {int(d): {} for d in demand_ids}
    if not demand_ids:
        return result
    from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem
    from apps.kuaizhizao.models.purchase_requisition import (
        PurchaseRequisition,
        PurchaseRequisitionItem,
    )

    src_types = {"demand", "demand_plan", "Demand", "DemandPlan"}
    prs = await PurchaseRequisition.filter(
        tenant_id=tenant_id,
        source_id__in=demand_ids,
        deleted_at__isnull=True,
    ).all()
    pr_by_demand: Dict[int, List[int]] = defaultdict(list)
    for pr in prs:
        if str(getattr(pr, "source_type", "") or "").strip() not in src_types:
            continue
        did = int(pr.source_id or 0)
        if did in result:
            pr_by_demand[did].append(int(pr.id))
    all_pr = [p for ids in pr_by_demand.values() for p in ids]
    if all_pr:
        pr_items = await PurchaseRequisitionItem.filter(
            tenant_id=tenant_id, requisition_id__in=all_pr
        ).all()
        pr_demand = {pid: did for did, ids in pr_by_demand.items() for pid in ids}
        for item in pr_items:
            did = pr_demand.get(int(item.requisition_id))
            mid = int(item.material_id or 0)
            if not did or mid <= 0:
                continue
            bucket = result.setdefault(did, {})
            bucket[mid] = bucket.get(mid, Decimal("0")) + _dec(item.quantity)

    pos = await PurchaseOrder.filter(
        tenant_id=tenant_id,
        source_id__in=demand_ids,
        deleted_at__isnull=True,
    ).all()
    po_by_demand: Dict[int, List[int]] = defaultdict(list)
    for po in pos:
        if str(getattr(po, "source_type", "") or "").strip() not in src_types:
            continue
        did = int(po.source_id or 0)
        if did in result:
            po_by_demand[did].append(int(po.id))
    all_po = [p for ids in po_by_demand.values() for p in ids]
    if all_po:
        po_items = await PurchaseOrderItem.filter(
            tenant_id=tenant_id, order_id__in=all_po
        ).all()
        po_demand = {pid: did for did, ids in po_by_demand.items() for pid in ids}
        for item in po_items:
            did = po_demand.get(int(item.order_id))
            mid = int(item.material_id or 0)
            if not did or mid <= 0:
                continue
            bucket = result.setdefault(did, {})
            bucket[mid] = bucket.get(mid, Decimal("0")) + _dec(item.ordered_quantity)
    return result


def _allocate_material_pool_across_lines(
    order_items: List[Any],
    pool_by_material: Dict[int, Decimal],
    line_qty_attr: str = "order_quantity",
) -> Dict[int, Decimal]:
    """按行顺序从物料池扣减，返回每行分配量（item.id -> allocated）。"""
    cursor = dict(pool_by_material)
    allocated: Dict[int, Decimal] = {}
    for it in sorted(order_items, key=lambda x: int(getattr(x, "id", 0) or 0)):
        lid = int(getattr(it, "id", 0) or 0)
        mid = int(getattr(it, "material_id", 0) or 0)
        qty = _dec(getattr(it, line_qty_attr, None) or getattr(it, "required_quantity", 0))
        if qty <= 0 or lid <= 0:
            allocated[lid] = Decimal("0")
            continue
        pool = cursor.get(mid, Decimal("0"))
        take = min(qty, pool) if pool > 0 else Decimal("0")
        allocated[lid] = take
        if mid > 0:
            cursor[mid] = pool - take
    return allocated


async def sales_order_item_fulfillment_rows(
    tenant_id: int,
    items_by_order: Dict[int, List[Any]],
    *,
    target: PullTarget,
) -> Dict[int, Dict[str, float]]:
    """sales_order_item.id -> 占用行。

    工单/采购互相扣减共享余量；``pushed_work_order_quantity`` /
    ``pushed_purchase_quantity`` 分开展示，``transferred_quantity`` 为二者合计。
    """
    if not items_by_order:
        return {}

    purchase_by_item, wo_by_item = await asyncio.gather(
        batch_pushed_purchase_qty_by_sales_order_item(tenant_id, items_by_order),
        batch_pushed_work_order_qty_by_sales_order_item(tenant_id, items_by_order),
    )
    mrp_by_so_item: Dict[int, Decimal] = {}
    if target == "mrp":
        mrp_by_so_item = {
            k: _dec(v)
            for k, v in (
                await batch_mrp_consumed_by_sales_order_item(
                    tenant_id, list(items_by_order.keys())
                )
            ).items()
        }

    out: Dict[int, Dict[str, float]] = {}

    for order_items in items_by_order.values():
        for it in order_items:
            lid = int(getattr(it, "id", 0) or 0)
            qty = _dec(getattr(it, "order_quantity", 0))
            if lid <= 0 or qty <= 0:
                continue
            purchase = purchase_by_item.get(lid, Decimal("0"))
            wo = wo_by_item.get(lid, Decimal("0"))
            mrp_line = mrp_by_so_item.get(lid, Decimal("0"))

            fulfilled = purchase + wo
            analyzed = purchase + wo + mrp_line

            if target == "work_order":
                remaining = qty - fulfilled
                if remaining < 0:
                    remaining = Decimal("0")
                out[lid] = {
                    "quantity": float(qty),
                    "pushed_work_order_quantity": float(wo),
                    "pushed_purchase_quantity": float(purchase),
                    "pushed_quantity": float(fulfilled),
                    "transferred_quantity": float(fulfilled),
                    "analyzed_quantity": float(analyzed),
                    "remaining_quantity": float(remaining),
                }
            else:
                remaining = qty - analyzed
                if remaining < 0:
                    remaining = Decimal("0")
                out[lid] = {
                    "quantity": float(qty),
                    "pushed_work_order_quantity": float(wo),
                    "pushed_purchase_quantity": float(purchase),
                    "analyzed_quantity": float(analyzed),
                    "transferred_quantity": float(fulfilled),
                    "remaining_quantity": float(remaining),
                }
    return out


async def batch_mrp_consumed_by_sales_order_item(
    tenant_id: int, order_ids: List[int]
) -> Dict[int, Decimal]:
    """SO 行已进 MRP：关联 Demand 明细按物料分摊到订单行。"""
    from apps.kuaizhizao.models.demand import Demand
    from apps.kuaizhizao.models.demand_item import DemandItem
    from apps.kuaizhizao.models.sales_order_item import SalesOrderItem

    out: Dict[int, Decimal] = {}
    if not order_ids:
        return out
    demands = await Demand.filter(
        tenant_id=tenant_id,
        source_type="sales_order",
        source_id__in=order_ids,
        deleted_at__isnull=True,
    ).all()
    by_order: Dict[int, Demand] = {int(d.source_id): d for d in demands if d.source_id}
    for oid in order_ids:
        demand = by_order.get(int(oid))
        if not demand:
            continue
        d_items = await DemandItem.filter(tenant_id=tenant_id, demand_id=demand.id).all()
        so_items = await SalesOrderItem.filter(
            tenant_id=tenant_id, sales_order_id=int(oid)
        ).order_by("id")
        # demand item qty by material -> allocate to SO lines
        mat_qty: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        seed_consumed = await batch_mrp_seeds_consumed_by_demand_item(
            tenant_id, [int(x.id) for x in d_items]
        )
        for di in d_items:
            mid = int(di.material_id or 0)
            qty = seed_consumed.get(int(di.id), Decimal("0"))
            if qty <= 0 and bool(getattr(demand, "pushed_to_computation", False)):
                qty = _dec(di.required_quantity)
            if mid > 0:
                mat_qty[mid] += qty
        pool = dict(mat_qty)
        for so_it in so_items:
            lid = int(so_it.id)
            mid = int(so_it.material_id or 0)
            line_qty = _dec(so_it.order_quantity)
            avail = pool.get(mid, Decimal("0"))
            take = min(line_qty, avail) if avail > 0 else Decimal("0")
            if take > 0:
                out[lid] = out.get(lid, Decimal("0")) + take
                pool[mid] = avail - take
    return out


async def demand_plan_item_fulfillment_rows(
    tenant_id: int,
    demand_items: List[Any],
    *,
    target: PullTarget,
) -> Dict[int, Dict[str, float]]:
    ids = [int(getattr(it, "id", 0)) for it in demand_items]
    ids = [i for i in ids if i > 0]
    mrp_map = await batch_mrp_seeds_consumed_by_demand_item(tenant_id, ids)
    wo_map = await batch_work_order_qty_by_demand_item(tenant_id, ids)
    demand_ids = list({int(getattr(it, "demand_id", 0)) for it in demand_items})
    purchase_by_demand = await batch_purchase_qty_by_demand(tenant_id, demand_ids)

    items_by_demand: Dict[int, List[Any]] = defaultdict(list)
    for it in demand_items:
        items_by_demand[int(it.demand_id)].append(it)

    purchase_alloc: Dict[int, Decimal] = {}
    for did, group in items_by_demand.items():
        pool = dict(purchase_by_demand.get(did, {}))
        part = _allocate_material_pool_across_lines(group, pool, "required_quantity")
        purchase_alloc.update(part)

    out: Dict[int, Dict[str, float]] = {}
    for it in demand_items:
        lid = int(it.id)
        qty = _dec(it.required_quantity)
        if qty <= 0:
            continue
        purchase = purchase_alloc.get(lid, Decimal("0"))
        wo = wo_map.get(lid, Decimal("0"))
        mrp = mrp_map.get(lid, Decimal("0"))
        transferred = purchase + wo
        analyzed = purchase + wo + mrp
        if target == "work_order":
            remaining = qty - transferred
        else:
            remaining = qty - analyzed
        if remaining < 0:
            remaining = Decimal("0")
        out[lid] = {
            "quantity": float(qty),
            "analyzed_quantity": float(analyzed),
            "transferred_quantity": float(transferred),
            "remaining_quantity": float(remaining),
        }
    return out


async def resolve_demand_item_id_for_sales_order_item(
    tenant_id: int,
    sales_order_id: int,
    sales_order_item_id: int,
) -> Optional[int]:
    """按物料维度与行顺序，将销售订单行映射到关联 Demand 明细 id。"""
    from apps.kuaizhizao.models.demand import Demand
    from apps.kuaizhizao.models.demand_item import DemandItem
    from apps.kuaizhizao.models.sales_order_item import SalesOrderItem

    demand = await Demand.get_or_none(
        tenant_id=tenant_id,
        source_type="sales_order",
        source_id=int(sales_order_id),
        deleted_at__isnull=True,
    )
    if not demand:
        return None
    so_item = await SalesOrderItem.get_or_none(
        tenant_id=tenant_id,
        id=int(sales_order_item_id),
        sales_order_id=int(sales_order_id),
        deleted_at__isnull=True,
    )
    if not so_item:
        return None
    mid = int(so_item.material_id or 0)
    so_siblings = await SalesOrderItem.filter(
        tenant_id=tenant_id,
        sales_order_id=int(sales_order_id),
        material_id=mid,
        deleted_at__isnull=True,
    ).order_by("id")
    di_siblings = await DemandItem.filter(
        tenant_id=tenant_id,
        demand_id=int(demand.id),
        material_id=mid,
        deleted_at__isnull=True,
    ).order_by("id")
    so_ids = [int(s.id) for s in so_siblings]
    if int(sales_order_item_id) not in so_ids:
        return None
    idx = so_ids.index(int(sales_order_item_id))
    if idx < len(di_siblings):
        return int(di_siblings[idx].id)
    if len(di_siblings) == 1:
        return int(di_siblings[0].id)
    return None


async def enrich_pull_lines_bom_warehouse(
    tenant_id: int, lines: List[Dict[str, Any]]
) -> None:
    """就地补充 warehouse_*、bom_version、bom_multi_version_allowed。"""
    if not lines:
        return
    from apps.master_data.models.material import BOM, Material
    from apps.master_data.models.warehouse import Warehouse
    from apps.master_data.services.material_service import (
        resolve_primary_default_warehouse_from_material,
    )
    from infra.services.business_config_service import BusinessConfigService

    unique_mids = sorted(
        {int(r.get("material_id") or 0) for r in lines if int(r.get("material_id") or 0) > 0}
    )
    bom_multi = await BusinessConfigService().get_bom_multi_version_allowed(tenant_id)

    bom_base = BOM.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        is_active=True,
        is_obsolete=False,
        approval_status="approved",
    )
    has_bom_ids: set[int] = set()
    default_bom: Dict[int, str] = {}
    if unique_mids:
        parent_rows = await bom_base.filter(material_id__in=unique_mids).distinct().values_list(
            "material_id", flat=True
        )
        has_bom_ids = {int(mid) for mid in parent_rows if mid is not None}
        if has_bom_ids:
            default_rows = await bom_base.filter(
                material_id__in=list(has_bom_ids), is_default=True
            ).values_list("material_id", "version")
            for mid_raw, ver in default_rows:
                mid = int(mid_raw or 0)
                if mid <= 0 or mid in default_bom:
                    continue
                default_bom[mid] = str(ver or "").strip()
            need_version = [mid for mid in has_bom_ids if mid not in default_bom]
            for mid in need_version:
                latest = (
                    await bom_base.filter(material_id=mid).order_by("-id").only("version").first()
                )
                if latest and latest.version:
                    default_bom[mid] = str(latest.version).strip()

    materials = await Material.filter(
        tenant_id=tenant_id, id__in=unique_mids, deleted_at__isnull=True
    ).all()
    wh_by_mid: Dict[int, Tuple[int, Optional[str]]] = {}
    for material in materials:
        wh_pair = await resolve_primary_default_warehouse_from_material(
            tenant_id, material=material
        )
        if wh_pair and wh_pair[0]:
            wh_by_mid[int(material.id)] = (int(wh_pair[0]), wh_pair[1])

    wh_name_cache: Dict[int, str] = {}
    bom_map = {mid: mid in has_bom_ids for mid in unique_mids}

    for row in lines:
        mid = int(row.get("material_id") or 0)
        row["bom_multi_version_allowed"] = bool(bom_multi and bom_map.get(mid))
        row["has_bom"] = bool(bom_map.get(mid))
        row["bom_version"] = default_bom.get(mid) or None
        wh_pair = wh_by_mid.get(mid)
        if not wh_pair:
            row["warehouse_id"] = None
            row["warehouse_name"] = None
            continue
        wid = int(wh_pair[0])
        row["warehouse_id"] = wid
        name = str(wh_pair[1] or "").strip()
        if name:
            row["warehouse_name"] = name
            continue
        if wid not in wh_name_cache:
            wh = await Warehouse.get_or_none(
                tenant_id=tenant_id, id=wid, deleted_at__isnull=True
            )
            wh_name_cache[wid] = str(wh.name).strip() if wh and wh.name else ""
        row["warehouse_name"] = wh_name_cache[wid] or None