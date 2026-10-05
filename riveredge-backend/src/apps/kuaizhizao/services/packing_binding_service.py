"""
装箱打包绑定业务服务

分箱剩余量门禁、来源行关联、包装物料真源、封箱状态、箱托层级字段与 ASN 汇总。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from tortoise.expressions import Q
from tortoise.functions import Sum
from tortoise.transactions import in_transaction

from apps.common.audit_actor import apply_create_audit, operator_name_from_user
from apps.common.base_service import AppBaseService
from apps.kuaizhizao.models.finished_goods_receipt import FinishedGoodsReceipt
from apps.kuaizhizao.models.finished_goods_receipt_item import FinishedGoodsReceiptItem
from apps.kuaizhizao.models.packing_binding import PackingBinding
from apps.kuaizhizao.models.sales_delivery import SalesDelivery
from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem
from apps.kuaizhizao.schemas.packing_binding import (
    PackingAsnLine,
    PackingAsnResponse,
    PackingBindingCreateFromDelivery,
    PackingBindingCreateFromReceipt,
    PackingBindingListResponse,
    PackingBindingPageResponse,
    PackingBindingResponse,
    PackingBindingStatisticsResponse,
    PackingBindingTaskPoolItemResponse,
    PackingBindingTaskPoolResponse,
    PackingBindingUpdate,
    PackingSourceRemainingLine,
    PackingSourceRemainingResponse,
)
from apps.kuaizhizao.services.document_action_policy.enricher import (
    enrich_packing_binding_capabilities_on_response,
    enrich_packing_binding_list_capabilities,
)
from apps.kuaizhizao.services.document_action_policy.packing_binding import (
    assert_packing_binding_capability,
)
from apps.master_data.models.material import Material
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User

PACKING_BINDING_BOX_RULE = "INDUSTRY_PACKING_BOX"

PACKING_BINDING_SORTABLE_FIELDS = frozenset({
    "box_no",
    "product_code",
    "product_name",
    "product_serial_no",
    "packing_quantity",
    "packing_material_code",
    "packing_material_name",
    "binding_method",
    "seal_status",
    "barcode",
    "bound_by_name",
    "bound_at",
    "created_at",
    "updated_at",
    "pallet_no",
    "parent_box_no",
    "packing_level",
})


def _dec(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _normalize_serial_list(
    primary: Optional[str],
    serial_numbers: Optional[List[str]],
) -> Tuple[Optional[str], Optional[List[str]]]:
    cleaned: List[str] = []
    seen = set()
    for raw in serial_numbers or []:
        sn = str(raw or "").strip()
        if not sn or sn in seen:
            continue
        seen.add(sn)
        cleaned.append(sn)
    primary_sn = (primary or "").strip() or None
    if primary_sn and primary_sn not in seen:
        cleaned.insert(0, primary_sn)
    elif not primary_sn and cleaned:
        primary_sn = cleaned[0]
    return primary_sn, cleaned or None


class PackingBindingService(AppBaseService[PackingBinding]):
    def __init__(self):
        super().__init__(PackingBinding)

    async def _resolve_material_snapshot(
        self,
        tenant_id: int,
        material_id: int,
        *,
        code: Optional[str] = None,
        name: Optional[str] = None,
        missing_label: str,
    ) -> Tuple[str, str]:
        material = await Material.get_or_none(
            id=material_id,
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        )
        if not material:
            raise ValidationError(f"{missing_label}不存在: {material_id}")
        return (
            str(material.code or code or "").strip(),
            str(material.name or name or "").strip(),
        )

    async def _resolve_packing_material(
        self,
        tenant_id: int,
        packing_material_id: Optional[int],
        packing_material_code: Optional[str],
        packing_material_name: Optional[str],
    ) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        if packing_material_id is None:
            return None, packing_material_code, packing_material_name
        code, name = await self._resolve_material_snapshot(
            tenant_id,
            packing_material_id,
            code=packing_material_code,
            name=packing_material_name,
            missing_label="包装物料",
        )
        if not code:
            raise ValidationError(f"包装物料缺少编码: {packing_material_id}")
        return packing_material_id, code, name or packing_material_name

    async def _allocate_box_no(self, tenant_id: int, box_no: Optional[str]) -> str:
        candidate = (box_no or "").strip()
        if candidate:
            exists = await PackingBinding.filter(
                tenant_id=tenant_id,
                box_no=candidate,
                deleted_at__isnull=True,
            ).exists()
            if exists:
                raise BusinessLogicError(f"箱号已存在: {candidate}")
            return candidate
        allocated = await self.generate_code(
            tenant_id=tenant_id,
            code_type=PACKING_BINDING_BOX_RULE,
        )
        allocated = str(allocated or "").strip()
        if not allocated:
            raise BusinessLogicError("箱号编码规则未返回有效箱号，请检查「装箱箱号」编码规则（INDUSTRY_PACKING_BOX）")
        exists = await PackingBinding.filter(
            tenant_id=tenant_id,
            box_no=allocated,
            deleted_at__isnull=True,
        ).exists()
        if exists:
            raise BusinessLogicError(f"编码规则生成的箱号已存在: {allocated}")
        return allocated

    async def _sum_packed_quantity(
        self,
        tenant_id: int,
        *,
        finished_goods_receipt_id: Optional[int] = None,
        sales_delivery_id: Optional[int] = None,
        source_line_id: Optional[int] = None,
        product_id: Optional[int] = None,
        exclude_binding_id: Optional[int] = None,
    ) -> Decimal:
        query = PackingBinding.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if finished_goods_receipt_id is not None:
            query = query.filter(finished_goods_receipt_id=finished_goods_receipt_id)
        if sales_delivery_id is not None:
            query = query.filter(sales_delivery_id=sales_delivery_id)
        if source_line_id is not None:
            query = query.filter(source_line_id=source_line_id)
        elif product_id is not None:
            query = query.filter(product_id=product_id)
        if exclude_binding_id is not None:
            query = query.exclude(id=exclude_binding_id)
        row = await query.annotate(total=Sum("packing_quantity")).values("total")
        return _dec(row[0]["total"] if row else 0)

    async def _count_boxes(
        self,
        tenant_id: int,
        *,
        finished_goods_receipt_id: Optional[int] = None,
        sales_delivery_id: Optional[int] = None,
        source_line_id: Optional[int] = None,
    ) -> int:
        query = PackingBinding.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if finished_goods_receipt_id is not None:
            query = query.filter(finished_goods_receipt_id=finished_goods_receipt_id)
        if sales_delivery_id is not None:
            query = query.filter(sales_delivery_id=sales_delivery_id)
        if source_line_id is not None:
            query = query.filter(source_line_id=source_line_id)
        return await query.count()

    async def _resolve_receipt_line(
        self,
        tenant_id: int,
        receipt_id: int,
        product_id: int,
        source_line_id: Optional[int],
    ) -> FinishedGoodsReceiptItem:
        if source_line_id is not None:
            line = await FinishedGoodsReceiptItem.get_or_none(
                id=source_line_id,
                tenant_id=tenant_id,
                receipt_id=receipt_id,
                deleted_at__isnull=True,
            )
            if not line:
                raise ValidationError(f"成品入库明细不存在: {source_line_id}")
            if int(line.material_id) != int(product_id):
                raise ValidationError("产品与入库明细物料不一致")
            return line
        lines = await FinishedGoodsReceiptItem.filter(
            tenant_id=tenant_id,
            receipt_id=receipt_id,
            material_id=product_id,
            deleted_at__isnull=True,
        ).all()
        if not lines:
            raise ValidationError(f"成品入库单不含该产品: {product_id}")
        if len(lines) > 1:
            raise ValidationError("同一产品存在多行明细，请指定 source_line_id")
        return lines[0]

    async def _resolve_delivery_line(
        self,
        tenant_id: int,
        delivery_id: int,
        product_id: int,
        source_line_id: Optional[int],
    ) -> SalesDeliveryItem:
        if source_line_id is not None:
            line = await SalesDeliveryItem.get_or_none(
                id=source_line_id,
                tenant_id=tenant_id,
                delivery_id=delivery_id,
                deleted_at__isnull=True,
            )
            if not line:
                raise ValidationError(f"销售出库明细不存在: {source_line_id}")
            if int(line.material_id) != int(product_id):
                raise ValidationError("产品与出库明细物料不一致")
            return line
        lines = await SalesDeliveryItem.filter(
            tenant_id=tenant_id,
            delivery_id=delivery_id,
            material_id=product_id,
            deleted_at__isnull=True,
        ).all()
        if not lines:
            raise ValidationError(f"销售出库单不含该产品: {product_id}")
        if len(lines) > 1:
            raise ValidationError("同一产品存在多行明细，请指定 source_line_id")
        return lines[0]

    def _line_required_qty_receipt(self, line: FinishedGoodsReceiptItem) -> Decimal:
        qty = _dec(line.qualified_quantity)
        if qty <= 0:
            qty = _dec(line.receipt_quantity)
        return qty

    def _line_required_qty_delivery(self, line: SalesDeliveryItem) -> Decimal:
        return _dec(line.delivery_quantity)

    async def _assert_remaining(
        self,
        tenant_id: int,
        *,
        finished_goods_receipt_id: Optional[int],
        sales_delivery_id: Optional[int],
        source_line_id: int,
        product_id: int,
        packing_quantity: Decimal,
        required_quantity: Decimal,
        exclude_binding_id: Optional[int] = None,
    ) -> None:
        if required_quantity <= 0:
            raise ValidationError("来源明细可装箱数量无效")
        packed = await self._sum_packed_quantity(
            tenant_id,
            finished_goods_receipt_id=finished_goods_receipt_id,
            sales_delivery_id=sales_delivery_id,
            source_line_id=source_line_id,
            product_id=product_id,
            exclude_binding_id=exclude_binding_id,
        )
        remaining = required_quantity - packed
        if packing_quantity > remaining:
            raise BusinessLogicError(
                f"装箱数量超出剩余可绑量（剩余 {remaining}，本次 {packing_quantity}）"
            )

    async def _create_document_relation(
        self,
        *,
        tenant_id: int,
        source_type: str,
        source_id: int,
        source_code: str,
        packing_binding: PackingBinding,
        created_by: int,
        relation_desc: str,
    ) -> None:
        from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
        from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

        await DocumentRelationNewService().create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type=source_type,
                source_id=source_id,
                source_code=source_code,
                source_name=None,
                target_type="packing_binding",
                target_id=packing_binding.id,
                target_code=packing_binding.box_no,
                target_name=None,
                relation_type="source",
                relation_mode="push",
                relation_desc=relation_desc,
            ),
            created_by=created_by,
        )

    async def create_packing_binding_from_receipt(
        self,
        tenant_id: int,
        receipt_id: int,
        binding_data: PackingBindingCreateFromReceipt,
        bound_by: int,
    ) -> PackingBindingResponse:
        async with in_transaction():
            receipt = await FinishedGoodsReceipt.get_or_none(
                id=receipt_id,
                tenant_id=tenant_id,
                deleted_at__isnull=True,
            )
            if not receipt:
                raise NotFoundError(f"成品入库单不存在: {receipt_id}")

            line = await self._resolve_receipt_line(
                tenant_id, receipt_id, binding_data.product_id, binding_data.source_line_id
            )
            required = self._line_required_qty_receipt(line)
            await self._assert_remaining(
                tenant_id,
                finished_goods_receipt_id=receipt_id,
                sales_delivery_id=None,
                source_line_id=int(line.id),
                product_id=binding_data.product_id,
                packing_quantity=_dec(binding_data.packing_quantity),
                required_quantity=required,
            )

            product_code, product_name = await self._resolve_material_snapshot(
                tenant_id,
                binding_data.product_id,
                code=binding_data.product_code or line.material_code,
                name=binding_data.product_name or line.material_name,
                missing_label="产品",
            )
            packing_material_id, packing_material_code, packing_material_name = (
                await self._resolve_packing_material(
                    tenant_id,
                    binding_data.packing_material_id,
                    binding_data.packing_material_code,
                    binding_data.packing_material_name,
                )
            )
            primary_sn, serial_numbers = _normalize_serial_list(
                binding_data.product_serial_no, binding_data.serial_numbers
            )
            box_no = await self._allocate_box_no(tenant_id, binding_data.box_no)
            user = await User.get_or_none(id=bound_by)
            method = (binding_data.binding_method or "manual").strip().lower()
            if method not in {"manual", "scan"}:
                raise ValidationError("binding_method 仅支持 manual/scan")
            if method == "scan" and not (binding_data.barcode or "").strip() and not primary_sn:
                raise ValidationError("扫码绑定时须提供条码或序列号")

            create_payload = dict(
                tenant_id=tenant_id,
                uuid=str(uuid.uuid4()),
                finished_goods_receipt_id=receipt_id,
                sales_delivery_id=None,
                source_line_id=int(line.id),
                product_id=binding_data.product_id,
                product_code=product_code,
                product_name=product_name,
                product_serial_no=primary_sn,
                serial_numbers=serial_numbers,
                packing_material_id=packing_material_id,
                packing_material_code=packing_material_code,
                packing_material_name=packing_material_name,
                packing_quantity=binding_data.packing_quantity,
                box_no=box_no,
                packing_level=binding_data.packing_level or "carton",
                parent_box_no=(binding_data.parent_box_no or None),
                pallet_no=(binding_data.pallet_no or None),
                binding_method=method,
                barcode=(binding_data.barcode or None),
                seal_status=binding_data.seal_status or "bound",
                bound_by=bound_by,
                bound_by_name=operator_name_from_user(user),
                bound_at=binding_data.bound_at or resolve_business_datetime(),
                remarks=binding_data.remarks,
            )
            apply_create_audit(create_payload, user)
            packing_binding = await PackingBinding.create(**create_payload)
            await self._create_document_relation(
                tenant_id=tenant_id,
                source_type="finished_goods_receipt",
                source_id=receipt_id,
                source_code=receipt.receipt_code,
                packing_binding=packing_binding,
                created_by=bound_by,
                relation_desc="成品入库创建装箱绑定",
            )
            return enrich_packing_binding_capabilities_on_response(
                packing_binding,
                PackingBindingResponse.model_validate(packing_binding),
            )

    async def create_packing_binding_from_delivery(
        self,
        tenant_id: int,
        delivery_id: int,
        binding_data: PackingBindingCreateFromDelivery,
        bound_by: int,
    ) -> PackingBindingResponse:
        async with in_transaction():
            delivery = await SalesDelivery.get_or_none(
                id=delivery_id,
                tenant_id=tenant_id,
                deleted_at__isnull=True,
            )
            if not delivery:
                raise NotFoundError(f"销售出库单不存在: {delivery_id}")

            line = await self._resolve_delivery_line(
                tenant_id, delivery_id, binding_data.product_id, binding_data.source_line_id
            )
            required = self._line_required_qty_delivery(line)
            await self._assert_remaining(
                tenant_id,
                finished_goods_receipt_id=None,
                sales_delivery_id=delivery_id,
                source_line_id=int(line.id),
                product_id=binding_data.product_id,
                packing_quantity=_dec(binding_data.packing_quantity),
                required_quantity=required,
            )

            product_code, product_name = await self._resolve_material_snapshot(
                tenant_id,
                binding_data.product_id,
                code=binding_data.product_code or line.material_code,
                name=binding_data.product_name or line.material_name,
                missing_label="产品",
            )
            packing_material_id, packing_material_code, packing_material_name = (
                await self._resolve_packing_material(
                    tenant_id,
                    binding_data.packing_material_id,
                    binding_data.packing_material_code,
                    binding_data.packing_material_name,
                )
            )
            primary_sn, serial_numbers = _normalize_serial_list(
                binding_data.product_serial_no, binding_data.serial_numbers
            )
            box_no = await self._allocate_box_no(tenant_id, binding_data.box_no)
            user = await User.get_or_none(id=bound_by)
            method = (binding_data.binding_method or "manual").strip().lower()
            if method not in {"manual", "scan"}:
                raise ValidationError("binding_method 仅支持 manual/scan")
            if method == "scan" and not (binding_data.barcode or "").strip() and not primary_sn:
                raise ValidationError("扫码绑定时须提供条码或序列号")

            create_payload = dict(
                tenant_id=tenant_id,
                uuid=str(uuid.uuid4()),
                finished_goods_receipt_id=None,
                sales_delivery_id=delivery_id,
                source_line_id=int(line.id),
                product_id=binding_data.product_id,
                product_code=product_code,
                product_name=product_name,
                product_serial_no=primary_sn,
                serial_numbers=serial_numbers,
                packing_material_id=packing_material_id,
                packing_material_code=packing_material_code,
                packing_material_name=packing_material_name,
                packing_quantity=binding_data.packing_quantity,
                box_no=box_no,
                packing_level=binding_data.packing_level or "carton",
                parent_box_no=(binding_data.parent_box_no or None),
                pallet_no=(binding_data.pallet_no or None),
                binding_method=method,
                barcode=(binding_data.barcode or None),
                seal_status=binding_data.seal_status or "bound",
                bound_by=bound_by,
                bound_by_name=operator_name_from_user(user),
                bound_at=binding_data.bound_at or resolve_business_datetime(),
                remarks=binding_data.remarks,
            )
            apply_create_audit(create_payload, user)
            packing_binding = await PackingBinding.create(**create_payload)
            await self._create_document_relation(
                tenant_id=tenant_id,
                source_type="sales_delivery",
                source_id=delivery_id,
                source_code=delivery.delivery_code,
                packing_binding=packing_binding,
                created_by=bound_by,
                relation_desc="销售出库创建装箱绑定",
            )
            return enrich_packing_binding_capabilities_on_response(
                packing_binding,
                PackingBindingResponse.model_validate(packing_binding),
            )

    async def get_source_remaining(
        self,
        tenant_id: int,
        *,
        source_type: str,
        source_id: int,
    ) -> PackingSourceRemainingResponse:
        lines_out: List[PackingSourceRemainingLine] = []
        if source_type == "finished_goods_receipt":
            receipt = await FinishedGoodsReceipt.get_or_none(
                id=source_id, tenant_id=tenant_id, deleted_at__isnull=True
            )
            if not receipt:
                raise NotFoundError(f"成品入库单不存在: {source_id}")
            items = await FinishedGoodsReceiptItem.filter(
                tenant_id=tenant_id, receipt_id=source_id, deleted_at__isnull=True
            ).all()
            for item in items:
                required = self._line_required_qty_receipt(item)
                packed = await self._sum_packed_quantity(
                    tenant_id,
                    finished_goods_receipt_id=source_id,
                    source_line_id=int(item.id),
                )
                box_count = await self._count_boxes(
                    tenant_id,
                    finished_goods_receipt_id=source_id,
                    source_line_id=int(item.id),
                )
                lines_out.append(
                    PackingSourceRemainingLine(
                        source_line_id=int(item.id),
                        product_id=int(item.material_id),
                        product_code=item.material_code,
                        product_name=item.material_name,
                        required_quantity=required,
                        packed_quantity=packed,
                        remaining_quantity=max(Decimal("0"), required - packed),
                        box_count=box_count,
                    )
                )
        elif source_type == "sales_delivery":
            delivery = await SalesDelivery.get_or_none(
                id=source_id, tenant_id=tenant_id, deleted_at__isnull=True
            )
            if not delivery:
                raise NotFoundError(f"销售出库单不存在: {source_id}")
            items = await SalesDeliveryItem.filter(
                tenant_id=tenant_id, delivery_id=source_id, deleted_at__isnull=True
            ).all()
            for item in items:
                required = self._line_required_qty_delivery(item)
                packed = await self._sum_packed_quantity(
                    tenant_id,
                    sales_delivery_id=source_id,
                    source_line_id=int(item.id),
                )
                box_count = await self._count_boxes(
                    tenant_id,
                    sales_delivery_id=source_id,
                    source_line_id=int(item.id),
                )
                lines_out.append(
                    PackingSourceRemainingLine(
                        source_line_id=int(item.id),
                        product_id=int(item.material_id),
                        product_code=item.material_code,
                        product_name=item.material_name,
                        required_quantity=required,
                        packed_quantity=packed,
                        remaining_quantity=max(Decimal("0"), required - packed),
                        box_count=box_count,
                    )
                )
        else:
            raise ValidationError("source_type 须为 sales_delivery 或 finished_goods_receipt")

        required_total = sum((x.required_quantity for x in lines_out), Decimal("0"))
        packed_total = sum((x.packed_quantity for x in lines_out), Decimal("0"))
        return PackingSourceRemainingResponse(
            source_type=source_type,  # type: ignore[arg-type]
            source_id=source_id,
            lines=lines_out,
            required_quantity=required_total,
            packed_quantity=packed_total,
            remaining_quantity=max(Decimal("0"), required_total - packed_total),
            box_count=sum(x.box_count for x in lines_out),
        )

    async def get_packing_bindings_by_receipt(
        self, tenant_id: int, receipt_id: int
    ) -> List[PackingBindingListResponse]:
        bindings = await PackingBinding.filter(
            tenant_id=tenant_id,
            finished_goods_receipt_id=receipt_id,
            deleted_at__isnull=True,
        ).order_by("-bound_at")
        responses = [PackingBindingListResponse.model_validate(b) for b in bindings]
        return enrich_packing_binding_list_capabilities(bindings, responses)

    async def get_packing_bindings_by_delivery(
        self, tenant_id: int, delivery_id: int
    ) -> List[PackingBindingListResponse]:
        bindings = await PackingBinding.filter(
            tenant_id=tenant_id,
            sales_delivery_id=delivery_id,
            deleted_at__isnull=True,
        ).order_by("-bound_at")
        responses = [PackingBindingListResponse.model_validate(b) for b in bindings]
        return enrich_packing_binding_list_capabilities(bindings, responses)

    async def delete_packing_binding(self, tenant_id: int, binding_id: int) -> None:
        binding = await PackingBinding.get_or_none(
            id=binding_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not binding:
            raise NotFoundError(f"装箱绑定记录不存在: {binding_id}")
        assert_packing_binding_capability(binding, "delete")
        binding.deleted_at = resolve_business_datetime()
        await binding.save()

    async def seal_packing_binding(
        self, tenant_id: int, binding_id: int
    ) -> PackingBindingResponse:
        async with in_transaction():
            binding = await PackingBinding.get_or_none(
                id=binding_id, tenant_id=tenant_id, deleted_at__isnull=True
            )
            if not binding:
                raise NotFoundError(f"装箱绑定记录不存在: {binding_id}")
            assert_packing_binding_capability(binding, "seal")
            binding.seal_status = "sealed"
            await binding.save()
            return enrich_packing_binding_capabilities_on_response(
                binding,
                PackingBindingResponse.model_validate(binding),
            )

    def _build_packing_binding_list_query(
        self,
        tenant_id: int,
        receipt_id: Optional[int] = None,
        sales_delivery_id: Optional[int] = None,
        product_id: Optional[int] = None,
        box_no: Optional[str] = None,
        uuid_value: Optional[str] = None,
        keyword: Optional[str] = None,
        product_code: Optional[str] = None,
        product_name: Optional[str] = None,
        product_serial_no: Optional[str] = None,
        packing_material_name: Optional[str] = None,
        binding_method: Optional[str] = None,
        seal_status: Optional[str] = None,
        source_type: Optional[str] = None,
        bound_at_from: Optional[Any] = None,
        bound_at_to: Optional[Any] = None,
        created_start_date: Optional[Any] = None,
        created_end_date: Optional[Any] = None,
    ):
        from datetime import date, datetime, time

        query = PackingBinding.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if receipt_id:
            query = query.filter(finished_goods_receipt_id=receipt_id)
        if sales_delivery_id:
            query = query.filter(sales_delivery_id=sales_delivery_id)
        if product_id:
            query = query.filter(product_id=product_id)
        bn = (box_no or "").strip()
        if bn:
            query = query.filter(box_no__icontains=bn)
        if uuid_value:
            query = query.filter(uuid=uuid_value)
        kw = (keyword or "").strip()
        if kw:
            query = query.filter(
                Q(box_no__icontains=kw)
                | Q(product_code__icontains=kw)
                | Q(product_name__icontains=kw)
                | Q(product_serial_no__icontains=kw)
                | Q(packing_material_name__icontains=kw)
                | Q(barcode__icontains=kw)
                | Q(bound_by_name__icontains=kw)
                | Q(pallet_no__icontains=kw)
            )
        pc = (product_code or "").strip()
        if pc:
            query = query.filter(product_code__icontains=pc)
        pn = (product_name or "").strip()
        if pn:
            query = query.filter(product_name__icontains=pn)
        psn = (product_serial_no or "").strip()
        if psn:
            query = query.filter(product_serial_no__icontains=psn)
        pmn = (packing_material_name or "").strip()
        if pmn:
            query = query.filter(packing_material_name__icontains=pmn)
        if binding_method:
            query = query.filter(binding_method=binding_method)
        if seal_status:
            query = query.filter(seal_status=seal_status.strip())
        st = (source_type or "").strip()
        if st == "finished_goods_receipt":
            query = query.filter(finished_goods_receipt_id__isnull=False)
        elif st == "sales_delivery":
            query = query.filter(sales_delivery_id__isnull=False)
        if bound_at_from is not None:
            query = query.filter(bound_at__gte=bound_at_from)
        if bound_at_to is not None:
            query = query.filter(bound_at__lte=bound_at_to)
        if created_start_date is not None:
            if isinstance(created_start_date, date) and not isinstance(created_start_date, datetime):
                query = query.filter(created_at__gte=datetime.combine(created_start_date, time.min))
            else:
                query = query.filter(created_at__gte=created_start_date)
        if created_end_date is not None:
            if isinstance(created_end_date, date) and not isinstance(created_end_date, datetime):
                query = query.filter(created_at__lte=datetime.combine(created_end_date, time.max))
            else:
                query = query.filter(created_at__lte=created_end_date)
        return query

    async def list_packing_bindings(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        **filters,
    ) -> List[PackingBindingListResponse]:
        query = self._build_packing_binding_list_query(tenant_id=tenant_id, **filters)
        order_clause = order_by if order_by else "-bound_at"
        field = order_clause.lstrip("-")
        if field not in PACKING_BINDING_SORTABLE_FIELDS:
            order_clause = "-bound_at"
        bindings = await query.order_by(order_clause).offset(skip).limit(limit)
        responses = [PackingBindingListResponse.model_validate(b) for b in bindings]
        return enrich_packing_binding_list_capabilities(bindings, responses)

    async def list_packing_bindings_page(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        **filters,
    ) -> PackingBindingPageResponse:
        query = self._build_packing_binding_list_query(tenant_id=tenant_id, **filters)
        total = await query.count()
        order_clause = order_by if order_by else "-bound_at"
        field = order_clause.lstrip("-")
        if field not in PACKING_BINDING_SORTABLE_FIELDS:
            order_clause = "-bound_at"
        rows = await query.order_by(order_clause).offset(skip).limit(limit)
        items = enrich_packing_binding_list_capabilities(
            rows,
            [PackingBindingListResponse.model_validate(r) for r in rows],
        )
        return PackingBindingPageResponse(data=items, total=total, success=True)

    async def get_packing_binding_statistics(self, tenant_id: int) -> PackingBindingStatisticsResponse:
        base = PackingBinding.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        total = await base.count()
        scan = await base.filter(binding_method="scan").count()
        manual = await base.filter(binding_method="manual").count()
        sealed = await base.filter(seal_status="sealed").count()
        bound = await base.filter(seal_status="bound").count()
        return PackingBindingStatisticsResponse(
            total=total, scan=scan, manual=manual, sealed=sealed, bound=bound
        )

    async def get_task_pool_summary(
        self, tenant_id: int, limit: int = 20
    ) -> PackingBindingTaskPoolResponse:
        pending_review_qs = SalesDelivery.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            review_status="待审核",
        ).exclude(status__in=["已完成", "COMPLETED", "已取消", "CANCELLED"])
        pending_outbound_qs = SalesDelivery.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            status="待出库",
        ).exclude(review_status="待审核")
        pending_receipt_qs = FinishedGoodsReceipt.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).exclude(status__in=["已完成", "COMPLETED", "已取消", "CANCELLED", "已入库"])

        pending_review = await pending_review_qs.count()
        pending_outbound = await pending_outbound_qs.count()
        pending_receipt = await pending_receipt_qs.count()

        delivery_rows = (
            await SalesDelivery.filter(tenant_id=tenant_id, deleted_at__isnull=True)
            .filter(Q(review_status="待审核") | Q(status="待出库"))
            .order_by("-updated_at", "-id")
            .limit(limit)
        )
        receipt_rows = (
            await FinishedGoodsReceipt.filter(tenant_id=tenant_id, deleted_at__isnull=True)
            .exclude(status__in=["已完成", "COMPLETED", "已取消", "CANCELLED", "已入库"])
            .order_by("-updated_at", "-id")
            .limit(limit)
        )

        items: List[PackingBindingTaskPoolItemResponse] = []
        for row in delivery_rows:
            remaining = await self.get_source_remaining(
                tenant_id, source_type="sales_delivery", source_id=row.id
            )
            if remaining.remaining_quantity <= 0:
                continue
            items.append(
                PackingBindingTaskPoolItemResponse(
                    id=row.id,
                    source_type="sales_delivery",
                    doc_code=row.delivery_code,
                    party_name=row.customer_name or "",
                    review_status=row.review_status or "",
                    status=row.status or "",
                    required_quantity=remaining.required_quantity,
                    packed_quantity=remaining.packed_quantity,
                    remaining_quantity=remaining.remaining_quantity,
                    box_count=remaining.box_count,
                    updated_at=row.updated_at,
                    delivery_code=row.delivery_code,
                    customer_name=row.customer_name or "",
                )
            )
        for row in receipt_rows:
            remaining = await self.get_source_remaining(
                tenant_id, source_type="finished_goods_receipt", source_id=row.id
            )
            if remaining.remaining_quantity <= 0:
                continue
            items.append(
                PackingBindingTaskPoolItemResponse(
                    id=row.id,
                    source_type="finished_goods_receipt",
                    doc_code=row.receipt_code,
                    party_name=getattr(row, "workshop_name", None) or "",
                    review_status=getattr(row, "review_status", None) or "",
                    status=row.status or "",
                    required_quantity=remaining.required_quantity,
                    packed_quantity=remaining.packed_quantity,
                    remaining_quantity=remaining.remaining_quantity,
                    box_count=remaining.box_count,
                    updated_at=row.updated_at,
                    delivery_code=row.receipt_code,
                    customer_name=getattr(row, "workshop_name", None) or "",
                )
            )

        items.sort(key=lambda x: x.updated_at, reverse=True)
        items = items[:limit]
        return PackingBindingTaskPoolResponse(
            pending_review=pending_review,
            pending_outbound=pending_outbound,
            pending_receipt=pending_receipt,
            total=pending_review + pending_outbound + pending_receipt,
            items=items,
        )

    async def get_packing_binding_by_id(
        self, tenant_id: int, binding_id: int
    ) -> PackingBindingResponse:
        binding = await PackingBinding.get_or_none(
            id=binding_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not binding:
            raise NotFoundError(f"装箱绑定记录不存在: {binding_id}")
        return enrich_packing_binding_capabilities_on_response(
            binding,
            PackingBindingResponse.model_validate(binding),
        )

    async def update_packing_binding(
        self,
        tenant_id: int,
        binding_id: int,
        binding_data: PackingBindingUpdate,
        updated_by: int,
    ) -> PackingBindingResponse:
        async with in_transaction():
            binding = await PackingBinding.get_or_none(
                id=binding_id, tenant_id=tenant_id, deleted_at__isnull=True
            )
            if not binding:
                raise NotFoundError(f"装箱绑定记录不存在: {binding_id}")
            assert_packing_binding_capability(binding, "update")

            if binding_data.box_no is not None:
                new_box = binding_data.box_no.strip()
                if new_box and new_box != binding.box_no:
                    exists = await PackingBinding.filter(
                        tenant_id=tenant_id,
                        box_no=new_box,
                        deleted_at__isnull=True,
                    ).exclude(id=binding_id).exists()
                    if exists:
                        raise BusinessLogicError(f"箱号已存在: {new_box}")
                    binding.box_no = new_box

            if binding_data.packing_quantity is not None:
                required = Decimal("0")
                if binding.source_line_id and binding.finished_goods_receipt_id:
                    line = await FinishedGoodsReceiptItem.get_or_none(
                        id=binding.source_line_id,
                        tenant_id=tenant_id,
                        deleted_at__isnull=True,
                    )
                    if line:
                        required = self._line_required_qty_receipt(line)
                elif binding.source_line_id and binding.sales_delivery_id:
                    line = await SalesDeliveryItem.get_or_none(
                        id=binding.source_line_id,
                        tenant_id=tenant_id,
                        deleted_at__isnull=True,
                    )
                    if line:
                        required = self._line_required_qty_delivery(line)
                if required > 0:
                    await self._assert_remaining(
                        tenant_id,
                        finished_goods_receipt_id=binding.finished_goods_receipt_id,
                        sales_delivery_id=binding.sales_delivery_id,
                        source_line_id=int(binding.source_line_id),
                        product_id=int(binding.product_id),
                        packing_quantity=_dec(binding_data.packing_quantity),
                        required_quantity=required,
                        exclude_binding_id=binding_id,
                    )
                binding.packing_quantity = binding_data.packing_quantity

            if binding_data.remarks is not None:
                binding.remarks = binding_data.remarks
            if binding_data.attachments is not None:
                binding.attachments = binding_data.attachments
            if binding_data.product_serial_no is not None or binding_data.serial_numbers is not None:
                primary_sn, serial_numbers = _normalize_serial_list(
                    binding_data.product_serial_no
                    if binding_data.product_serial_no is not None
                    else binding.product_serial_no,
                    binding_data.serial_numbers
                    if binding_data.serial_numbers is not None
                    else binding.serial_numbers,
                )
                binding.product_serial_no = primary_sn
                binding.serial_numbers = serial_numbers
            if binding_data.packing_material_id is not None:
                mid, code, name = await self._resolve_packing_material(
                    tenant_id,
                    binding_data.packing_material_id,
                    binding_data.packing_material_code,
                    binding_data.packing_material_name,
                )
                binding.packing_material_id = mid
                binding.packing_material_code = code
                binding.packing_material_name = name
            if binding_data.packing_level is not None:
                binding.packing_level = binding_data.packing_level
            if binding_data.parent_box_no is not None:
                binding.parent_box_no = binding_data.parent_box_no or None
            if binding_data.pallet_no is not None:
                binding.pallet_no = binding_data.pallet_no or None
            if binding_data.seal_status is not None:
                if binding_data.seal_status == "sealed":
                    assert_packing_binding_capability(binding, "seal")
                binding.seal_status = binding_data.seal_status

            await binding.save()
            logger.debug("packing_binding updated id=%s by=%s", binding_id, updated_by)
            return enrich_packing_binding_capabilities_on_response(
                binding,
                PackingBindingResponse.model_validate(binding),
            )

    async def get_asn_for_delivery(
        self, tenant_id: int, delivery_id: int
    ) -> PackingAsnResponse:
        delivery = await SalesDelivery.get_or_none(
            id=delivery_id, tenant_id=tenant_id, deleted_at__isnull=True
        )
        if not delivery:
            raise NotFoundError(f"销售出库单不存在: {delivery_id}")
        bindings = await PackingBinding.filter(
            tenant_id=tenant_id,
            sales_delivery_id=delivery_id,
            deleted_at__isnull=True,
        ).order_by("pallet_no", "parent_box_no", "box_no", "id")
        lines = [
            PackingAsnLine(
                box_no=b.box_no,
                packing_level=b.packing_level,
                parent_box_no=b.parent_box_no,
                pallet_no=b.pallet_no,
                product_code=b.product_code,
                product_name=b.product_name,
                packing_quantity=_dec(b.packing_quantity),
                product_serial_no=b.product_serial_no,
                serial_numbers=b.serial_numbers if isinstance(b.serial_numbers, list) else None,
                seal_status=b.seal_status,
            )
            for b in bindings
        ]
        total_qty = sum((x.packing_quantity for x in lines), Decimal("0"))
        return PackingAsnResponse(
            sales_delivery_id=delivery_id,
            delivery_code=delivery.delivery_code,
            customer_name=delivery.customer_name or "",
            box_count=len(lines),
            total_quantity=total_qty,
            lines=lines,
        )

    async def count_pending_task_pool(self, tenant_id: int) -> int:
        """菜单角标：仍有剩余可绑数量的出库/入库任务数。"""
        summary = await self.get_task_pool_summary(tenant_id, limit=200)
        return len(summary.items)
