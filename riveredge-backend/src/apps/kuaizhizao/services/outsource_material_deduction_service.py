"""委外材料超耗扣款预览与校验。"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Sequence

from apps.kuaizhizao.models.outsource_work_order import (
    OutsourceMaterialIssue,
    OutsourceMaterialReturn,
    OutsourceWorkOrder,
)
from apps.kuaizhizao.utils.bom_helper import (
    bom_item_base_quantity,
    bom_line_required_quantity_decimal,
    get_bom_items_by_material_id,
)
from apps.master_data.models.material import Material
from infra.exceptions.exceptions import ValidationError


class OutsourceMaterialDeductionPreviewLine:
    __slots__ = (
        "outsource_work_order_id",
        "outsource_work_order_code",
        "material_id",
        "material_code",
        "material_name",
        "standard_qty",
        "actual_qty",
        "overrun_qty",
        "unit_price",
        "deduction_amount",
    )

    def __init__(
        self,
        *,
        outsource_work_order_id: int,
        outsource_work_order_code: str,
        material_id: int,
        material_code: str,
        material_name: str,
        standard_qty: Decimal,
        actual_qty: Decimal,
        overrun_qty: Decimal,
        unit_price: Decimal,
        deduction_amount: Decimal,
    ) -> None:
        self.outsource_work_order_id = outsource_work_order_id
        self.outsource_work_order_code = outsource_work_order_code
        self.material_id = material_id
        self.material_code = material_code
        self.material_name = material_name
        self.standard_qty = standard_qty
        self.actual_qty = actual_qty
        self.overrun_qty = overrun_qty
        self.unit_price = unit_price
        self.deduction_amount = deduction_amount


class OutsourceMaterialDeductionService:
    @classmethod
    async def preview_deductions(
        cls,
        tenant_id: int,
        *,
        supplier_id: int,
        work_order_ids: Sequence[int],
    ) -> List[OutsourceMaterialDeductionPreviewLine]:
        if not work_order_ids:
            return []
        work_orders = await OutsourceWorkOrder.filter(
            tenant_id=tenant_id,
            id__in=list(work_order_ids),
            supplier_id=supplier_id,
            deleted_at__isnull=True,
        ).all()
        if not work_orders:
            return []

        result: List[OutsourceMaterialDeductionPreviewLine] = []
        for owo in work_orders:
            lines = await cls._preview_for_work_order(tenant_id, owo)
            result.extend(lines)
        return result

    @classmethod
    async def _preview_for_work_order(
        cls,
        tenant_id: int,
        owo: OutsourceWorkOrder,
    ) -> List[OutsourceMaterialDeductionPreviewLine]:
        product_id = int(owo.product_id or 0)
        if product_id <= 0:
            return []
        product = await Material.filter(
            tenant_id=tenant_id,
            id=product_id,
            deleted_at__isnull=True,
        ).first()
        if not product:
            return []

        wo_qty = Decimal(str(owo.quantity or 0))
        if wo_qty <= 0:
            return []

        standard_by_material: Dict[int, Decimal] = {}
        bom_items = await get_bom_items_by_material_id(
            tenant_id=tenant_id,
            material_id=product.id,
            only_approved=True,
        )
        for bom_item in bom_items:
            component = await bom_item.component
            if not component:
                continue
            component_qty = bom_line_required_quantity_decimal(
                bom_item_base_quantity(bom_item),
                wo_qty,
                bom_item.waste_rate,
            )
            mid = int(component.id)
            standard_by_material[mid] = standard_by_material.get(mid, Decimal("0")) + component_qty

        issues = await OutsourceMaterialIssue.filter(
            tenant_id=tenant_id,
            outsource_work_order_id=owo.id,
            status="completed",
            deleted_at__isnull=True,
        ).all()
        returns = await OutsourceMaterialReturn.filter(
            tenant_id=tenant_id,
            outsource_work_order_id=owo.id,
            status="completed",
            deleted_at__isnull=True,
        ).all()

        actual_by_material: Dict[int, Decimal] = {}
        cost_by_material: Dict[int, Decimal] = {}
        for issue in issues:
            mid = int(issue.material_id)
            actual_by_material[mid] = actual_by_material.get(mid, Decimal("0")) + Decimal(str(issue.quantity or 0))
            unit_cost = issue.issue_unit_cost
            if unit_cost is None:
                raise ValidationError(
                    f"委外发料单 {issue.code} 缺少发料成本快照，无法计算超耗扣款"
                )
            cost_by_material[mid] = Decimal(str(unit_cost))

        for ret in returns:
            mid = int(ret.material_id)
            actual_by_material[mid] = actual_by_material.get(mid, Decimal("0")) - Decimal(str(ret.quantity or 0))

        lines: List[OutsourceMaterialDeductionPreviewLine] = []
        material_ids = set(standard_by_material.keys()) | set(actual_by_material.keys())
        for mid in material_ids:
            standard = standard_by_material.get(mid, Decimal("0"))
            actual = max(Decimal("0"), actual_by_material.get(mid, Decimal("0")))
            overrun = actual - standard
            if overrun <= 0:
                continue
            if mid not in cost_by_material:
                raise ValidationError(f"物料 ID {mid} 发料缺少成本快照，无法计算超耗扣款")
            unit_price = cost_by_material[mid]
            material = await Material.filter(tenant_id=tenant_id, id=mid, deleted_at__isnull=True).first()
            if not material:
                continue
            amount = (overrun * unit_price).quantize(Decimal("0.01"))
            lines.append(
                OutsourceMaterialDeductionPreviewLine(
                    outsource_work_order_id=int(owo.id),
                    outsource_work_order_code=str(owo.code or ""),
                    material_id=mid,
                    material_code=str(material.main_code or ""),
                    material_name=str(material.name or ""),
                    standard_qty=standard,
                    actual_qty=actual,
                    overrun_qty=overrun,
                    unit_price=unit_price,
                    deduction_amount=amount,
                )
            )
        return lines
