"""
工单工序跳转门禁。

唯一控制源：工单头 ``allow_operation_jump``（开单快照，之后可再改）。

默认写入快照前的读取优先级：
  工单表单显式值 > 物料产品工艺 > 物料分组产品工艺 > 工艺路线

运行时（开工 / 报工 / 委外下达 / 在制转入）认工单头 ``allow_operation_jump``。
工序行 ``allow_jump`` 只是展示镜像，不是第二套真源。节点是否可跳认行上
``is_node_operation``。

- ``allow_operation_jump=True``：非节点工序可跳过；前序节点工序仍不可跳过
  （尚无合格产出时，后续不能开工、不能报工、不能下达委外）
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

    允许跳转时关闸为最近的前序节点工序（无节点则可跳）；不允许时为紧邻前序。
    行上 ``allow_jump`` 不参与判定。
    """
    alive = [op for op in predecessors if getattr(op, "deleted_at", None) is None]
    if allow_operation_jump:
        nodes = [op for op in alive if bool(getattr(op, "is_node_operation", False))]
        return nodes[-1] if nodes else None
    return alive[-1] if alive else None


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


def _previous_operations(
    current: WorkOrderOperation,
    predecessors: Sequence[Any],
) -> List[Any]:
    current_seq = int(getattr(current, "sequence", None) or 0)
    alive = []
    for op in predecessors:
        if getattr(op, "deleted_at", None) is not None:
            continue
        if int(getattr(op, "sequence", None) or 0) >= current_seq:
            continue
        alive.append(op)
    return alive


async def previous_node_operations(
    tenant_id: int,
    work_order_id: int,
    work_order_operation: WorkOrderOperation,
    *,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
) -> List[Any]:
    """当前工序之前的节点工序（按 sequence 升序）。"""
    current_seq = int(getattr(work_order_operation, "sequence", None) or 0)
    if ordered_operations is not None:
        preds = _previous_operations(work_order_operation, ordered_operations)
    else:
        preds = await list_predecessors(tenant_id, work_order_id, current_seq)
    return [op for op in preds if bool(getattr(op, "is_node_operation", False))]


async def first_blocking_previous_node(
    tenant_id: int,
    work_order: Any,
    work_order_operation: WorkOrderOperation,
    *,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
    policy_cache: Optional[Dict[int, Any]] = None,
    inspections_by_op: Optional[Dict[int, List[Any]]] = None,
) -> Optional[Any]:
    """
    允许跳转时，返回第一个尚无合格产出的前序节点工序。

    不允许跳转时返回 None（紧邻前序由按序关闸负责）。行上 allow_jump 不参与。
    """
    if not work_order_allows_operation_jump(work_order):
        return None
    work_order_id = int(
        getattr(work_order_operation, "work_order_id", None) or getattr(work_order, "id") or 0
    )
    nodes = await previous_node_operations(
        tenant_id,
        work_order_id,
        work_order_operation,
        ordered_operations=ordered_operations,
    )
    for node in nodes:
        transferred = await qualified_transfer_quantity_async(
            tenant_id,
            work_order_id,
            node,
            policy_cache=policy_cache,
            inspections_by_op=inspections_by_op,
        )
        if transferred <= 0:
            return node
    return None


def previous_node_blocked_message(node: Any) -> str:
    name = getattr(node, "operation_name", None) or "节点工序"
    return (
        f"允许跳转时前序节点仍不可跳过：前序节点工序「{name}」尚无合格产出"
    )


async def assert_previous_nodes_have_qualified_output(
    tenant_id: int,
    work_order: Any,
    work_order_operation: WorkOrderOperation,
    *,
    ordered_operations: Optional[Sequence[WorkOrderOperation]] = None,
    policy_cache: Optional[Dict[int, Any]] = None,
    inspections_by_op: Optional[Dict[int, List[Any]]] = None,
) -> None:
    """开工 / 报工 / 委外下达：允许跳转时前序节点仍不可跳过。"""
    blocked = await first_blocking_previous_node(
        tenant_id,
        work_order,
        work_order_operation,
        ordered_operations=ordered_operations,
        policy_cache=policy_cache,
        inspections_by_op=inspections_by_op,
    )
    if blocked is not None:
        raise BusinessLogicError(previous_node_blocked_message(blocked))


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

    - 工单允许跳转：按工单计划数（超报不占在制，须补领抬高）；
      前序节点尚无合格产出时为 0，后续不能开工/报工/下达委外。
    - 不允许跳转：取紧邻前序合格转出（无前序则同计划数）。
    """
    plan = plan_qty if plan_qty > 0 else Decimal("0")
    from apps.kuaizhizao.services.over_report_rules import first_operation_material_incoming

    if work_order_allows_operation_jump(work_order):
        blocked = await first_blocking_previous_node(
            tenant_id,
            work_order,
            work_order_operation,
            ordered_operations=ordered_operations,
            policy_cache=policy_cache,
            inspections_by_op=inspections_by_op,
        )
        if blocked is not None:
            return Decimal("0")
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
    wo = await _load_work_order(tenant_id, work_order_id, work_order)
    await assert_previous_nodes_have_qualified_output(
        tenant_id,
        wo,
        work_order_operation,
        ordered_operations=ordered_operations,
    )
    gate = await resolve_jump_gate_predecessor(
        tenant_id,
        work_order_id,
        work_order_operation,
        work_order=wo,
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
    - 工单允许跳转：非节点可跳；前序节点尚无合格产出时不可报。有合格产出后不按节点数量封顶。
    - 不允许：数量累计不可超过紧邻前序合格产出；状态报完成时前序须 completed。
    """
    wo = await _load_work_order(tenant_id, work_order_id, work_order)
    await assert_previous_nodes_have_qualified_output(
        tenant_id,
        wo,
        work_order_operation,
        ordered_operations=ordered_operations,
    )
    gate = await resolve_jump_gate_predecessor(
        tenant_id,
        work_order_id,
        work_order_operation,
        work_order=wo,
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
