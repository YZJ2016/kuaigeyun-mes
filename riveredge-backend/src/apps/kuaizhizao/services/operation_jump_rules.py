"""
工单工序跳转门禁。

唯一控制源：工单头 ``allow_operation_jump``（开单快照，之后可再改）。

默认写入快照前的读取优先级：
  工单表单显式值 > 物料产品工艺 > 物料分组产品工艺 > 工艺路线

运行时（开工 / 报工 / 在制转入）只认工单快照，不认工序行 ``allow_jump`` /
``is_node_operation``（行上可镜像头字段，仅展示/兼容，不作关闸）。

- ``allow_operation_jump=True``：允许跳过前序，不强制前序合格转入
- ``allow_operation_jump=False``：按序，紧邻前序须有可转下道合格数量
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
from apps.kuaizhizao.services.operation_transfer_service import resolve_operation_transfer_qualified
from infra.exceptions.exceptions import BusinessLogicError


def work_order_allows_operation_jump(work_order: Any) -> bool:
    """工单是否允许工序跳转（唯一控制源）。"""
    return bool(getattr(work_order, "allow_operation_jump", False))


def operation_allows_jump(operation: Any) -> bool:
    """
    兼容旧调用：行上 allow_jump 仅为头字段镜像，不作独立真源。
    新逻辑请用 ``work_order_allows_operation_jump``。
    """
    return bool(getattr(operation, "allow_jump", False))


def effective_allow_jump(work_order: Any, work_order_operation: Optional[WorkOrderOperation] = None) -> bool:
    """是否允许跳过前序：只认工单头。"""
    _ = work_order_operation
    return work_order_allows_operation_jump(work_order)


def qualified_transfer_quantity(operation: WorkOrderOperation) -> Decimal:
    """同步回退：报工合格数（调用方应优先使用 qualified_transfer_quantity_async）。"""
    return Decimal(str(getattr(operation, "qualified_quantity", None) or 0))


async def qualified_transfer_quantity_async(
    tenant_id: int,
    work_order_id: int,
    operation: WorkOrderOperation,
    *,
    policy_cache: Optional[Dict[int, Any]] = None,
    inspections_by_op: Optional[Dict[int, List[Any]]] = None,
) -> Decimal:
    """上道工序转入下道的数量（方案质检须过程检验放行后计入）。"""
    return await resolve_operation_transfer_qualified(
        tenant_id,
        work_order_id,
        operation,
        policy_cache=policy_cache,
        inspections_by_op=inspections_by_op,
    )


def find_adjacent_predecessor(predecessors: Sequence[Any]) -> Optional[Any]:
    """按序门禁：紧邻前序（sequence 最大的未删除前序）。"""
    alive = [op for op in predecessors if getattr(op, "deleted_at", None) is None]
    return alive[-1] if alive else None


def find_nearest_jump_gate(
    predecessors: Sequence[Any],
    *,
    allow_operation_jump: bool = False,
) -> Optional[Any]:
    """
    关闸前序。

    允许跳转时无关闸；不允许时关闸为紧邻前序。
    ``predecessors`` 上的行 ``allow_jump`` 不再参与判定。
    """
    if allow_operation_jump:
        return None
    return find_adjacent_predecessor(predecessors)


async def list_predecessors(
    tenant_id: int,
    work_order_id: int,
    current_sequence: int,
) -> List[WorkOrderOperation]:
    return await WorkOrderOperation.filter(
        tenant_id=tenant_id,
        work_order_id=work_order_id,
        sequence__lt=current_sequence,
        deleted_at__isnull=True,
    ).order_by("sequence").all()


async def _load_work_order(tenant_id: int, work_order_id: int, work_order: Optional[Any] = None) -> Any:
    if work_order is not None:
        return work_order
    from apps.kuaizhizao.models.work_order import WorkOrder

    wo = await WorkOrder.get_or_none(
        id=work_order_id,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    )
    if wo is None:
        raise BusinessLogicError(f"工单不存在: id={work_order_id}")
    return wo


async def resolve_jump_gate_predecessor(
    tenant_id: int,
    work_order_id: int,
    work_order_operation: WorkOrderOperation,
    *,
    work_order: Optional[Any] = None,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
) -> Optional[WorkOrderOperation]:
    wo = await _load_work_order(tenant_id, work_order_id, work_order)
    if work_order_allows_operation_jump(wo):
        return None

    current_seq = int(getattr(work_order_operation, "sequence", None) or 0)
    if ordered_operations is not None:
        preds = [
            op
            for op in ordered_operations
            if int(getattr(op, "sequence", None) or 0) < current_seq
            and getattr(op, "deleted_at", None) is None
        ]
    else:
        preds = await list_predecessors(tenant_id, work_order_id, current_seq)
    return find_adjacent_predecessor(preds)


async def resolve_material_incoming_qty(
    tenant_id: int,
    work_order: Any,
    work_order_operation: WorkOrderOperation,
    *,
    plan_qty: Decimal,
    adjacent_prev_transfer: Decimal,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
    policy_cache: Optional[Dict[int, Any]] = None,
    inspections_by_op: Optional[Dict[int, List[Any]]] = None,
) -> Decimal:
    """
    本道可用的在制转入上限。

    - 工单允许跳转：按计划数 + 本道超报（与首道口径一致）；
    - 不允许跳转：取紧邻前序合格转出（无前序则同首道）。
    """
    plan = plan_qty if plan_qty > 0 else Decimal("0")
    from apps.kuaizhizao.services.over_report_rules import first_operation_material_incoming

    if work_order_allows_operation_jump(work_order):
        return first_operation_material_incoming(plan, work_order_operation, work_order)

    work_order_id = int(getattr(work_order_operation, "work_order_id", None) or getattr(work_order, "id") or 0)
    gate = await resolve_jump_gate_predecessor(
        tenant_id,
        work_order_id,
        work_order_operation,
        work_order=work_order,
        ordered_operations=ordered_operations,
    )
    if gate is None:
        return first_operation_material_incoming(plan, work_order_operation, work_order)

    return adjacent_prev_transfer if adjacent_prev_transfer > 0 else Decimal("0")


async def list_node_predecessors(
    tenant_id: int,
    work_order_id: int,
    current_sequence: int,
) -> List[WorkOrderOperation]:
    """兼容旧名：按序时返回紧邻前序；允许跳转时由调用方先看工单头。"""
    preds = await list_predecessors(tenant_id, work_order_id, current_sequence)
    gate = find_adjacent_predecessor(preds)
    return [gate] if gate is not None else []


async def validate_start_respects_node_operations(
    tenant_id: int,
    work_order_id: int,
    work_order_operation: WorkOrderOperation,
) -> None:
    """开工：不允许跳转时，紧邻前序合格转入须 > 0。"""
    await validate_start_respects_jump_gates(tenant_id, work_order_id, work_order_operation)


async def validate_start_respects_jump_gates(
    tenant_id: int,
    work_order_id: int,
    work_order_operation: WorkOrderOperation,
    *,
    work_order: Optional[Any] = None,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
) -> None:
    gate = await resolve_jump_gate_predecessor(
        tenant_id,
        work_order_id,
        work_order_operation,
        work_order=work_order,
        ordered_operations=ordered_operations,
    )
    if gate is None:
        return
    n_transfer = await qualified_transfer_quantity_async(tenant_id, work_order_id, gate)
    if n_transfer <= 0:
        raise BusinessLogicError(
            f"工序跳转规则：前序工序「{gate.operation_name}」尚无可转下道合格数量，不能开始当前工序"
        )


async def validate_reporting_respects_node_operations(
    tenant_id: int,
    work_order_id: int,
    work_order_operation: WorkOrderOperation,
    reporting_type: str,
    reported_quantity: Decimal,
) -> None:
    """兼容旧名 → 工单头跳转报工校验。"""
    await validate_reporting_respects_jump_gates(
        tenant_id,
        work_order_id,
        work_order_operation,
        reporting_type=reporting_type,
        reported_quantity=reported_quantity,
    )


async def validate_reporting_respects_jump_gates(
    tenant_id: int,
    work_order_id: int,
    work_order_operation: WorkOrderOperation,
    reporting_type: str,
    reported_quantity: Decimal,
    *,
    work_order: Optional[Any] = None,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
) -> None:
    """
    报工：
    - 工单允许跳转：不卡前序转入；
    - 不允许：数量累计不可超过紧邻前序合格产出；状态报完成时前序须 completed。
    """
    gate = await resolve_jump_gate_predecessor(
        tenant_id,
        work_order_id,
        work_order_operation,
        work_order=work_order,
        ordered_operations=ordered_operations,
    )
    if gate is None:
        return

    if reporting_type == "status":
        if reported_quantity > 0 and gate.status != "completed":
            raise BusinessLogicError(
                f"工序跳转规则：请先完成前序工序「{gate.operation_name}」后，再将当前工序报为完成"
            )
        return

    current_completed = Decimal(str(work_order_operation.completed_quantity or 0))
    new_total = current_completed + reported_quantity
    n_transfer = await qualified_transfer_quantity_async(tenant_id, work_order_id, gate)
    if reported_quantity > 0 and new_total > n_transfer:
        raise BusinessLogicError(
            f"工序跳转规则：当前工序累计报工数量（{new_total}）不能超过"
            f"前序工序「{gate.operation_name}」的合格产出（{n_transfer}）"
        )
