"""工序委外：发料预览与确认后开工。"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from tortoise.transactions import in_transaction

from apps.kuaizhizao.models.outsource_order import OutsourceOrder
from apps.kuaizhizao.models.outsource_work_order import OutsourceMaterialIssue
from apps.kuaizhizao.models.work_order import WorkOrder
from apps.kuaizhizao.models.work_order_operation import WorkOrderOperation
from apps.kuaizhizao.schemas.outsource_work_order import (
    OutsourceMaterialIssueBatchCreate,
    OutsourceMaterialIssueBatchResponse,
    OutsourceMaterialIssuePreviewLine,
    OutsourceMaterialIssuePreviewResponse,
)
from apps.kuaizhizao.services.document_action_policy.outsource_order import assert_outsource_order_push_issue
from apps.kuaizhizao.services.outsource_material_issue_service import OutsourceMaterialIssueService
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError


class OutsourceOrderIssueBridge:
    async def get_issue_preview(
        self,
        tenant_id: int,
        outsource_order_id: int,
    ) -> OutsourceMaterialIssuePreviewResponse:
        from apps.kuaizhizao.utils.bom_helper import calculate_material_requirements_from_bom
        from apps.kuaizhizao.utils.inventory_helper import batch_get_material_inventory

        oo = await OutsourceOrder.filter(
            tenant_id=tenant_id,
            id=outsource_order_id,
            deleted_at__isnull=True,
        ).first()
        if not oo:
            raise NotFoundError(f"工序委外单不存在: {outsource_order_id}")
        assert_outsource_order_push_issue(oo)

        work_order = await WorkOrder.filter(
            tenant_id=tenant_id,
            id=int(oo.work_order_id),
            deleted_at__isnull=True,
        ).first()
        if not work_order or not work_order.product_id:
            raise BusinessLogicError("工单或产品不存在，无法生成发料预览")

        issue_svc = OutsourceMaterialIssueService()
        scale_qty = float(oo.outsource_quantity or 0)
        if scale_qty <= 0:
            raise ValidationError("委外数量无效")

        message: Optional[str] = None
        try:
            reqs = await calculate_material_requirements_from_bom(
                tenant_id=tenant_id,
                material_id=int(work_order.product_id),
                required_quantity=scale_qty,
                only_approved=True,
                for_kitting_analysis=True,
            )
        except NotFoundError:
            reqs = []
            message = "未找到已审核的产品 BOM，可在发料页手动选择物料"

        issue_reqs = [
            r for r in reqs
            if issue_svc._should_issue_for_outsource(
                getattr(r, "issue_method", None),
                getattr(r, "component_type", None),
            )
        ]
        issued_map = await self._net_issued_by_material(tenant_id, outsource_order_id)
        mat_ids = [int(r.component_id) for r in issue_reqs]
        inv_map = await batch_get_material_inventory(tenant_id, mat_ids)

        lines: List[OutsourceMaterialIssuePreviewLine] = []
        for r in issue_reqs:
            mid = int(r.component_id)
            required = Decimal(str(r.net_requirement or r.gross_requirement or 0))
            issued = issued_map.get(mid, Decimal("0"))
            pending = max(Decimal("0"), required - issued)
            inv_row = inv_map.get(mid) or {}
            available = Decimal(str(inv_row.get("available_quantity") or 0))
            lines.append(
                OutsourceMaterialIssuePreviewLine(
                    material_id=mid,
                    material_code=r.component_code or "",
                    material_name=r.component_name or "",
                    unit=r.unit or "",
                    required_quantity=required,
                    issued_quantity=issued,
                    pending_quantity=pending,
                    available_quantity=available,
                    issue_method=getattr(r, "issue_method", None) or "pick",
                )
            )

        if not lines and not message:
            message = "BOM 中无需要发料的子件，可在发料页手动选择物料"

        return OutsourceMaterialIssuePreviewResponse(
            outsource_order_id=int(oo.id),
            outsource_order_code=str(oo.code or ""),
            product_name=str(work_order.product_name or ""),
            supplier_code=str(oo.supplier_code or "") or None,
            supplier_name=str(oo.supplier_name or "") or None,
            planned_start_date=oo.planned_start_date,
            planned_end_date=oo.planned_end_date,
            quantity=Decimal(str(scale_qty)),
            lines=lines,
            message=message,
            allow_manual_lines=True,
        )

    async def create_issues_batch(
        self,
        tenant_id: int,
        outsource_order_id: int,
        batch: OutsourceMaterialIssueBatchCreate,
        created_by: int,
    ) -> OutsourceMaterialIssueBatchResponse:
        oo = await OutsourceOrder.filter(
            tenant_id=tenant_id,
            id=outsource_order_id,
            deleted_at__isnull=True,
        ).first()
        if not oo:
            raise NotFoundError(f"工序委外单不存在: {outsource_order_id}")
        assert_outsource_order_push_issue(oo)

        from apps.kuaizhizao.services.warehouse_wo_outsource_pull_service import (
            _resolve_material_warehouse,
        )

        issue_svc = OutsourceMaterialIssueService()
        created: List = []
        async with in_transaction():
            for line in batch.lines:
                from apps.kuaizhizao.schemas.outsource_work_order import OutsourceMaterialIssueCreate

                wh_id = line.warehouse_id or batch.warehouse_id
                wh_name = line.warehouse_name or batch.warehouse_name
                if not wh_id or int(wh_id) <= 0:
                    label = str(line.material_code or line.material_name or line.material_id)
                    wh_id, wh_name = await _resolve_material_warehouse(
                        tenant_id, int(line.material_id), label
                    )

                issue_data = OutsourceMaterialIssueCreate(
                    outsource_work_order_id=None,
                    outsource_work_order_code=None,
                    outsource_order_id=int(oo.id),
                    outsource_order_code=str(oo.code or ""),
                    material_id=line.material_id,
                    material_code=line.material_code,
                    material_name=line.material_name,
                    quantity=line.quantity,
                    unit=line.unit,
                    warehouse_id=int(wh_id),
                    warehouse_name=wh_name,
                    location_id=line.location_id,
                    location_name=line.location_name,
                    batch_number=line.batch_number,
                    serial_numbers=line.serial_numbers,
                    issued_at=batch.issued_at,
                    issued_by=batch.issued_by,
                    issued_by_name=batch.issued_by_name,
                    remarks=batch.remarks,
                )
                resp = await issue_svc.create_material_issue_for_outsource_order(
                    tenant_id=tenant_id,
                    issue_data=issue_data,
                    outsource_order=oo,
                    created_by=created_by,
                )
                created.append(resp)
            await self._apply_execution_start(tenant_id, oo, updated_by=created_by)
        return OutsourceMaterialIssueBatchResponse(created_count=len(created), issues=created)

    async def auto_issue_pending(
        self,
        tenant_id: int,
        outsource_order_id: int,
        created_by: int,
    ) -> OutsourceMaterialIssueBatchResponse:
        from apps.kuaizhizao.schemas.outsource_work_order import (
            OutsourceMaterialIssueLineCreate,
        )
        from apps.kuaizhizao.services.warehouse_wo_outsource_pull_service import (
            _resolve_material_warehouse,
        )

        preview = await self.get_issue_preview(tenant_id, outsource_order_id)
        batch_lines: List[OutsourceMaterialIssueLineCreate] = []
        for row in preview.lines or []:
            pending = Decimal(str(row.pending_quantity or 0))
            if pending <= 0:
                continue
            label = str(row.material_code or row.material_name or row.material_id)
            wh_id, wh_name = await _resolve_material_warehouse(tenant_id, int(row.material_id), label)
            batch_lines.append(
                OutsourceMaterialIssueLineCreate(
                    material_id=int(row.material_id),
                    material_code=str(row.material_code or ""),
                    material_name=str(row.material_name or ""),
                    quantity=pending,
                    unit=str(row.unit or "个"),
                    warehouse_id=wh_id,
                    warehouse_name=wh_name,
                )
            )
        if not batch_lines:
            raise BusinessLogicError("没有待发物料，无法工序发料")
        oo = await OutsourceOrder.filter(
            tenant_id=tenant_id,
            id=outsource_order_id,
            deleted_at__isnull=True,
        ).first()
        if not oo:
            raise NotFoundError(f"工序委外单不存在: {outsource_order_id}")
        batch = OutsourceMaterialIssueBatchCreate(
            outsource_order_id=int(oo.id),
            outsource_order_code=str(oo.code or ""),
            lines=batch_lines,
        )
        return await self.create_issues_batch(tenant_id, outsource_order_id, batch, created_by)

    async def _net_issued_by_material(
        self,
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
            net[mid] = net.get(mid, Decimal("0")) + Decimal(str(issue.quantity or 0))
        return net

    async def _apply_execution_start(
        self,
        tenant_id: int,
        oo: OutsourceOrder,
        *,
        updated_by: int,
    ) -> None:
        now = resolve_business_datetime()
        if str(oo.status or "").strip() == "released":
            oo.status = "in_progress"
            if not oo.actual_start_date:
                oo.actual_start_date = now
        elif not oo.actual_start_date:
            oo.actual_start_date = now
        oo.updated_by = updated_by
        await oo.save()

        op = await WorkOrderOperation.filter(
            tenant_id=tenant_id,
            id=int(oo.work_order_operation_id),
            deleted_at__isnull=True,
        ).first()
        if not op:
            return
        if not op.actual_start_date:
            op.actual_start_date = now
        st = str(op.status or "").strip().lower()
        if st in ("pending", "assigned", "", "待开始", "已派工"):
            op.status = "in_progress"
        await op.save()