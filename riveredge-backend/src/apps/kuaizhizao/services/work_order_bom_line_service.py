"""
工单子件明细：持久化、齐套/领料读侧。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from loguru import logger

from apps.kuaizhizao.models.work_order import WorkOrder
from apps.kuaizhizao.models.work_order_bom_line import WorkOrderBomLine
from apps.kuaizhizao.schemas.work_order import WorkOrderBomLineCreate, WorkOrderBomLineResponse
from apps.kuaizhizao.utils.bom_helper import calculate_material_requirements_from_bom
from apps.kuaizhizao.utils.picking_posting import sum_confirmed_picked_by_material
from core.utils.timezone_utils import now_utc


class WorkOrderBomLineService:
    async def list_lines(
        self, tenant_id: int, work_order_id: int, *, with_issued: bool = True
    ) -> List[WorkOrderBomLineResponse]:
        rows = await WorkOrderBomLine.filter(
            tenant_id=tenant_id,
            work_order_id=work_order_id,
            deleted_at__isnull=True,
        ).order_by("sequence", "id")
        picked: Dict[int, Decimal] = {}
        if with_issued and rows:
            picked = await sum_confirmed_picked_by_material(tenant_id, work_order_id)

        items: List[WorkOrderBomLineResponse] = []
        for row in rows:
            issued = picked.get(int(row.material_id), Decimal("0"))
            items.append(
                WorkOrderBomLineResponse.model_validate(row).model_copy(
                    update={"issued_quantity": issued}
                )
            )
        return items

    async def has_saved_lines(self, tenant_id: int, work_order_id: int) -> bool:
        return await WorkOrderBomLine.filter(
            tenant_id=tenant_id,
            work_order_id=work_order_id,
            deleted_at__isnull=True,
        ).exists()

    async def replace_lines(
        self,
        tenant_id: int,
        work_order_id: int,
        lines: Optional[Sequence[WorkOrderBomLineCreate]],
        *,
        created_by: int,
        created_by_name: str,
    ) -> None:
        if lines is None:
            return
        await WorkOrderBomLine.filter(
            tenant_id=tenant_id,
            work_order_id=work_order_id,
            deleted_at__isnull=True,
        ).update(deleted_at=now_utc())
        for idx, raw in enumerate(lines, 1):
            # update 路径常经 model_dump 得到 dict；create 路径为 Pydantic 模型
            line = (
                raw
                if isinstance(raw, WorkOrderBomLineCreate)
                else WorkOrderBomLineCreate.model_validate(raw)
            )
            seq = line.sequence if line.sequence else idx
            await WorkOrderBomLine.create(
                tenant_id=tenant_id,
                uuid=str(uuid4()),
                work_order_id=work_order_id,
                sequence=seq,
                material_id=line.material_id,
                material_code=line.material_code,
                material_name=line.material_name,
                material_spec=line.material_spec,
                warehouse_id=line.warehouse_id,
                warehouse_name=line.warehouse_name,
                unit=line.unit,
                required_quantity=line.required_quantity,
                batch_no=line.batch_no,
                bom_version=line.bom_version,
                line_remarks=line.line_remarks,
                created_by=created_by,
                created_by_name=created_by_name,
                updated_by=created_by,
                updated_by_name=created_by_name,
            )

    async def build_requirements_from_saved_lines(
        self, tenant_id: int, work_order: WorkOrder
    ) -> Optional[List[Any]]:
        """有已保存子件行时返回类 BOM 需求对象列表，否则 None。"""
        rows = await WorkOrderBomLine.filter(
            tenant_id=tenant_id,
            work_order_id=work_order.id,
            deleted_at__isnull=True,
        ).order_by("sequence", "id")
        if not rows:
            return None

        class _Req:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        reqs = []
        for row in rows:
            reqs.append(
                _Req(
                    component_id=int(row.material_id),
                    component_code=row.material_code,
                    component_name=row.material_name,
                    gross_requirement=float(row.required_quantity or 0),
                    net_requirement=float(row.required_quantity or 0),
                    warehouse_id=row.warehouse_id,
                    warehouse_name=row.warehouse_name,
                    issue_method=None,
                    component_type=None,
                    material_spec=row.material_spec,
                    bom_version=row.bom_version,
                    batch_no=row.batch_no,
                    unit=row.unit,
                )
            )
        return reqs

    async def expand_bom_lines_for_form(
        self,
        tenant_id: int,
        *,
        product_id: int,
        quantity: Decimal,
        product_bom_version: Optional[str],
        variant_attributes: Optional[dict],
        configurable_selections: Optional[dict],
        existing_lines: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> List[WorkOrderBomLineResponse]:
        """按 BOM 重算应发量，尽量保留用户改过的仓库/批号/备注。"""
        try:
            requirements = await calculate_material_requirements_from_bom(
                tenant_id=tenant_id,
                material_id=product_id,
                required_quantity=float(quantity),
                only_approved=True,
                bom_version=product_bom_version,
                use_default_bom=not bool(product_bom_version),
                variant_attributes=variant_attributes,
                configurable_selections=configurable_selections,
                for_kitting_analysis=True,
            )
        except Exception as exc:
            logger.warning("工单 BOM 展开失败 product=%s err=%s", product_id, exc)
            requirements = []

        by_mid: Dict[int, Dict[str, Any]] = {}
        if existing_lines:
            for ex in existing_lines:
                mid = int(ex.get("material_id") or 0)
                if mid > 0:
                    by_mid[mid] = ex

        out: List[WorkOrderBomLineResponse] = []
        for idx, req in enumerate(requirements or [], 1):
            mid = int(getattr(req, "component_id", 0) or 0)
            if mid <= 0:
                continue
            preserved = by_mid.get(mid) or {}
            gross = getattr(req, "gross_requirement", None) or getattr(req, "net_requirement", 0)
            out.append(
                WorkOrderBomLineResponse(
                    id=preserved.get("id"),
                    material_id=mid,
                    material_code=getattr(req, "component_code", None) or preserved.get("material_code", ""),
                    material_name=getattr(req, "component_name", None) or preserved.get("material_name", ""),
                    material_spec=getattr(req, "material_spec", None) or preserved.get("material_spec"),
                    warehouse_id=preserved.get("warehouse_id") or getattr(req, "warehouse_id", None),
                    warehouse_name=preserved.get("warehouse_name") or getattr(req, "warehouse_name", None),
                    unit=getattr(req, "unit", None) or preserved.get("unit"),
                    required_quantity=Decimal(str(gross or 0)),
                    batch_no=preserved.get("batch_no"),
                    bom_version=preserved.get("bom_version") or product_bom_version,
                    line_remarks=preserved.get("line_remarks"),
                    sequence=idx,
                    issued_quantity=Decimal("0"),
                    current_stock=None,
                )
            )
        return out