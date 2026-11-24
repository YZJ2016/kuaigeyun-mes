"""
委外单业务服务模块

提供委外单相关的业务逻辑处理，包括CRUD操作、状态流转、委外入库关联等。

Author: Luigi Lu
Date: 2025-01-04
"""

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal
from tortoise.queryset import Q
from apps.kuaizhizao.utils.document_amount_write import (
    line_total_qty_unit_price,
    resolve_simple_line_total,
)
from tortoise.transactions import in_transaction

from apps.kuaizhizao.utils.stock_posting import serialize_stock_create

from infra.exceptions.exceptions import NotFoundError, ValidationError, BusinessLogicError

from infra.models.user import User

from apps.common.base_service import AppBaseService
from apps.kuaizhizao.models.outsource_order import OutsourceOrder
from apps.kuaizhizao.models.work_order import WorkOrder
from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
from apps.kuaizhizao.schemas.outsource_order import (
    OutsourceOrderCreate,
    OutsourceOrderUpdate,
    OutsourceOrderResponse,
    OutsourceOrderListResponse,
    OutsourceOptionResponse,
    OutsourceOrderRegisterReceipt,
)
from apps.master_data.models.supplier import Supplier
from apps.kuaizhizao.services.over_report_rules import (
    OVER_REPORT_NONE,
    effective_over_report_for_reporting,
    max_completed_quantity_for_plan,
    remaining_completed_headroom,
    tuple_from_model,
)
from loguru import logger
from core.utils.timezone_utils import resolve_business_datetime, today_site_str

_OUTSOURCE_PULL_WO_STATUSES = frozenset(
    {
        "released",
        "in_progress",
        "已下达",
        "执行中",
        "进行中",
    }
)


def _outsource_pull_line_matches_keyword(
    keyword: Optional[str],
    *,
    work_order: WorkOrder,
    option: OutsourceOptionResponse,
) -> bool:
    kw = str(keyword or "").strip().lower()
    if not kw:
        return True
    parts = (
        work_order.code,
        work_order.name,
        work_order.product_code,
        work_order.product_name,
        option.work_order_code,
        option.operation_code,
        option.operation_name,
        option.material_code,
        option.material_name,
    )
    return any(kw in str(part or "").strip().lower() for part in parts)


@dataclass
class OutsourceOptionsBatchContext:
    """工序委外可委外量批量计算上下文（固定规模查询，不随工单×工序 N+1）。"""

    operations_by_work_order_id: Dict[int, List[WorkOrderOperation]] = field(default_factory=dict)
    product_specification_by_product_id: Dict[int, Optional[str]] = field(default_factory=dict)
    outsource_orders_by_work_order_id: Dict[int, List[OutsourceOrder]] = field(default_factory=dict)
    inspections_by_work_order_id: Dict[int, Dict[int, List[Any]]] = field(default_factory=dict)
    scrap_qty_by_work_order_id: Dict[int, Dict[int, Decimal]] = field(default_factory=dict)
    policy_cache: Dict[int, Tuple[str, Optional[int], str]] = field(default_factory=dict)
    quality_cfg: Any = None
    process_inspection_audit_required: bool = False
    master_operation_by_id: Dict[int, Any] = field(default_factory=dict)


OUTSOURCE_ORDER_SORTABLE_FIELDS = frozenset({
    "code",
    "work_order_code",
    "operation_name",
    "supplier_name",
    "outsource_quantity",
    "received_quantity",
    "qualified_quantity",
    "unit_price",
    "total_amount",
    "status",
    "planned_start_date",
    "planned_end_date",
    "created_at",
    "updated_at",
})


class OutsourceService(AppBaseService[OutsourceOrder]):
    """
    委外单服务类

    处理委外单相关的所有业务逻辑。
    """

    def __init__(self):
        super().__init__(OutsourceOrder)

    @staticmethod
    def _resolve_effective_over_report_cached(
        work_order: WorkOrder,
        work_order_operation: WorkOrderOperation,
        master_operation_by_id: Dict[int, Any],
    ) -> Tuple[str, Decimal]:
        om, ov = effective_over_report_for_reporting(work_order, work_order_operation)
        if om != OVER_REPORT_NONE:
            return om, ov
        mid = getattr(work_order_operation, "operation_id", None)
        if not mid:
            return om, ov
        master = master_operation_by_id.get(int(mid))
        if master is not None:
            return tuple_from_model(master)
        return om, ov

    async def _load_outsource_options_batch_context(
        self,
        tenant_id: int,
        work_orders: List[WorkOrder],
    ) -> OutsourceOptionsBatchContext:
        ctx = OutsourceOptionsBatchContext()
        wo_ids = [int(wo.id) for wo in work_orders if wo.id is not None]
        if not wo_ids:
            return ctx

        from apps.master_data.models.material import Material
        from apps.master_data.models.process import Operation
        from apps.kuaizhizao.models.process_inspection import ProcessInspection
        from apps.kuaizhizao.models.scrap_record import ScrapRecord
        from apps.kuaizhizao.services.inspection_policy_service import get_quality_effective_config
        from apps.kuaizhizao.services.operation_transfer_service import build_operation_policy_cache
        from infra.services.business_config_service import BusinessConfigService

        operations_task = WorkOrderOperation.filter(
            tenant_id=tenant_id,
            work_order_id__in=wo_ids,
            deleted_at__isnull=True,
        ).order_by("sequence", "id").all()
        outsource_task = OutsourceOrder.filter(
            tenant_id=tenant_id,
            work_order_id__in=wo_ids,
            deleted_at__isnull=True,
        ).exclude(status="cancelled").all()
        inspections_task = ProcessInspection.filter(
            tenant_id=tenant_id,
            work_order_id__in=wo_ids,
            deleted_at__isnull=True,
        ).all()
        scrap_task = ScrapRecord.filter(
            tenant_id=tenant_id,
            work_order_id__in=wo_ids,
            status__in=["draft", "confirmed"],
            deleted_at__isnull=True,
        ).all()

        operations, outsource_rows, inspection_rows, scrap_rows = await asyncio.gather(
            operations_task,
            outsource_task,
            inspections_task,
            scrap_task,
        )

        master_op_ids: List[int] = []
        master_op_seen: set[int] = set()
        master_ops_needing_fallback: set[int] = set()
        wo_by_id = {int(wo.id): wo for wo in work_orders if wo.id is not None}

        for op in operations:
            wo_id = int(op.work_order_id)
            ctx.operations_by_work_order_id.setdefault(wo_id, []).append(op)
            if op.operation_id is not None:
                oid = int(op.operation_id)
                if oid not in master_op_seen:
                    master_op_seen.add(oid)
                    master_op_ids.append(oid)
                wo = wo_by_id.get(wo_id)
                if wo is not None:
                    om, _ = effective_over_report_for_reporting(wo, op)
                    if om == OVER_REPORT_NONE:
                        master_ops_needing_fallback.add(oid)

        for row in outsource_rows:
            wo_id = int(row.work_order_id or 0)
            if wo_id > 0:
                ctx.outsource_orders_by_work_order_id.setdefault(wo_id, []).append(row)

        for row in inspection_rows:
            wo_id = int(row.work_order_id or 0)
            op_id = int(row.operation_id or 0)
            if wo_id > 0 and op_id > 0:
                ctx.inspections_by_work_order_id.setdefault(wo_id, defaultdict(list))[op_id].append(row)

        for row in scrap_rows:
            wo_id = int(row.work_order_id or 0)
            op_id = row.operation_id
            if wo_id <= 0 or op_id is None:
                continue
            kid = int(op_id)
            bucket = ctx.scrap_qty_by_work_order_id.setdefault(wo_id, {})
            bucket[kid] = bucket.get(kid, Decimal("0")) + Decimal(str(row.scrap_quantity or 0))

        product_ids = sorted({int(wo.product_id) for wo in work_orders if wo.product_id})
        materials_task = (
            Material.filter(
                tenant_id=tenant_id,
                id__in=product_ids,
                deleted_at__isnull=True,
            )
            .only("id", "specification")
            .all()
            if product_ids
            else None
        )
        master_task = (
            Operation.filter(
                tenant_id=tenant_id,
                id__in=sorted(master_ops_needing_fallback),
                deleted_at__isnull=True,
            ).all()
            if master_ops_needing_fallback
            else None
        )

        policy_task = build_operation_policy_cache(tenant_id, master_op_ids)
        quality_task = get_quality_effective_config(tenant_id)
        audit_task = BusinessConfigService().check_audit_required(tenant_id, "process_inspection")

        gather_parts: List[Any] = [policy_task, quality_task, audit_task]
        if materials_task is not None:
            gather_parts.append(materials_task)
        if master_task is not None:
            gather_parts.append(master_task)

        gathered = await asyncio.gather(*gather_parts)
        ctx.policy_cache = gathered[0]
        ctx.quality_cfg = gathered[1]
        ctx.process_inspection_audit_required = bool(gathered[2])
        idx = 3
        if materials_task is not None:
            for material in gathered[idx]:
                spec = (getattr(material, "specification", None) or "").strip() or None
                ctx.product_specification_by_product_id[int(material.id)] = spec
            idx += 1
        if master_task is not None:
            for master in gathered[idx]:
                ctx.master_operation_by_id[int(master.id)] = master

        return ctx

    async def _resolve_operation_flow_caps(
        self,
        tenant_id: int,
        work_order: WorkOrder,
        work_order_operation: WorkOrderOperation,
        *,
        ordered_operations: Optional[List[WorkOrderOperation]] = None,
        policy_cache: Optional[Dict[int, Tuple[str, Optional[int], str]]] = None,
        quality_cfg: Optional[Any] = None,
        inspections_by_op: Optional[Dict[int, List[Any]]] = None,
        scrap_qty_by_master_operation_id: Optional[Dict[int, Decimal]] = None,
        process_inspection_audit_required: Optional[bool] = None,
        master_operation_by_id: Optional[Dict[int, Any]] = None,
    ) -> Dict[str, Decimal]:
        """
        与厂内报工同一套工艺流转上限：
        计划(+超报)剩余 ∩ 上道转入剩余（允许跳转时按 resolve_material_incoming_qty）。
        """
        from apps.kuaizhizao.services.inspection_policy_service import get_quality_effective_config
        from apps.kuaizhizao.services.operation_jump_rules import resolve_material_incoming_qty
        from apps.kuaizhizao.services.operation_transfer_service import (
            build_operation_policy_cache,
            material_consumed_against_incoming,
            resolve_ipqc_for_work_order_operation,
            resolve_operation_transfer_qualified,
            sum_process_inspection_quality_quantities,
        )
        from apps.kuaizhizao.services.over_report_rules import resolve_effective_over_report_async

        plan_qty = Decimal(str(work_order.quantity or 0))
        if master_operation_by_id is not None:
            om, ov = self._resolve_effective_over_report_cached(
                work_order, work_order_operation, master_operation_by_id
            )
        else:
            om, ov = await resolve_effective_over_report_async(
                tenant_id, work_order, work_order_operation
            )
        max_quantity = max_completed_quantity_for_plan(plan_qty, om, ov)
        completed = Decimal(str(work_order_operation.completed_quantity or 0))
        plan_remaining = remaining_completed_headroom(plan_qty, completed, om, ov)

        ops = ordered_operations
        if ops is None:
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

        if op_index == 0:
            adjacent_prev = max_quantity
        else:
            adjacent_prev = await resolve_operation_transfer_qualified(
                tenant_id,
                int(work_order.id),
                ops[op_index - 1],
                policy_cache=policy_cache,
                inspections_by_op=inspections_by_op,
                audit_required=process_inspection_audit_required,
            )
        incoming = await resolve_material_incoming_qty(
            tenant_id,
            work_order,
            work_order_operation,
            plan_qty=plan_qty,
            adjacent_prev_transfer=adjacent_prev,
            ordered_operations=ops,
            policy_cache=policy_cache,
            inspections_by_op=inspections_by_op,
        )
        from apps.kuaizhizao.services.operation_jump_rules import work_order_allows_operation_jump
        from apps.kuaizhizao.services.work_order_service import WorkOrderService

        # 与厂内报工相同：首道或允许跳转的工序，在制上限加上补领抬高。
        # 前序节点尚无合格产出时 incoming 为 0，不能靠补领绕过节点。
        if incoming > 0 and (
            op_index == 0 or work_order_allows_operation_jump(work_order)
        ):
            incoming = incoming + await WorkOrderService.resolve_material_incoming_picking_extra_units(
                tenant_id, int(work_order.id), plan_qty
            )

        master_id = int(work_order_operation.operation_id) if work_order_operation.operation_id else 0
        mode = "none"
        insp_q, insp_u = Decimal("0"), Decimal("0")
        if master_id > 0:
            local_policy = policy_cache
            if local_policy is None:
                local_policy = await build_operation_policy_cache(tenant_id, [master_id])
            local_quality = quality_cfg
            if local_quality is None:
                local_quality = await get_quality_effective_config(tenant_id)
            mode, _, _ = resolve_ipqc_for_work_order_operation(
                local_quality,
                work_order_operation,
                local_policy.get(master_id, ("none", None, "default_none")),
            )
            if mode == "plan":
                if inspections_by_op is not None:
                    inspections = inspections_by_op.get(master_id, [])
                else:
                    from apps.kuaizhizao.models.process_inspection import ProcessInspection

                    inspections = await ProcessInspection.filter(
                        tenant_id=tenant_id,
                        work_order_id=int(work_order.id),
                        operation_id=master_id,
                        deleted_at__isnull=True,
                    ).all()
                insp_q, insp_u = sum_process_inspection_quality_quantities(inspections)

        qualified = Decimal(str(work_order_operation.qualified_quantity or 0))
        scrap_qty = Decimal("0")
        if master_id > 0:
            if scrap_qty_by_master_operation_id is not None:
                scrap_qty = Decimal(str(scrap_qty_by_master_operation_id.get(master_id, 0) or 0))
            else:
                from apps.kuaizhizao.models.scrap_record import ScrapRecord

                scrap_rows = await ScrapRecord.filter(
                    tenant_id=tenant_id,
                    work_order_id=int(work_order.id),
                    operation_id=master_id,
                    status__in=["draft", "confirmed"],
                    deleted_at__isnull=True,
                ).all()
                for sr in scrap_rows:
                    scrap_qty += Decimal(str(sr.scrap_quantity or 0))

        consumed = material_consumed_against_incoming(
            is_first_operation=op_index == 0,
            inspection_mode=mode,
            completed=completed,
            qualified=qualified,
            inspection_qualified=insp_q,
            inspection_unqualified=insp_u,
            scrap_qty=scrap_qty,
        )
        material_remaining = incoming - consumed
        if material_remaining < 0:
            material_remaining = Decimal("0")

        return {
            "max_quantity": max_quantity,
            "completed_quantity": completed,
            "incoming_quantity": incoming,
            "material_remaining": material_remaining,
            "plan_remaining": plan_remaining,
        }

    @staticmethod
    def _open_outsource_reserved_qty(orders: List[OutsourceOrder]) -> Decimal:
        """未收完的委外占用（出单数量 − 已收），避免与工序已完成重复扣减。"""
        reserved = Decimal("0")
        for row in orders:
            out_qty = Decimal(str(row.outsource_quantity or 0))
            recv = Decimal(str(row.received_quantity or 0))
            open_qty = out_qty - recv
            if open_qty > 0:
                reserved += open_qty
        return reserved

    async def _compute_outsourceable_breakdown(
        self,
        tenant_id: int,
        work_order: WorkOrder,
        work_order_operation: WorkOrderOperation,
        *,
        exclude_outsource_order_id: Optional[int] = None,
        ordered_operations: Optional[List[WorkOrderOperation]] = None,
        apply_incoming_gate: bool = True,
        preloaded_outsource_orders: Optional[List[OutsourceOrder]] = None,
        flow_policy_cache: Optional[Dict[int, Tuple[str, Optional[int], str]]] = None,
        flow_quality_cfg: Optional[Any] = None,
        flow_inspections_by_op: Optional[Dict[int, List[Any]]] = None,
        flow_scrap_qty_by_master_operation_id: Optional[Dict[int, Decimal]] = None,
        flow_process_inspection_audit_required: Optional[bool] = None,
        flow_master_operation_by_id: Optional[Dict[int, Any]] = None,
    ) -> Dict[str, Decimal]:
        """
        apply_incoming_gate=True：可执行量（计划剩余 ∩ 上道转入剩余），用于列表/下达/收货。
        False：仅计划(+超报)剩余，用于草稿预建（提前期），不卡上道转入。
        """
        caps = await self._resolve_operation_flow_caps(
            tenant_id,
            work_order,
            work_order_operation,
            ordered_operations=ordered_operations,
            policy_cache=flow_policy_cache,
            quality_cfg=flow_quality_cfg,
            inspections_by_op=flow_inspections_by_op,
            scrap_qty_by_master_operation_id=flow_scrap_qty_by_master_operation_id,
            process_inspection_audit_required=flow_process_inspection_audit_required,
            master_operation_by_id=flow_master_operation_by_id,
        )
        if preloaded_outsource_orders is not None:
            orders = [
                row
                for row in preloaded_outsource_orders
                if int(row.work_order_operation_id or 0) == int(work_order_operation.id)
                and row.deleted_at is None
                and str(row.status or "") != "cancelled"
                and (
                    exclude_outsource_order_id is None
                    or int(row.id) != int(exclude_outsource_order_id)
                )
            ]
        else:
            q = OutsourceOrder.filter(
                tenant_id=tenant_id,
                work_order_operation_id=int(work_order_operation.id),
                deleted_at__isnull=True,
            ).exclude(status="cancelled")
            if exclude_outsource_order_id:
                q = q.exclude(id=int(exclude_outsource_order_id))
            orders = await q.all()
        already_outsourced = sum(
            (Decimal(str(r.outsource_quantity or 0)) for r in orders),
            Decimal("0"),
        )
        open_reserved = self._open_outsource_reserved_qty(orders)
        plan_remaining = max(Decimal("0"), caps["plan_remaining"] - open_reserved)
        material_remaining = max(Decimal("0"), caps["material_remaining"] - open_reserved)
        if apply_incoming_gate:
            outsourceable_quantity = min(plan_remaining, material_remaining)
        else:
            outsourceable_quantity = plan_remaining
        return {
            "max_quantity": caps["max_quantity"],
            "completed_quantity": caps["completed_quantity"],
            "incoming_quantity": caps["incoming_quantity"],
            "already_outsourced_quantity": already_outsourced,
            "open_reserved_quantity": open_reserved,
            "outsourceable_quantity": outsourceable_quantity,
        }

    async def _list_outsource_options_for_work_order(
        self,
        tenant_id: int,
        work_order: WorkOrder,
        batch_ctx: OutsourceOptionsBatchContext,
    ) -> List[OutsourceOptionResponse]:
        wo_id = int(work_order.id)
        operations = batch_ctx.operations_by_work_order_id.get(wo_id, [])
        preloaded_orders = batch_ctx.outsource_orders_by_work_order_id.get(wo_id, [])

        product_specification: Optional[str] = None
        if work_order.product_id:
            product_specification = batch_ctx.product_specification_by_product_id.get(int(work_order.product_id))

        flow_inspections = batch_ctx.inspections_by_work_order_id.get(wo_id, {})
        flow_scrap = batch_ctx.scrap_qty_by_work_order_id.get(wo_id, {})
        plan_quantity = Decimal(str(work_order.quantity or 0))

        options: List[OutsourceOptionResponse] = []
        for operation in operations:
            breakdown = await self._compute_outsourceable_breakdown(
                tenant_id,
                work_order,
                operation,
                ordered_operations=operations,
                preloaded_outsource_orders=preloaded_orders,
                flow_policy_cache=batch_ctx.policy_cache,
                flow_quality_cfg=batch_ctx.quality_cfg,
                flow_inspections_by_op=flow_inspections,
                flow_scrap_qty_by_master_operation_id=flow_scrap,
                flow_process_inspection_audit_required=batch_ctx.process_inspection_audit_required,
                flow_master_operation_by_id=batch_ctx.master_operation_by_id,
            )
            options.append(
                OutsourceOptionResponse(
                    work_order_operation_id=operation.id,
                    operation_id=operation.operation_id,
                    operation_code=operation.operation_code,
                    operation_name=operation.operation_name,
                    sequence=operation.sequence,
                    work_order_code=str(work_order.code or ""),
                    material_code=str(work_order.product_code or ""),
                    material_name=str(work_order.product_name or ""),
                    specification=product_specification,
                    quantity=plan_quantity,
                    prev_operation_reported_quantity=breakdown["incoming_quantity"],
                    max_quantity=breakdown["max_quantity"],
                    completed_quantity=breakdown["completed_quantity"],
                    already_outsourced_quantity=breakdown["already_outsourced_quantity"],
                    outsourceable_quantity=breakdown["outsourceable_quantity"],
                    default_outsource_supplier_id=(
                        int(operation.default_outsource_supplier_id)
                        if operation.default_outsource_supplier_id
                        else None
                    ),
                    planned_start_date=operation.planned_start_date,
                    planned_end_date=operation.planned_end_date,
                )
            )
        return options

    async def list_outsource_options(
        self,
        tenant_id: int,
        work_order_id: int,
    ) -> List[OutsourceOptionResponse]:
        work_order = await WorkOrder.filter(
            tenant_id=tenant_id,
            id=work_order_id,
            deleted_at__isnull=True,
        ).first()
        if not work_order:
            raise NotFoundError(f"工单不存在: {work_order_id}")

        batch_ctx = await self._load_outsource_options_batch_context(tenant_id, [work_order])
        return await self._list_outsource_options_for_work_order(tenant_id, work_order, batch_ctx)

    @staticmethod
    def _outsource_option_to_pull_line(
        work_order: WorkOrder,
        option: OutsourceOptionResponse,
    ) -> Dict[str, Any]:
        completed = float(option.completed_quantity or 0)
        already = float(option.already_outsourced_quantity or 0)
        return {
            "pull_row_key": f"{int(work_order.id)}-{int(option.work_order_operation_id)}",
            "work_order_id": int(work_order.id),
            "work_order_code": option.work_order_code or work_order.code,
            "work_order_name": work_order.name,
            "product_name": work_order.product_name,
            "material_code": option.material_code,
            "material_name": option.material_name,
            "specification": option.specification,
            "quantity": float(option.quantity or 0),
            "prev_operation_reported_quantity": float(option.prev_operation_reported_quantity or 0),
            "work_order_operation_id": int(option.work_order_operation_id),
            "operation_code": option.operation_code,
            "operation_name": option.operation_name,
            "sequence": int(option.sequence or 0),
            "max_quantity": float(option.max_quantity or 0),
            "completed_quantity": completed,
            "already_outsourced_quantity": already,
            "outsourceable_quantity": float(option.outsourceable_quantity or 0),
            "occupied_quantity": completed + already,
            "default_outsource_supplier_id": option.default_outsource_supplier_id,
            "planned_start_date": option.planned_start_date,
            "planned_end_date": option.planned_end_date,
        }

    async def list_work_order_outsource_pull_lines(
        self,
        tenant_id: int,
        *,
        current_user: Optional[User] = None,
        skip: int = 0,
        limit: int = 20,
        keyword: Optional[str] = None,
        outsourceable_only: bool = True,
    ) -> Dict[str, Any]:
        """
        工序委外取单：执行中/已下达工单 × 工序开口行，服务端分页。
        与工单列表同一套范围与数据范围，避免前端 N+1 请求 outsource-options。
        """
        wo_group_q = Q(group_role__isnull=True) | Q(
            group_role__in=["root", "component", "outsource_component"]
        )
        query = (
            WorkOrder.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
                parent_work_order_id__isnull=True,
                status__in=list(_OUTSOURCE_PULL_WO_STATUSES),
            )
            .filter(wo_group_q)
            .order_by("-created_at", "-id")
        )
        from apps.kuaizhizao.services.kuaizhizao_data_scope import apply_kuaizhizao_list_scope

        query = await apply_kuaizhizao_list_scope(
            query,
            tenant_id=tenant_id,
            current_user=current_user,
            resource="kuaizhizao:work-order",
        )
        work_orders = await query.all()

        batch_ctx = await self._load_outsource_options_batch_context(tenant_id, work_orders)

        lines: List[Dict[str, Any]] = []
        for work_order in work_orders:
            try:
                options = await self._list_outsource_options_for_work_order(
                    tenant_id, work_order, batch_ctx
                )
            except NotFoundError:
                continue
            for option in options:
                if outsourceable_only and float(option.outsourceable_quantity or 0) <= 0:
                    continue
                if not _outsource_pull_line_matches_keyword(keyword, work_order=work_order, option=option):
                    continue
                lines.append(self._outsource_option_to_pull_line(work_order, option))

        lines.sort(
            key=lambda row: (
                str(row.get("work_order_code") or ""),
                int(row.get("sequence") or 0),
                int(row.get("work_order_operation_id") or 0),
            )
        )
        total = len(lines)
        page = lines[skip : skip + limit]
        return {"data": page, "total": total, "success": True}

    @serialize_stock_create("outsource_order")
    async def create_outsource_order(
        self,
        tenant_id: int,
        outsource_order_data: OutsourceOrderCreate,
        created_by: int
    ) -> OutsourceOrderResponse:
        """
        创建委外单

        Args:
            tenant_id: 组织ID
            outsource_order_data: 委外单创建数据
            created_by: 创建人ID

        Returns:
            OutsourceOrderResponse: 创建的委外单信息

        Raises:
            ValidationError: 数据验证失败
            NotFoundError: 工单或工序不存在
        """
        async with in_transaction():
            # 验证工单是否存在
            work_order = await WorkOrder.filter(
                tenant_id=tenant_id,
                id=outsource_order_data.work_order_id,
                deleted_at__isnull=True
            ).first()
            
            if not work_order:
                raise NotFoundError(f"工单不存在: {outsource_order_data.work_order_id}")

            # 验证工单工序是否存在
            work_order_operation = await WorkOrderOperation.filter(
                tenant_id=tenant_id,
                id=outsource_order_data.work_order_operation_id,
                work_order_id=outsource_order_data.work_order_id,
                deleted_at__isnull=True
            ).first()
            
            if not work_order_operation:
                raise NotFoundError(f"工单工序不存在: {outsource_order_data.work_order_operation_id}")

            # 验证供应商是否存在
            supplier = await Supplier.filter(
                tenant_id=tenant_id,
                id=outsource_order_data.supplier_id,
                deleted_at__isnull=True,
                is_active=True
            ).first()
            
            if not supplier:
                raise NotFoundError(f"供应商不存在或已禁用: {outsource_order_data.supplier_id}")

            if outsource_order_data.outsource_quantity <= 0:
                raise ValidationError("委外数量必须大于 0")

            # 建草稿只卡计划(+超报)；上道转入在下达/收货时硬卡（允许提前备单）
            breakdown = await self._compute_outsourceable_breakdown(
                tenant_id,
                work_order,
                work_order_operation,
                apply_incoming_gate=False,
            )
            outsourceable_quantity = breakdown["outsourceable_quantity"]

            if outsource_order_data.outsource_quantity > outsourceable_quantity:
                raise ValidationError(
                    f"委外数量({outsource_order_data.outsource_quantity})不能超过可委外数量"
                    f"({outsourceable_quantity})"
                )

            # 生成委外单编码（如果未提供）
            if not outsource_order_data.code:
                today = today_site_str()
                code = await self.generate_code(
                    tenant_id=tenant_id,
                    code_type="OUTSOURCE_ORDER_CODE",
                    prefix=f"OS{today}"
                )
            else:
                code = outsource_order_data.code

            # 获取创建人信息
            user_info = await self.get_user_info(created_by)

            # 计算总金额
            total_amount = resolve_simple_line_total(
                outsource_order_data.outsource_quantity,
                outsource_order_data.unit_price or 0,
                outsource_order_data.total_amount,
            )

            from apps.kuaizhizao.services.document_recognition import ensure_payable_recognition_on_create

            payable_recognition = await ensure_payable_recognition_on_create(
                tenant_id,
                int(supplier.id),
                getattr(outsource_order_data, "payable_recognition", None),
            )

            # 创建委外单
            outsource_order = await OutsourceOrder.create(
                tenant_id=tenant_id,
                uuid=str(uuid.uuid4()),
                code=code,
                work_order_id=outsource_order_data.work_order_id,
                work_order_code=work_order.code,
                work_order_operation_id=outsource_order_data.work_order_operation_id,
                operation_id=outsource_order_data.operation_id,
                operation_code=outsource_order_data.operation_code,
                operation_name=outsource_order_data.operation_name,
                supplier_id=outsource_order_data.supplier_id,
                supplier_code=supplier.code,
                supplier_name=supplier.name,
                outsource_quantity=outsource_order_data.outsource_quantity,
                received_quantity=Decimal('0'),
                qualified_quantity=Decimal('0'),
                unqualified_quantity=Decimal('0'),
                unit_price=outsource_order_data.unit_price,
                total_amount=total_amount,
                planned_start_date=outsource_order_data.planned_start_date,
                planned_end_date=outsource_order_data.planned_end_date,
                payable_recognition=payable_recognition,
                status="draft",
                remarks=outsource_order_data.remarks,
                created_by=created_by,
                created_by_name=user_info["name"],
                updated_by=created_by,
                updated_by_name=user_info["name"]
            )

            # 建立工单→工序委外的 DocumentRelation（支持单据追溯）
            try:
                from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService
                from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate

                rel_svc = DocumentRelationNewService()
                await rel_svc.create_relation(
                    tenant_id=tenant_id,
                    relation_data=DocumentRelationCreate(
                        source_type="work_order",
                        source_id=outsource_order_data.work_order_id,
                        source_code=work_order.code,
                        source_name=work_order.name,
                        target_type="outsource_order",
                        target_id=outsource_order.id,
                        target_code=outsource_order.code,
                        target_name=outsource_order_data.operation_name,
                        relation_type="source",
                        relation_mode="push",
                        relation_desc="工单工序委外",
                    ),
                    created_by=created_by,
                )
            except BusinessLogicError:
                pass  # 关联已存在，忽略
            except Exception as e:
                logger.warning("建立工单→工序委外关联失败: %s", e)

            await self._apply_outsource_to_work_order_operation(
                work_order_operation,
                outsource_order=outsource_order,
                remarks=outsource_order_data.remarks,
            )

            logger.info(f"创建委外单成功: {code}, 工单: {work_order.code}, 工序: {outsource_order_data.operation_name}")
            return OutsourceOrderResponse.model_validate(outsource_order)

    async def _apply_outsource_to_work_order_operation(
        self,
        work_order_operation: WorkOrderOperation,
        *,
        outsource_order: OutsourceOrder,
        remarks: Optional[str] = None,
    ) -> None:
        """创建委外单后：落章委外类型、清空本厂派工、同步计划窗。"""
        from apps.kuaizhizao.utils.outsource_operation import (
            OUTSOURCE_KIND_AD_HOC,
            OUTSOURCE_KIND_NONE,
            OUTSOURCE_KIND_PLANNED,
            normalize_outsource_kind,
        )

        kind = normalize_outsource_kind(getattr(work_order_operation, "outsource_kind", None))
        # 下达自动创建的计划委外保持 planned；其余视为临时委外
        auto_planned = bool(remarks and "计划工序委外" in str(remarks))
        if kind == OUTSOURCE_KIND_NONE and not auto_planned:
            work_order_operation.outsource_kind = OUTSOURCE_KIND_AD_HOC
        elif kind == OUTSOURCE_KIND_NONE and auto_planned:
            work_order_operation.outsource_kind = OUTSOURCE_KIND_PLANNED

        work_order_operation.assigned_station_id = None
        work_order_operation.assigned_station_name = None
        work_order_operation.assigned_worker_id = None
        work_order_operation.assigned_worker_name = None
        work_order_operation.assigned_worker_ids = []
        work_order_operation.assigned_team_id = None
        work_order_operation.assigned_team_name = None
        work_order_operation.assigned_equipment_id = None
        work_order_operation.assigned_equipment_name = None
        work_order_operation.assigned_mold_id = None
        work_order_operation.assigned_mold_name = None
        work_order_operation.assigned_tool_id = None
        work_order_operation.assigned_tool_name = None

        if outsource_order.planned_start_date:
            work_order_operation.planned_start_date = outsource_order.planned_start_date
        if outsource_order.planned_end_date:
            work_order_operation.planned_end_date = outsource_order.planned_end_date
        if not work_order_operation.default_outsource_supplier_id and outsource_order.supplier_id:
            work_order_operation.default_outsource_supplier_id = outsource_order.supplier_id
            work_order_operation.default_outsource_supplier_name = outsource_order.supplier_name

        await work_order_operation.save()

    async def _restore_work_order_operation_after_outsource_cancel(
        self,
        tenant_id: int,
        work_order_operation_id: int,
    ) -> None:
        """取消委外单后：若无其它有效委外单则恢复工序委外状态。"""
        from apps.kuaizhizao.utils.outsource_operation import (
            OUTSOURCE_KIND_AD_HOC,
            OUTSOURCE_KIND_NONE,
            OUTSOURCE_KIND_PLANNED,
            normalize_outsource_kind,
        )

        op = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id=work_order_operation_id,
            deleted_at__isnull=True,
        ).first()
        if not op:
            return
        still_active = await OutsourceOrder.filter(
            tenant_id=tenant_id,
            work_order_operation_id=work_order_operation_id,
            deleted_at__isnull=True,
        ).exclude(status="cancelled").exists()
        if still_active:
            await self._sync_work_order_operation_from_outsource_receipts(
                tenant_id, work_order_operation_id
            )
            return
        kind = normalize_outsource_kind(getattr(op, "outsource_kind", None))
        if kind == OUTSOURCE_KIND_AD_HOC:
            # 临时委外取消：若仍有提前期+默认供应商（曾是计划）则恢复 planned
            if op.outsource_lead_time_days is not None and op.default_outsource_supplier_id:
                op.outsource_kind = OUTSOURCE_KIND_PLANNED
            else:
                op.outsource_kind = OUTSOURCE_KIND_NONE
            await op.save(update_fields=["outsource_kind", "updated_at"])
        elif kind == OUTSOURCE_KIND_PLANNED:
            # 计划委外单取消后仍保持 planned（可再次下达补建草稿）
            pass
        await self._sync_work_order_operation_from_outsource_receipts(
            tenant_id, work_order_operation_id
        )

    async def create_outsource_order_from_work_order(
        self,
        tenant_id: int,
        work_order_id: int,
        work_order_operation_id: int,
        supplier_id: int,
        outsource_quantity: Decimal,
        created_by: int,
        unit_price: Optional[Decimal] = None,
        planned_start_date: Optional[datetime] = None,
        planned_end_date: Optional[datetime] = None,
        remarks: Optional[str] = None,
        payable_recognition: Optional[str] = None,
    ) -> OutsourceOrderResponse:
        """
        从工单工序创建委外单

        这是从工单详情页创建委外单的便捷方法。

        Args:
            tenant_id: 组织ID
            work_order_id: 工单ID
            work_order_operation_id: 工单工序ID
            supplier_id: 供应商ID
            outsource_quantity: 委外数量
            unit_price: 单价（可选）
            planned_start_date: 计划开始日期（可选）
            planned_end_date: 计划结束日期（可选）
            remarks: 备注（可选）
            created_by: 创建人ID

        Returns:
            OutsourceOrderResponse: 创建的委外单信息
        """
        # 获取工单信息
        work_order = await WorkOrder.filter(
            tenant_id=tenant_id,
            id=work_order_id,
            deleted_at__isnull=True
        ).first()
        
        if not work_order:
            raise NotFoundError(f"工单不存在: {work_order_id}")

        # 获取工单工序信息
        work_order_operation = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id=work_order_operation_id,
            work_order_id=work_order_id,
            deleted_at__isnull=True
        ).first()
        
        if not work_order_operation:
            raise NotFoundError(f"工单工序不存在: {work_order_operation_id}")

        # 获取供应商信息
        supplier = await Supplier.filter(
            tenant_id=tenant_id,
            id=supplier_id,
            deleted_at__isnull=True,
            is_active=True
        ).first()
        
        if not supplier:
            raise NotFoundError(f"供应商不存在或已禁用: {supplier_id}")

        # 构建创建数据
        create_data = OutsourceOrderCreate(
            work_order_id=work_order_id,
            work_order_code=work_order.code,
            work_order_operation_id=work_order_operation_id,
            operation_id=work_order_operation.operation_id,
            operation_code=work_order_operation.operation_code,
            operation_name=work_order_operation.operation_name,
            supplier_id=supplier_id,
            supplier_code=supplier.code,
            supplier_name=supplier.name,
            outsource_quantity=outsource_quantity,
            unit_price=unit_price,
            planned_start_date=planned_start_date or work_order_operation.planned_start_date,
            planned_end_date=planned_end_date or work_order_operation.planned_end_date,
            remarks=remarks,
            payable_recognition=payable_recognition,
        )

        return await self.create_outsource_order(
            tenant_id=tenant_id,
            outsource_order_data=create_data,
            created_by=created_by
        )

    async def get_outsource_order_by_id(
        self,
        tenant_id: int,
        outsource_order_id: int
    ) -> OutsourceOrderResponse:
        """
        根据ID获取委外单

        Args:
            tenant_id: 组织ID
            outsource_order_id: 委外单ID

        Returns:
            OutsourceOrderResponse: 委外单信息

        Raises:
            NotFoundError: 委外单不存在
        """
        outsource_order = await OutsourceOrder.filter(
            tenant_id=tenant_id,
            id=outsource_order_id,
            deleted_at__isnull=True
        ).first()

        if not outsource_order:
            raise NotFoundError(f"委外单不存在: {outsource_order_id}")

        from apps.kuaizhizao.services.document_lifecycle_service import get_outsource_order_lifecycle

        from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt
        from apps.kuaizhizao.services.document_action_policy.outsource_order import (
            derive_outsource_order_push_issue_cap,
        )

        batches = await OutsourceOrderReceipt.filter(
            tenant_id=tenant_id,
            outsource_order_id=int(outsource_order.id),
            deleted_at__isnull=True,
        ).order_by("id").all()
        payload = OutsourceOrderResponse.model_validate(outsource_order).model_dump()
        payload["lifecycle"] = get_outsource_order_lifecycle(outsource_order)
        payload["capabilities"] = {
            "push_outsource_issue": derive_outsource_order_push_issue_cap(outsource_order).model_dump(),
        }
        payload["receipt_batches"] = [
            {
                "id": b.id,
                "received_quantity": b.received_quantity,
                "qualified_quantity": b.qualified_quantity,
                "unqualified_quantity": b.unqualified_quantity,
                "created_at": b.created_at,
                "created_by_name": b.created_by_name,
            }
            for b in batches
        ]
        from apps.kuaizhizao.services.outsource_order_batch_quantity import (
            compute_issued_batch_quantity,
            resolve_outsource_suggested_receipt_quantity,
        )

        work_order = await WorkOrder.filter(
            tenant_id=tenant_id,
            id=int(outsource_order.work_order_id),
            deleted_at__isnull=True,
        ).first()
        work_order_operation = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id=int(outsource_order.work_order_operation_id),
            deleted_at__isnull=True,
        ).first()
        payload["issued_batch_quantity"] = await compute_issued_batch_quantity(
            tenant_id,
            outsource_order,
            work_order=work_order,
        )
        payload["suggested_receipt_quantity"] = await resolve_outsource_suggested_receipt_quantity(
            tenant_id,
            outsource_order,
            work_order=work_order,
            work_order_operation=work_order_operation,
        )
        return OutsourceOrderResponse.model_validate(payload)

    async def list_outsource_orders(
        self,
        tenant_id: int,
        current_user: Optional[User] = None,
        skip: int = 0,
        limit: int = 100,
        work_order_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        status: Optional[str] = None,
        code: Optional[str] = None,
        work_order_code: Optional[str] = None,
        operation_name: Optional[str] = None,
        supplier_name: Optional[str] = None,
        keyword: Optional[str] = None,
        planned_start_from: Optional[date] = None,
        planned_start_to: Optional[date] = None,
        created_start_date: Optional[date] = None,
        created_end_date: Optional[date] = None,
        order_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询委外单列表

        Args:
            tenant_id: 组织ID
            skip: 跳过数量
            limit: 返回数量
            work_order_id: 工单ID（可选筛选）
            supplier_id: 供应商ID（可选筛选）
            status: 状态（可选筛选）
            code: 委外单编码（可选筛选，模糊匹配）

        Returns:
            List[OutsourceOrderListResponse]: 委外单列表
        """
        query = OutsourceOrder.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True
        )
        from apps.kuaizhizao.services.kuaizhizao_data_scope import apply_kuaizhizao_list_scope

        query = await apply_kuaizhizao_list_scope(
            query,
            tenant_id=tenant_id,
            current_user=current_user,
            resource="kuaizhizao:outsource-order",
        )

        # 添加筛选条件
        if work_order_id:
            query = query.filter(work_order_id=work_order_id)
        if supplier_id:
            query = query.filter(supplier_id=supplier_id)
        if status:
            query = query.filter(status=status)
        c = (code or "").strip()
        if c:
            query = query.filter(code__icontains=c)
        kw = (keyword or "").strip()
        if kw:
            query = query.filter(
                Q(code__icontains=kw)
                | Q(work_order_code__icontains=kw)
                | Q(operation_name__icontains=kw)
                | Q(supplier_name__icontains=kw)
            )
        woc = (work_order_code or "").strip()
        if woc:
            query = query.filter(work_order_code__icontains=woc)
        on = (operation_name or "").strip()
        if on:
            query = query.filter(operation_name__icontains=on)
        sn = (supplier_name or "").strip()
        if sn:
            query = query.filter(supplier_name__icontains=sn)
        if planned_start_from is not None:
            query = query.filter(planned_start_date__gte=planned_start_from)
        if planned_start_to is not None:
            query = query.filter(planned_start_date__lte=planned_start_to)
        if created_start_date is not None:
            query = query.filter(created_at__gte=datetime.combine(created_start_date, time.min))
        if created_end_date is not None:
            query = query.filter(created_at__lte=datetime.combine(created_end_date, time.max))

        total = await query.count()
        order_clause = order_by if order_by else "-created_at"
        outsource_orders = await query.offset(skip).limit(limit).order_by(order_clause).all()

        from apps.kuaizhizao.services.document_lifecycle_service import get_outsource_order_lifecycle

        from apps.kuaizhizao.services.document_action_policy.outsource_order import (
            derive_outsource_order_push_issue_cap,
        )

        wo_ids = list({int(r.work_order_id) for r in outsource_orders if r.work_order_id})
        wo_rows = await WorkOrder.filter(
            tenant_id=tenant_id,
            id__in=wo_ids,
            deleted_at__isnull=True,
        ).all() if wo_ids else []
        work_orders_by_id = {int(w.id): w for w in wo_rows}

        op_ids = list({int(r.work_order_operation_id) for r in outsource_orders if r.work_order_operation_id})
        op_rows = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id__in=op_ids,
            deleted_at__isnull=True,
        ).all() if op_ids else []
        ops_by_id = {int(o.id): o for o in op_rows}

        from apps.kuaizhizao.services.outsource_order_batch_quantity import (
            batch_compute_issued_batch_quantities,
            resolve_outsource_suggested_receipt_quantity,
        )

        issued_batch_by_order = await batch_compute_issued_batch_quantities(
            tenant_id, outsource_orders, work_orders_by_id
        )

        rows: list[dict] = []
        for row in outsource_orders:
            item = OutsourceOrderListResponse.model_validate(row).model_dump()
            item["lifecycle"] = get_outsource_order_lifecycle(row)
            item["capabilities"] = {
                "push_outsource_issue": derive_outsource_order_push_issue_cap(row).model_dump(),
            }
            oid = int(row.id)
            item["issued_batch_quantity"] = issued_batch_by_order.get(oid, Decimal("0"))
            wo = work_orders_by_id.get(int(row.work_order_id))
            op = ops_by_id.get(int(row.work_order_operation_id))
            if wo and op:
                item["suggested_receipt_quantity"] = await resolve_outsource_suggested_receipt_quantity(
                    tenant_id,
                    row,
                    work_order=wo,
                    work_order_operation=op,
                )
            rows.append(item)
        return {
            "data": rows,
            "total": total,
            "success": True,
        }

    async def update_outsource_order(
        self,
        tenant_id: int,
        outsource_order_id: int,
        outsource_order_data: OutsourceOrderUpdate,
        updated_by: int
    ) -> OutsourceOrderResponse:
        """
        更新委外单

        Args:
            tenant_id: 组织ID
            outsource_order_id: 委外单ID
            outsource_order_data: 委外单更新数据
            updated_by: 更新人ID

        Returns:
            OutsourceOrderResponse: 更新后的委外单信息

        Raises:
            NotFoundError: 委外单不存在
            ValidationError: 数据验证失败
        """
        async with in_transaction():
            outsource_order = await OutsourceOrder.filter(
                tenant_id=tenant_id,
                id=outsource_order_id,
                deleted_at__isnull=True
            ).first()

            if not outsource_order:
                raise NotFoundError(f"委外单不存在: {outsource_order_id}")

            # 如果状态为completed或cancelled，不允许更新
            if outsource_order.status in ['completed', 'cancelled']:
                raise BusinessLogicError(f"委外单状态为 {outsource_order.status}，不允许更新")
            if outsource_order.status != "draft":
                raise BusinessLogicError("仅草稿可编辑；已下达请使用撤回下达，执行中请使用登记收货或完成")

            # 获取更新人信息
            user_info = await self.get_user_info(updated_by)

            # 更新字段
            update_dict = outsource_order_data.model_dump(exclude_unset=True, exclude_none=True)
            if "status" in update_dict and update_dict["status"] != "draft":
                raise BusinessLogicError("状态须通过下达、撤回下达、开始执行、登记收货或完成变更")
            update_dict.pop("status", None)

            # 如果更新了单价或数量，重新计算总金额
            if 'unit_price' in update_dict or 'outsource_quantity' in update_dict:
                unit_price = update_dict.get('unit_price', outsource_order.unit_price)
                outsource_quantity = update_dict.get('outsource_quantity', outsource_order.outsource_quantity)
                if unit_price:
                    update_dict['total_amount'] = line_total_qty_unit_price(
                        outsource_quantity, unit_price
                    )

            # 如果更新了供应商信息，需要验证供应商是否存在
            if 'supplier_id' in update_dict:
                supplier = await Supplier.filter(
                    tenant_id=tenant_id,
                    id=update_dict['supplier_id'],
                    deleted_at__isnull=True,
                    is_active=True
                ).first()
                
                if not supplier:
                    raise NotFoundError(f"供应商不存在或已禁用: {update_dict['supplier_id']}")
                
                update_dict['supplier_code'] = supplier.code
                update_dict['supplier_name'] = supplier.name

            prev_status = outsource_order.status
            # 更新字段
            for key, value in update_dict.items():
                setattr(outsource_order, key, value)

            outsource_order.updated_by = updated_by
            outsource_order.updated_by_name = user_info["name"]
            await outsource_order.save()

            if (
                update_dict.get("status") == "cancelled"
                and prev_status != "cancelled"
                and outsource_order.work_order_operation_id
            ):
                await self._restore_work_order_operation_after_outsource_cancel(
                    tenant_id,
                    int(outsource_order.work_order_operation_id),
                )

            logger.info(f"更新委外单成功: {outsource_order.code}")
            return OutsourceOrderResponse.model_validate(outsource_order)

    async def delete_outsource_order(
        self,
        tenant_id: int,
        outsource_order_id: int,
        deleted_by: int
    ) -> None:
        """
        删除委外单（软删除）

        Args:
            tenant_id: 组织ID
            outsource_order_id: 委外单ID
            deleted_by: 删除人ID

        Raises:
            NotFoundError: 委外单不存在
            BusinessLogicError: 委外单状态不允许删除
        """
        async with in_transaction():
            outsource_order = await OutsourceOrder.filter(
                tenant_id=tenant_id,
                id=outsource_order_id,
                deleted_at__isnull=True
            ).first()

            if not outsource_order:
                raise NotFoundError(f"委外单不存在: {outsource_order_id}")

            if outsource_order.status != "draft":
                raise BusinessLogicError("仅草稿可删除；已下达请使用撤回下达回到草稿后再删")

            # 获取删除人信息
            user_info = await self.get_user_info(deleted_by)

            # 软删除
            outsource_order.deleted_at = resolve_business_datetime()
            outsource_order.updated_by = deleted_by
            outsource_order.updated_by_name = user_info["name"]
            await outsource_order.save()

            logger.info(f"删除委外单成功: {outsource_order.code}")

    async def _get_outsource_order_row(
        self,
        tenant_id: int,
        outsource_order_id: int,
    ) -> OutsourceOrder:
        row = await OutsourceOrder.filter(
            tenant_id=tenant_id,
            id=outsource_order_id,
            deleted_at__isnull=True,
        ).first()
        if not row:
            raise NotFoundError(f"委外单不存在: {outsource_order_id}")
        return row

    @staticmethod
    def _validate_outsource_receipt_quantities(
        *,
        outsource_quantity: Decimal,
        received_quantity: Decimal,
        qualified_quantity: Decimal,
        unqualified_quantity: Decimal,
    ) -> None:
        if received_quantity < 0 or qualified_quantity < 0 or unqualified_quantity < 0:
            raise ValidationError("收货数量不能为负数")
        if received_quantity > outsource_quantity:
            raise BusinessLogicError(
                f"已接收数量({received_quantity})不能超过委外数量({outsource_quantity})"
            )
        if qualified_quantity + unqualified_quantity != received_quantity:
            raise BusinessLogicError("合格数量与不合格数量之和须等于已接收数量")

    async def _assert_outsource_order_within_executable_flow(
        self,
        tenant_id: int,
        row: OutsourceOrder,
    ) -> None:
        """下达/开始执行：委外数量不可超过上道转入与计划共同约束的可执行量。"""
        work_order = await WorkOrder.filter(
            tenant_id=tenant_id,
            id=int(row.work_order_id),
            deleted_at__isnull=True,
        ).first()
        op = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id=int(row.work_order_operation_id),
            deleted_at__isnull=True,
        ).first()
        if not work_order or not op:
            raise NotFoundError("委外单关联的工单或工序不存在")
        from apps.kuaizhizao.services.operation_jump_rules import (
            assert_previous_nodes_have_qualified_output,
        )

        await assert_previous_nodes_have_qualified_output(tenant_id, work_order, op)
        breakdown = await self._compute_outsourceable_breakdown(
            tenant_id,
            work_order,
            op,
            exclude_outsource_order_id=int(row.id),
            apply_incoming_gate=True,
        )
        out_qty = Decimal(str(row.outsource_quantity or 0))
        executable = breakdown["outsourceable_quantity"]
        if out_qty > executable:
            incoming = breakdown["incoming_quantity"]
            raise BusinessLogicError(
                f"工序流转门禁：委外数量({out_qty})超过当前可执行量({executable})"
                f"（上道转入 {incoming}，已占用见可委外量）"
            )

    async def release_outsource_order(
        self,
        tenant_id: int,
        outsource_order_id: int,
        updated_by: int,
    ) -> OutsourceOrderResponse:
        async with in_transaction():
            row = await self._get_outsource_order_row(tenant_id, outsource_order_id)
            if row.status != "draft":
                raise BusinessLogicError(f"当前状态为 {row.status}，仅草稿可下达")
            await self._assert_outsource_order_within_executable_flow(tenant_id, row)
            user_info = await self.get_user_info(updated_by)
            row.status = "released"
            row.updated_by = updated_by
            row.updated_by_name = user_info["name"]
            await row.save()
        return await self.get_outsource_order_by_id(tenant_id, outsource_order_id)

    @staticmethod
    def can_revoke_outsource_order_release(record: OutsourceOrder) -> bool:
        if str(getattr(record, "status", "") or "").strip() != "released":
            return False
        if getattr(record, "purchase_receipt_id", None):
            return False
        recv = Decimal(str(getattr(record, "received_quantity", 0) or 0))
        if recv > 0:
            return False
        if getattr(record, "actual_start_date", None):
            return False
        return True

    async def revoke_outsource_order_release(
        self,
        tenant_id: int,
        outsource_order_id: int,
        updated_by: int,
    ) -> OutsourceOrderResponse:
        async with in_transaction():
            row = await self._get_outsource_order_row(tenant_id, outsource_order_id)
            if not self.can_revoke_outsource_order_release(row):
                raise BusinessLogicError("当前不可撤回下达（须为已下达且未入库、未收货、未开始执行）")
            user_info = await self.get_user_info(updated_by)
            row.status = "draft"
            row.updated_by = updated_by
            row.updated_by_name = user_info["name"]
            await row.save()
        return await self.get_outsource_order_by_id(tenant_id, outsource_order_id)

    async def start_outsource_order(
        self,
        tenant_id: int,
        outsource_order_id: int,
        updated_by: int,
    ) -> OutsourceOrderResponse:
        raise BusinessLogicError("请通过「工序发料」完成发料后自动开工，不可直接开始执行")

    async def _sync_work_order_operation_from_outsource_receipts(
        self,
        tenant_id: int,
        work_order_operation_id: int,
        *,
        now: Optional[datetime] = None,
    ) -> None:
        """委外收货真源回写工序完成量，供下道转入使用。"""
        op = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id=int(work_order_operation_id),
            deleted_at__isnull=True,
        ).first()
        if not op:
            return
        orders = await OutsourceOrder.filter(
            tenant_id=tenant_id,
            work_order_operation_id=int(work_order_operation_id),
            deleted_at__isnull=True,
        ).exclude(status="cancelled").all()
        total_recv = Decimal("0")
        total_qual = Decimal("0")
        total_unqual = Decimal("0")
        for o in orders:
            total_recv += Decimal(str(o.received_quantity or 0))
            total_qual += Decimal(str(o.qualified_quantity or 0))
            total_unqual += Decimal(str(o.unqualified_quantity or 0))
        op.completed_quantity = total_recv
        op.qualified_quantity = total_qual
        op.unqualified_quantity = total_unqual
        stamp = now or resolve_business_datetime()
        if total_recv > 0 and not op.actual_start_date:
            op.actual_start_date = stamp
        if total_recv > 0 and str(op.status or "").strip() in ("pending", "assigned", ""):
            op.status = "in_progress"
        # 本道委外单均已完成且累计接收达到各单委外量时，工序可结为 completed
        active = [o for o in orders if str(o.status or "").strip() != "cancelled"]
        if active and all(str(o.status or "").strip() == "completed" for o in active):
            planned = sum((Decimal(str(o.outsource_quantity or 0)) for o in active), Decimal("0"))
            if planned > 0 and total_recv >= planned:
                op.status = "completed"
                if not op.actual_end_date:
                    op.actual_end_date = stamp
        await op.save()

    async def _assert_outsource_receipt_within_incoming(
        self,
        tenant_id: int,
        row: OutsourceOrder,
        *,
        received_quantity: Decimal,
    ) -> None:
        """登记收货后本道累计完成不可超过上道转入（与报工门禁一致）。"""
        work_order = await WorkOrder.filter(
            tenant_id=tenant_id,
            id=int(row.work_order_id),
            deleted_at__isnull=True,
        ).first()
        op = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id=int(row.work_order_operation_id),
            deleted_at__isnull=True,
        ).first()
        if not work_order or not op:
            return
        # 与报工同一套关闸转入（含跳过 allow_jump=True 的前序）
        caps = await self._resolve_operation_flow_caps(tenant_id, work_order, op)
        incoming = caps["incoming_quantity"]
        siblings = await OutsourceOrder.filter(
            tenant_id=tenant_id,
            work_order_operation_id=int(row.work_order_operation_id),
            deleted_at__isnull=True,
        ).exclude(status="cancelled").all()
        total_recv = Decimal("0")
        for o in siblings:
            if int(o.id) == int(row.id):
                total_recv += received_quantity
            else:
                total_recv += Decimal(str(o.received_quantity or 0))
        if total_recv > incoming:
            raise BusinessLogicError(
                f"工序流转门禁：本道累计接收数量（{total_recv}）不能超过上道转入数量（{incoming}）"
            )

    async def register_outsource_order_receipt(
        self,
        tenant_id: int,
        outsource_order_id: int,
        receipt_data: OutsourceOrderRegisterReceipt,
        updated_by: int,
    ) -> OutsourceOrderResponse:
        from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt
        from apps.kuaizhizao.services.outsource_order_receipt_finance import (
            maybe_auto_payable_for_outsource_order_receipt_batch,
        )

        batch_id: Optional[int] = None
        async with in_transaction():
            row = await self._get_outsource_order_row(tenant_id, outsource_order_id)
            if row.status not in ("released", "in_progress"):
                raise BusinessLogicError(f"当前状态为 {row.status}，无法登记收货")
            out_qty = Decimal(str(row.outsource_quantity or 0))
            batch_recv = Decimal(str(receipt_data.received_quantity))
            batch_qual = Decimal(str(receipt_data.qualified_quantity))
            if batch_recv <= 0:
                raise ValidationError("本批接收数量必须大于 0")
            if batch_qual < 0 or batch_qual > batch_recv:
                raise ValidationError("合格数量须在 0 与本批接收数量之间")
            batch_unqual = batch_recv - batch_qual
            expected_unqual = Decimal(str(receipt_data.unqualified_quantity))
            if expected_unqual != batch_unqual:
                raise ValidationError("不合格数量须等于本批接收数量减合格数量")
            new_recv = Decimal(str(row.received_quantity or 0)) + batch_recv
            new_qual = Decimal(str(row.qualified_quantity or 0)) + batch_qual
            new_unqual = Decimal(str(row.unqualified_quantity or 0)) + batch_unqual
            if new_recv > out_qty:
                raise BusinessLogicError(
                    f"累计接收数量（{new_recv}）不能超过委外数量（{out_qty}）"
                )
            await self._assert_outsource_receipt_within_incoming(
                tenant_id,
                row,
                received_quantity=new_recv,
            )
            user_info = await self.get_user_info(updated_by)
            now = resolve_business_datetime()
            batch_row = await OutsourceOrderReceipt.create(
                tenant_id=tenant_id,
                uuid=str(uuid.uuid4()),
                outsource_order_id=int(row.id),
                outsource_order_code=str(row.code or ""),
                received_quantity=batch_recv,
                qualified_quantity=batch_qual,
                unqualified_quantity=batch_unqual,
                payable_recognition=str(row.payable_recognition or ""),
                created_by=updated_by,
                created_by_name=user_info["name"],
            )
            batch_id = int(batch_row.id)
            row.received_quantity = new_recv
            row.qualified_quantity = new_qual
            row.unqualified_quantity = new_unqual
            if row.status == "released":
                row.status = "in_progress"
                if not row.actual_start_date:
                    row.actual_start_date = now
            row.updated_by = updated_by
            row.updated_by_name = user_info["name"]
            await row.save()
            if row.work_order_operation_id:
                await self._sync_work_order_operation_from_outsource_receipts(
                    tenant_id,
                    int(row.work_order_operation_id),
                    now=now,
                )
        if batch_id:
            await maybe_auto_payable_for_outsource_order_receipt_batch(
                tenant_id=tenant_id,
                outsource_order_id=outsource_order_id,
                batch_id=batch_id,
                created_by=updated_by,
            )
        return await self.get_outsource_order_by_id(tenant_id, outsource_order_id)

    async def complete_outsource_order(
        self,
        tenant_id: int,
        outsource_order_id: int,
        updated_by: int,
    ) -> OutsourceOrderResponse:
        async with in_transaction():
            row = await self._get_outsource_order_row(tenant_id, outsource_order_id)
            if row.status != "in_progress":
                raise BusinessLogicError(f"当前状态为 {row.status}，仅执行中可完成")
            out_qty = Decimal(str(row.outsource_quantity or 0))
            recv = Decimal(str(row.received_quantity or 0))
            if out_qty <= 0:
                raise BusinessLogicError("委外数量无效，无法完成")
            if recv < out_qty:
                raise BusinessLogicError(
                    f"已接收数量({recv})未达到委外数量({out_qty})，请先登记收货"
                )
            user_info = await self.get_user_info(updated_by)
            now = resolve_business_datetime()
            row.status = "completed"
            row.actual_end_date = now
            row.updated_by = updated_by
            row.updated_by_name = user_info["name"]
            await row.save()
            if row.work_order_operation_id:
                await self._sync_work_order_operation_from_outsource_receipts(
                    tenant_id,
                    int(row.work_order_operation_id),
                    now=now,
                )
        return await self.get_outsource_order_by_id(tenant_id, outsource_order_id)

    async def link_purchase_receipt(
        self,
        tenant_id: int,
        outsource_order_id: int,
        purchase_receipt_id: int,
        updated_by: int
    ) -> OutsourceOrderResponse:
        """
        关联采购入库单（委外入库）

        Args:
            tenant_id: 组织ID
            outsource_order_id: 委外单ID
            purchase_receipt_id: 采购入库单ID
            updated_by: 更新人ID

        Returns:
            OutsourceOrderResponse: 更新后的委外单信息

        Raises:
            NotFoundError: 委外单或采购入库单不存在
            BusinessLogicError: 业务逻辑错误
        """
        async with in_transaction():
            outsource_order = await OutsourceOrder.filter(
                tenant_id=tenant_id,
                id=outsource_order_id,
                deleted_at__isnull=True
            ).first()

            if not outsource_order:
                raise NotFoundError(f"委外单不存在: {outsource_order_id}")

            purchase_receipt = await PurchaseReceipt.filter(
                tenant_id=tenant_id,
                id=purchase_receipt_id,
                deleted_at__isnull=True
            ).first()

            if not purchase_receipt:
                raise NotFoundError(f"采购入库单不存在: {purchase_receipt_id}")

            # 验证供应商是否匹配
            if purchase_receipt.supplier_id != outsource_order.supplier_id:
                raise BusinessLogicError(f"采购入库单的供应商({purchase_receipt.supplier_name})与委外单的供应商({outsource_order.supplier_name})不匹配")

            # 获取更新人信息
            user_info = await self.get_user_info(updated_by)

            # 关联采购入库单
            outsource_order.purchase_receipt_id = purchase_receipt_id
            outsource_order.purchase_receipt_code = purchase_receipt.receipt_code
            outsource_order.updated_by = updated_by
            outsource_order.updated_by_name = user_info["name"]
            await outsource_order.save()

            logger.info(f"委外单 {outsource_order.code} 关联采购入库单 {purchase_receipt.receipt_code} 成功")
        return await self.get_outsource_order_by_id(tenant_id, outsource_order_id)

