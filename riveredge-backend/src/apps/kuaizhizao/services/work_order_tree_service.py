"""
工单列表树形子行：拆分工单 / 返工单 / 工序委外单挂在原工单下
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable, List, Optional

from apps.kuaizhizao.models.outsource_order import OutsourceOrder
from apps.kuaizhizao.models.rework_order import ReworkOrder
from apps.kuaizhizao.models.work_order import WorkOrder
from apps.kuaizhizao.schemas.work_order import WorkOrderListResponse

def _split_child_response(wo: WorkOrder) -> WorkOrderListResponse:
    item = WorkOrderListResponse.model_validate(wo)
    return item.model_copy(update={"row_kind": "split", "parent_work_order_id": wo.parent_work_order_id})


def _rework_child_response(
    parent_id: int,
    rework: ReworkOrder,
    *,
    rework_operation_names: Optional[str] = None,
) -> WorkOrderListResponse:
    return WorkOrderListResponse(
        id=rework.id,
        uuid=rework.uuid,
        code=rework.code,
        name=rework.rework_type,
        product_name=rework.product_name,
        quantity=rework.quantity,
        production_mode="—",
        status=rework.status,
        planned_start_date=rework.planned_start_date,
        planned_end_date=rework.planned_end_date,
        created_at=rework.created_at,
        row_kind="rework",
        parent_work_order_id=parent_id,
        rework_type=rework.rework_type,
        rework_operation_names=rework_operation_names or None,
    )


def _outsource_child_response(parent_id: int, order: OutsourceOrder) -> WorkOrderListResponse:
    return WorkOrderListResponse(
        id=order.id,
        uuid=order.uuid,
        code=order.code,
        name=order.operation_name,
        product_name=order.operation_name or order.work_order_code,
        quantity=order.outsource_quantity,
        production_mode="—",
        status=order.status,
        planned_start_date=order.planned_start_date,
        planned_end_date=order.planned_end_date,
        created_at=order.created_at,
        row_kind="outsource",
        parent_work_order_id=parent_id,
        operation_name=order.operation_name,
        supplier_name=order.supplier_name,
    )


class WorkOrderTreeService:
    async def _collect_split_descendants(
        self,
        tenant_id: int,
        root_ids: List[int],
    ) -> List[WorkOrder]:
        """BFS 拉取根工单下全部层级的拆分子工单（含子工单再次拆分）。"""
        split_rows: List[WorkOrder] = []
        frontier = list(root_ids)
        seen_parent_ids: set[int] = set()
        while frontier:
            batch_ids = [pid for pid in frontier if pid not in seen_parent_ids]
            if not batch_ids:
                break
            seen_parent_ids.update(batch_ids)
            rows = await WorkOrder.filter(
                tenant_id=tenant_id,
                parent_work_order_id__in=batch_ids,
                deleted_at__isnull=True,
            ).order_by("code").all()
            if not rows:
                break
            split_rows.extend(rows)
            frontier = [row.id for row in rows if row.id is not None]
        return split_rows

    async def attach_tree_children(
        self,
        tenant_id: int,
        roots: Iterable[WorkOrderListResponse],
        *,
        operation_steps_by_wo_id: dict[int, list] | None = None,
        refresh_stale_readiness: bool = True,
        include_downstream_push_progress: bool = True,
    ) -> List[WorkOrderListResponse]:
        root_list = list(roots)
        if not root_list:
            return []

        parent_ids = [r.id for r in root_list if r.id is not None]
        if not parent_ids:
            return [r.model_copy(update={"row_kind": "work_order"}) for r in root_list]

        split_rows = await self._collect_split_descendants(tenant_id, parent_ids)

        from apps.kuaizhizao.services.work_order_readiness_service import (
            READINESS_ACTIVE_STATUSES,
            WorkOrderReadinessService,
        )

        stale_split_ids = [
            row.id
            for row in split_rows
            if row.id is not None
            and row.readiness_rate is None
            and (row.status or "") in READINESS_ACTIVE_STATUSES
        ]
        if refresh_stale_readiness and stale_split_ids:
            await WorkOrderReadinessService().refresh_work_orders(tenant_id, stale_split_ids)
            split_rows = await self._collect_split_descendants(tenant_id, parent_ids)

        # 拆分子工单的工序由拆分写入路径 _provision_split_work_order_operations 保证，
        # 历史缺失数据用 scripts/backfill_split_child_operations.py 离线补齐；
        # 列表读路径不再逐子工单补写（原实现为每子工单 2-4 次串行查询且会写库）。

        from apps.kuaizhizao.services.work_order_operation_steps import (
            as_route_only_operation_steps,
            build_work_order_operation_steps,
        )

        split_steps_by_id: dict[int, list] = {}
        # 列表页只对根工单算了完工进度；拆分子单挂树上时需单独批量计算，否则子/已拆分父恒为 0%
        split_progress_by_id: dict[int, float] = {}
        split_ids = [row.id for row in split_rows if row.id is not None]
        if split_ids:
            from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation

            split_ops = await WorkOrderOperation.filter(
                tenant_id=tenant_id,
                work_order_id__in=split_ids,
                deleted_at__isnull=True,
            ).order_by("work_order_id", "sequence").all()
            ops_by_split: dict[int, list] = defaultdict(list)
            for op in split_ops:
                ops_by_split[op.work_order_id].append(op)
            qty_by_split = {row.id: float(row.quantity or 0) for row in split_rows if row.id is not None}
            for sid, ops in ops_by_split.items():
                raw_ops = [
                    {
                        "operation_name": op.operation_name,
                        "sequence": op.sequence,
                        "status": op.status,
                        "qualified_quantity": op.qualified_quantity,
                    }
                    for op in ops
                ]
                split_steps_by_id[sid] = build_work_order_operation_steps(
                    raw_ops,
                    qty_by_split.get(sid, 0),
                )

            if include_downstream_push_progress:
                from apps.kuaizhizao.services.work_order_service import WorkOrderService

                split_progress_by_id = await WorkOrderService()._batch_work_order_downstream_push_progress(
                    tenant_id,
                    split_rows,
                )

        # 返工/委外挂在主工单与任意层级拆分子工单下
        tree_host_ids = list({*parent_ids, *split_ids})
        rework_rows = await ReworkOrder.filter(
            tenant_id=tenant_id,
            original_work_order_id__in=tree_host_ids,
            deleted_at__isnull=True,
        ).order_by("code").all()

        rework_op_names_by_rework_id: dict[int, str] = {}
        start_op_ids = [
            row.start_work_order_operation_id
            for row in rework_rows
            if row.start_work_order_operation_id is not None
        ]
        if start_op_ids:
            from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation

            start_ops = await WorkOrderOperation.filter(
                tenant_id=tenant_id,
                id__in=start_op_ids,
                deleted_at__isnull=True,
            ).all()
            start_op_name_by_id = {
                op.id: (op.operation_name or op.operation_code or "").strip()
                for op in start_ops
                if op.id is not None
            }
            for row in rework_rows:
                if row.id is not None and row.start_work_order_operation_id is not None:
                    name = start_op_name_by_id.get(row.start_work_order_operation_id, "")
                    if name:
                        rework_op_names_by_rework_id[row.id] = name

        outsource_rows = await OutsourceOrder.filter(
            tenant_id=tenant_id,
            work_order_id__in=tree_host_ids,
            deleted_at__isnull=True,
        ).order_by("code").all()

        splits_by_parent: dict[int, list[WorkOrderListResponse]] = defaultdict(list)
        quantity_by_split_id: dict[int, Decimal] = {}
        status_by_split_id: dict[int, str] = {}
        for row in split_rows:
            if row.parent_work_order_id is not None:
                child = _split_child_response(row)
                if row.id is not None:
                    quantity_by_split_id[row.id] = Decimal(str(row.quantity or 0))
                    status_by_split_id[row.id] = str(row.status or "")
                    own_steps = (
                        (operation_steps_by_wo_id or {}).get(row.id)
                        or split_steps_by_id.get(row.id)
                        or []
                    )
                    # 缺自有工序时仅借父行路线名，不借父行完工进度
                    steps = own_steps or as_route_only_operation_steps(
                        (operation_steps_by_wo_id or {}).get(row.parent_work_order_id)
                    )
                    child_update: dict = {}
                    if steps:
                        child_update["operation_steps"] = steps
                    if include_downstream_push_progress and row.id in split_progress_by_id:
                        child_update["downstream_push_progress"] = split_progress_by_id[row.id]
                    if child_update:
                        child = child.model_copy(update=child_update)
                splits_by_parent[row.parent_work_order_id].append(child)

        reworks_by_parent: dict[int, list[WorkOrderListResponse]] = defaultdict(list)
        for row in rework_rows:
            if row.original_work_order_id is not None:
                reworks_by_parent[row.original_work_order_id].append(
                    _rework_child_response(
                        row.original_work_order_id,
                        row,
                        rework_operation_names=rework_op_names_by_rework_id.get(row.id or 0),
                    )
                )

        outsources_by_parent: dict[int, list[WorkOrderListResponse]] = defaultdict(list)
        for row in outsource_rows:
            outsources_by_parent[row.work_order_id].append(_outsource_child_response(row.work_order_id, row))

        def _tree_child_sort_key(item: WorkOrderListResponse) -> tuple:
            kind = item.row_kind or "split"
            kind_order = {"split": 0, "rework": 1, "outsource": 2}.get(kind, 3)
            return (kind_order, item.code or "")

        def _nest_children(
            host_id: int,
            *,
            host_quantity: Decimal,
            host_status: str,
            clear_parent_id: bool,
            root_kind: str = "work_order",
            base: Optional[WorkOrderListResponse] = None,
            visiting: Optional[set[int]] = None,
        ) -> WorkOrderListResponse:
            seen = visiting if visiting is not None else set()
            if host_id in seen:
                if base is None:
                    raise ValueError("split tree cycle without host node")
                return base
            seen = set(seen)
            seen.add(host_id)
            split_children = splits_by_parent.get(host_id, [])
            nested_splits: List[WorkOrderListResponse] = []
            for sc in split_children:
                if sc.id is None:
                    nested_splits.append(sc)
                    continue
                nested_splits.append(
                    _nest_children(
                        sc.id,
                        host_quantity=quantity_by_split_id.get(sc.id, Decimal(str(sc.quantity or 0))),
                        host_status=status_by_split_id.get(sc.id, str(sc.status or "")),
                        clear_parent_id=False,
                        root_kind="split",
                        base=sc,
                        visiting=seen,
                    )
                )
            children: List[WorkOrderListResponse] = []
            children.extend(nested_splits)
            children.extend(reworks_by_parent.get(host_id, []))
            children.extend(outsources_by_parent.get(host_id, []))
            if children:
                children.sort(key=_tree_child_sort_key)
            split_remaining_quantity = None
            if host_status == "split":
                allocated = sum(
                    Decimal(str(c.quantity or 0))
                    for c in nested_splits
                )
                split_remaining_quantity = max(Decimal("0"), host_quantity - allocated)
            update: dict = {
                "row_kind": root_kind,
                "split_remaining_quantity": split_remaining_quantity,
                "children": children or None,
            }
            # 已拆分容器自身工序已归档，完工进度按子单数量加权（未拆完剩余量视为 0%）
            if (
                include_downstream_push_progress
                and host_status == "split"
                and host_quantity > 0
            ):
                weighted = sum(
                    (
                        Decimal(str(c.downstream_push_progress or 0))
                        * Decimal(str(c.quantity or 0))
                    )
                    for c in nested_splits
                )
                update["downstream_push_progress"] = float(
                    round(weighted / host_quantity, 1)
                )
            if clear_parent_id:
                update["parent_work_order_id"] = None
            if base is not None:
                return base.model_copy(update=update)
            raise ValueError("base required for nested split nodes")

        result: List[WorkOrderListResponse] = []
        for root in root_list:
            pid = root.id
            if pid is None:
                result.append(root.model_copy(update={"row_kind": "work_order"}))
                continue
            result.append(
                _nest_children(
                    pid,
                    host_quantity=Decimal(str(root.quantity or 0)),
                    host_status=str(root.status or ""),
                    clear_parent_id=True,
                    root_kind="work_order",
                    base=root,
                )
            )
        return result
