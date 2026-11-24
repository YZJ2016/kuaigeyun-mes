"""成品入库从工单取单：领料与工序报工门禁（列表与建单共用）。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
from apps.kuaizhizao.services.document_action_policy.types import CAPABILITY_REASON_MESSAGES
from apps.kuaizhizao.services.work_order_bom_line_service import WorkOrderBomLineService
from apps.kuaizhizao.services.work_order_service import WorkOrderService
from apps.kuaizhizao.utils.bom_helper import calculate_material_requirements_from_bom
from apps.kuaizhizao.utils.issue_method_resolver import is_pick_list_material
from apps.kuaizhizao.utils.mrp_bom_snapshot import bom_expand_kwargs_from_work_order
from apps.kuaizhizao.utils.mrp_quantity import MRP_QTY_STEP
from apps.kuaizhizao.utils.picking_posting import sum_confirmed_picked_by_material
from infra.exceptions.exceptions import BusinessLogicError

REASON_PICK_INCOMPLETE = "finished_goods_inbound.pull.pick_incomplete"
REASON_OPERATION_NOT_REPORTED = "finished_goods_inbound.pull.operation_not_reported"


@dataclass(frozen=True)
class FgPullReadinessResult:
    eligible: bool
    has_pick_bom: bool
    has_operations: bool
    reason_code: Optional[str] = None


def _pick_requirements(requirements: Sequence[Any]) -> List[Tuple[int, Decimal]]:
    rows: List[Tuple[int, Decimal]] = []
    for req in requirements or []:
        if not is_pick_list_material(
            getattr(req, "issue_method", None),
            getattr(req, "component_type", None),
        ):
            continue
        mid = int(getattr(req, "component_id", 0) or 0)
        if mid <= 0:
            continue
        required = Decimal(
            str(
                getattr(req, "gross_requirement", None)
                or getattr(req, "net_requirement", None)
                or 0
            )
        )
        if required <= 0:
            continue
        rows.append((mid, required))
    return rows


async def _load_material_requirements(tenant_id: int, work_order: Any) -> List[Any]:
    bom_line_svc = WorkOrderBomLineService()
    requirements = await bom_line_svc.build_requirements_from_saved_lines(
        tenant_id, work_order
    )
    if requirements is not None:
        return list(requirements)
    try:
        expanded = await calculate_material_requirements_from_bom(
            tenant_id=tenant_id,
            material_id=int(work_order.product_id),
            required_quantity=float(work_order.quantity or 0),
            only_approved=True,
            variant_attributes=getattr(work_order, "variant_attributes", None),
            configurable_selections=getattr(work_order, "configurable_selections", None),
            for_kitting_analysis=True,
            **bom_expand_kwargs_from_work_order(work_order),
        )
        return list(expanded or [])
    except Exception:
        return []


async def _pick_materials_fully_issued(
    tenant_id: int, work_order_id: int, pick_reqs: List[Tuple[int, Decimal]]
) -> bool:
    if not pick_reqs:
        return True
    picked_map = await sum_confirmed_picked_by_material(tenant_id, work_order_id)
    for mid, required in pick_reqs:
        picked = Decimal(str(picked_map.get(mid, 0) or 0))
        if picked + MRP_QTY_STEP < required:
            return False
    return True


async def _all_operations_reported(
    tenant_id: int,
    work_order_id: int,
    operations: List[WorkOrderOperation],
) -> bool:
    if not operations:
        return True
    wo_svc = WorkOrderService()
    for op in operations:
        if not await wo_svc._work_order_operation_has_reporting_qty(
            tenant_id, work_order_id, op
        ):
            return False
    return True


async def evaluate_fg_pull_readiness(
    tenant_id: int,
    work_order: Any,
    *,
    operations: Optional[List[WorkOrderOperation]] = None,
) -> FgPullReadinessResult:
    wo_id = int(getattr(work_order, "id", 0) or 0)
    if operations is None:
        operations = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            work_order_id=wo_id,
            deleted_at__isnull=True,
        ).all()

    has_operations = bool(operations)
    requirements = await _load_material_requirements(tenant_id, work_order)
    pick_reqs = _pick_requirements(requirements)
    has_pick_bom = bool(pick_reqs)

    if not has_pick_bom and not has_operations:
        return FgPullReadinessResult(
            eligible=True,
            has_pick_bom=False,
            has_operations=False,
        )

    pick_ok = True
    if has_pick_bom:
        pick_ok = await _pick_materials_fully_issued(tenant_id, wo_id, pick_reqs)
        if not pick_ok:
            return FgPullReadinessResult(
                eligible=False,
                has_pick_bom=True,
                has_operations=has_operations,
                reason_code=REASON_PICK_INCOMPLETE,
            )

    if has_operations:
        ops_ok = await _all_operations_reported(tenant_id, wo_id, operations)
        if not ops_ok:
            return FgPullReadinessResult(
                eligible=False,
                has_pick_bom=has_pick_bom,
                has_operations=True,
                reason_code=REASON_OPERATION_NOT_REPORTED,
            )

    return FgPullReadinessResult(
        eligible=True,
        has_pick_bom=has_pick_bom,
        has_operations=has_operations,
    )


async def batch_evaluate_fg_pull_readiness(
    tenant_id: int,
    work_orders: Sequence[Any],
) -> Dict[int, FgPullReadinessResult]:
    rows = [wo for wo in work_orders if getattr(wo, "id", None)]
    if not rows:
        return {}
    ids = [int(wo.id) for wo in rows]
    all_ops = await WorkOrderOperation.filter(
        tenant_id=tenant_id,
        work_order_id__in=ids,
        deleted_at__isnull=True,
    ).all()
    ops_by_wo: Dict[int, List[WorkOrderOperation]] = {}
    for op in all_ops:
        wid = int(op.work_order_id)
        ops_by_wo.setdefault(wid, []).append(op)

    out: Dict[int, FgPullReadinessResult] = {}
    for wo in rows:
        wid = int(wo.id)
        out[wid] = await evaluate_fg_pull_readiness(
            tenant_id,
            wo,
            operations=ops_by_wo.get(wid, []),
        )
    return out


async def assert_fg_inbound_pull_readiness(tenant_id: int, work_order: Any) -> None:
    result = await evaluate_fg_pull_readiness(tenant_id, work_order)
    if result.eligible:
        return
    code = result.reason_code or ""
    message = CAPABILITY_REASON_MESSAGES.get(code)
    if not message:
        message = "工单不满足成品入库取单条件"
    raise BusinessLogicError(message)