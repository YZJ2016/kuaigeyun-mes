"""工序委外：默认套数基数、已发料套数与建议发料/收货数量。"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from apps.kuaizhizao.models.outsource_order import OutsourceOrder
from apps.kuaizhizao.models.outsource_work_order import OutsourceMaterialIssue
from apps.kuaizhizao.models.work_order import WorkOrder
from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
from apps.kuaizhizao.services.operation_jump_rules import work_order_allows_operation_jump
from apps.kuaizhizao.services.operation_transfer_service import resolve_operation_transfer_qualified
from apps.kuaizhizao.services.outsource_material_issue_service import OutsourceMaterialIssueService


def _dec(value: object) -> Decimal:
    return Decimal(str(value or 0))


async def resolve_outsource_default_basis_quantity(
    tenant_id: int,
    work_order: WorkOrder,
    work_order_operation: WorkOrderOperation,
    *,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
) -> Decimal:
    """弹窗默认数量基数：允许跳转=工单计划数；否则=紧邻上道合格转出（首道=计划数）。"""
    plan_qty = _dec(work_order.quantity)
    ops = list(ordered_operations or [])
    if not ops:
        ops = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            work_order_id=int(work_order.id),
            deleted_at__isnull=True,
        ).order_by("sequence", "id").all()

    op_index = 0
    for i, op in enumerate(ops):
        if int(op.id) == int(work_order_operation.id):
            op_index = i
            break

    if work_order_allows_operation_jump(work_order):
        return plan_qty

    if op_index == 0:
        return plan_qty

    adjacent_prev = await resolve_operation_transfer_qualified(
        tenant_id,
        int(work_order.id),
        ops[op_index - 1],
    )
    return adjacent_prev if adjacent_prev > 0 else Decimal("0")


async def resolve_outsource_suggested_receipt_quantity(
    tenant_id: int,
    outsource_order: OutsourceOrder,
    *,
    work_order: Optional[WorkOrder] = None,
    work_order_operation: Optional[WorkOrderOperation] = None,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
) -> Decimal:
    """登记收货弹窗默认本批数量。"""
    out_qty = _dec(outsource_order.outsource_quantity)
    received = _dec(outsource_order.received_quantity)
    remain = max(Decimal("0"), out_qty - received)
    if remain <= 0:
        return Decimal("0")

    wo = work_order
    if wo is None:
        wo = await WorkOrder.filter(
            tenant_id=tenant_id,
            id=int(outsource_order.work_order_id),
            deleted_at__isnull=True,
        ).first()
    if not wo:
        return remain

    op = work_order_operation
    if op is None:
        op = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id=int(outsource_order.work_order_operation_id),
            deleted_at__isnull=True,
        ).first()
    if not op:
        return remain

    basis = await resolve_outsource_default_basis_quantity(
        tenant_id, wo, op, ordered_operations=ordered_operations
    )
    return min(remain, basis) if basis > 0 else remain


async def _load_bom_issue_per_unit(
    tenant_id: int,
    product_id: int,
) -> List[Tuple[int, Decimal]]:
    """每委外 1 件的 BOM 发料子件需求量 (material_id, per_unit)。"""
    from apps.kuaizhizao.utils.bom_helper import calculate_material_requirements_from_bom

    issue_svc = OutsourceMaterialIssueService()
    try:
        reqs = await calculate_material_requirements_from_bom(
            tenant_id=tenant_id,
            material_id=int(product_id),
            required_quantity=1.0,
            only_approved=True,
            for_kitting_analysis=True,
        )
    except Exception:
        return []

    rows: List[Tuple[int, Decimal]] = []
    for r in reqs:
        if not issue_svc._should_issue_for_outsource(
            getattr(r, "issue_method", None),
            getattr(r, "component_type", None),
        ):
            continue
        per_unit = _dec(r.net_requirement or r.gross_requirement or 0)
        if per_unit <= 0:
            continue
        rows.append((int(r.component_id), per_unit))
    return rows


async def compute_issued_batch_quantity(
    tenant_id: int,
    outsource_order: OutsourceOrder,
    *,
    work_order: Optional[WorkOrder] = None,
    issued_map: Optional[Dict[int, Decimal]] = None,
    bom_per_unit: Optional[List[Tuple[int, Decimal]]] = None,
) -> Decimal:
    """已累计发料套数（BOM 齐套瓶颈）。"""
    out_qty = _dec(outsource_order.outsource_quantity)
    if out_qty <= 0:
        return Decimal("0")

    wo = work_order
    if wo is None:
        wo = await WorkOrder.filter(
            tenant_id=tenant_id,
            id=int(outsource_order.work_order_id),
            deleted_at__isnull=True,
        ).first()
    if not wo or not wo.product_id:
        return Decimal("0")

    per_unit_rows = bom_per_unit
    if per_unit_rows is None:
        per_unit_rows = await _load_bom_issue_per_unit(tenant_id, int(wo.product_id))
    if not per_unit_rows:
        return Decimal("0")

    net = issued_map
    if net is None:
        net = await _net_issued_by_material(tenant_id, int(outsource_order.id))

    covers: List[Decimal] = []
    for mid, per_unit in per_unit_rows:
        issued = net.get(mid, Decimal("0"))
        if issued <= 0:
            covers.append(Decimal("0"))
            continue
        covers.append(issued / per_unit)

    if not covers:
        return Decimal("0")
    return min(covers)


async def resolve_outsource_suggested_issue_batch_quantity(
    tenant_id: int,
    outsource_order: OutsourceOrder,
    *,
    work_order: Optional[WorkOrder] = None,
    work_order_operation: Optional[WorkOrderOperation] = None,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
    issued_batch: Optional[Decimal] = None,
) -> Decimal:
    """工序发料本次建议套数。"""
    out_qty = _dec(outsource_order.outsource_quantity)
    if out_qty <= 0:
        return Decimal("0")

    if issued_batch is None:
        issued_batch = await compute_issued_batch_quantity(
            tenant_id, outsource_order, work_order=work_order
        )
    pending_batch = max(Decimal("0"), out_qty - issued_batch)
    if pending_batch <= 0:
        return Decimal("0")

    wo = work_order
    if wo is None:
        wo = await WorkOrder.filter(
            tenant_id=tenant_id,
            id=int(outsource_order.work_order_id),
            deleted_at__isnull=True,
        ).first()
    op = work_order_operation
    if wo and op is None:
        op = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id=int(outsource_order.work_order_operation_id),
            deleted_at__isnull=True,
        ).first()
    if not wo or not op:
        return pending_batch

    basis = await resolve_outsource_default_basis_quantity(
        tenant_id, wo, op, ordered_operations=ordered_operations
    )
    return min(pending_batch, basis) if basis > 0 else pending_batch


async def batch_compute_issued_batch_quantities(
    tenant_id: int,
    outsource_orders: Sequence[OutsourceOrder],
    work_orders_by_id: Dict[int, WorkOrder],
) -> Dict[int, Decimal]:
    """列表批量：outsource_order_id -> 已发料套数。"""
    if not outsource_orders:
        return {}

    order_ids = [int(o.id) for o in outsource_orders if o.id]
    issues = await OutsourceMaterialIssue.filter(
        tenant_id=tenant_id,
        outsource_order_id__in=order_ids,
        deleted_at__isnull=True,
    ).all()
    issued_by_order: Dict[int, Dict[int, Decimal]] = {}
    for issue in issues:
        oid = int(issue.outsource_order_id or 0)
        if oid <= 0:
            continue
        mid = int(issue.material_id)
        issued_by_order.setdefault(oid, {})
        issued_by_order[oid][mid] = issued_by_order[oid].get(mid, Decimal("0")) + _dec(issue.quantity)

    bom_cache: Dict[int, List[Tuple[int, Decimal]]] = {}
    result: Dict[int, Decimal] = {}
    for oo in outsource_orders:
        oid = int(oo.id)
        wo = work_orders_by_id.get(int(oo.work_order_id))
        if not wo or not wo.product_id:
            result[oid] = Decimal("0")
            continue
        pid = int(wo.product_id)
        if pid not in bom_cache:
            bom_cache[pid] = await _load_bom_issue_per_unit(tenant_id, pid)
        result[oid] = await compute_issued_batch_quantity(
            tenant_id,
            oo,
            work_order=wo,
            issued_map=issued_by_order.get(oid, {}),
            bom_per_unit=bom_cache[pid],
        )
    return result


async def _net_issued_by_material(
    tenant_id: int,
    outsource_order_id: int,
) -> Dict[int, Decimal]:
    issues = await OutsourceMaterialIssue.filter(
        tenant_id=tenant_id,
        outsource_order_id=int(outsource_order_id),
        deleted_at__isnull=True,
    ).all()
    net: Dict[int, Decimal] = {}
    for issue in issues:
        mid = int(issue.material_id)
        net[mid] = net.get(mid, Decimal("0")) + _dec(issue.quantity)
    return net