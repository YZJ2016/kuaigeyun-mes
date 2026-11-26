"""
装箱 HU 会话、组托、核销（标准流程扩展）

由 PackingBindingService 混入调用，保持单服务入口。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from tortoise.transactions import in_transaction

from apps.common.audit_actor import apply_create_audit, operator_name_from_user
from apps.kuaizhizao.models.packing_binding import PackingBinding
from apps.kuaizhizao.models.packing_binding_line import PackingBindingLine
from apps.kuaizhizao.models.packing_profile import PackingProfile
from apps.kuaizhizao.services.packing_profile_service import PackingProfileService
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError, ValidationError
from infra.models.user import User


def _dec(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


async def sync_binding_quantity_and_serials(
    tenant_id: int,
    binding: PackingBinding,
) -> None:
    lines = await PackingBindingLine.filter(
        tenant_id=tenant_id,
        binding_id=binding.id,
        line_status="active",
        deleted_at__isnull=True,
    ).order_by("id")
    serials = [str(l.product_serial_no).strip() for l in lines if str(l.product_serial_no or "").strip()]
    total = sum((_dec(l.quantity) for l in lines), Decimal("0"))
    binding.packing_quantity = total
    binding.product_serial_no = serials[0] if serials else None
    binding.serial_numbers = serials or None
    await binding.save()


async def assert_serial_available(
    tenant_id: int,
    serial_no: str,
    *,
    exclude_binding_id: Optional[int] = None,
) -> None:
    sn = (serial_no or "").strip()
    if not sn:
        raise ValidationError("序列号不能为空")
    line_q = PackingBindingLine.filter(
        tenant_id=tenant_id,
        product_serial_no=sn,
        line_status="active",
        deleted_at__isnull=True,
    )
    if exclude_binding_id is not None:
        line_q = line_q.exclude(binding_id=exclude_binding_id)
    if await line_q.exists():
        raise BusinessLogicError(f"序列号 {sn} 已在其它有效装箱中（已扣减预占）")

    legacy = await PackingBinding.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        consumed_at__isnull=True,
        seal_status__in=["bound", "sealed"],
    )
    if exclude_binding_id is not None:
        legacy = legacy.exclude(id=exclude_binding_id)
    for row in await legacy.all():
        nums = row.serial_numbers if isinstance(row.serial_numbers, list) else []
        if sn in nums or (row.product_serial_no or "").strip() == sn:
            has_line = await PackingBindingLine.filter(
                tenant_id=tenant_id,
                binding_id=row.id,
                deleted_at__isnull=True,
            ).exists()
            if not has_line:
                raise BusinessLogicError(f"序列号 {sn} 已在其它有效装箱中（已扣减预占）")


def assert_mix_policy(
    profile: PackingProfile,
    binding: PackingBinding,
    product_id: int,
) -> None:
    policy = (profile.mix_policy or "same_material").strip()
    if policy == "mixed":
        return
    current_pid = int(binding.product_id)
    new_pid = int(product_id)
    if policy == "same_product" and current_pid != new_pid and _dec(binding.packing_quantity) > 0:
        raise BusinessLogicError("当前箱规不允许混装不同产品")
    if policy == "same_material" and current_pid != new_pid and _dec(binding.packing_quantity) > 0:
        raise BusinessLogicError("当前箱规不允许混装不同物料")


async def open_packing_session_core(
    svc: Any,
    tenant_id: int,
    *,
    source_type: str,
    source_id: int,
    product_id: int,
    source_line_id: Optional[int],
    bound_by: int,
    box_no: Optional[str],
    packing_material_id: Optional[int],
    packing_material_code: Optional[str],
    packing_material_name: Optional[str],
) -> PackingBinding:
    profile_svc = PackingProfileService()
    profile = await profile_svc.get_effective_profile(tenant_id, material_id=product_id)
    if box_no and not profile.allow_manual_box_code:
        raise BusinessLogicError("当前箱规不允许手工输入箱码")

    if source_type == "finished_goods_receipt":
        line = await svc._resolve_receipt_line(tenant_id, source_id, product_id, source_line_id)
        required = svc._line_required_qty_receipt(line)
        fid, sid = source_id, None
        product_code, product_name = await svc._resolve_material_snapshot(
            tenant_id,
            product_id,
            code=line.material_code,
            name=line.material_name,
            missing_label="产品",
        )
    elif source_type == "sales_delivery":
        line = await svc._resolve_delivery_line(tenant_id, source_id, product_id, source_line_id)
        required = svc._line_required_qty_delivery(line)
        fid, sid = None, source_id
        product_code, product_name = await svc._resolve_material_snapshot(
            tenant_id,
            product_id,
            code=line.material_code,
            name=line.material_name,
            missing_label="产品",
        )
    else:
        raise ValidationError("source_type 须为 sales_delivery 或 finished_goods_receipt")

    await svc._assert_remaining(
        tenant_id,
        finished_goods_receipt_id=fid,
        sales_delivery_id=sid,
        source_line_id=int(line.id),
        product_id=product_id,
        packing_quantity=Decimal("1"),
        required_quantity=required,
    )

    pm_id, pm_code, pm_name = await svc._resolve_packing_material(
        tenant_id,
        packing_material_id,
        packing_material_code,
        packing_material_name,
    )
    allocated_box = await svc._allocate_box_no(tenant_id, box_no)
    user = await User.get_or_none(id=bound_by)
    now = resolve_business_datetime()
    create_payload = dict(
        tenant_id=tenant_id,
        uuid=str(uuid.uuid4()),
        finished_goods_receipt_id=fid,
        sales_delivery_id=sid,
        source_line_id=int(line.id),
        product_id=product_id,
        product_code=product_code,
        product_name=product_name,
        product_serial_no=None,
        serial_numbers=None,
        packing_material_id=pm_id,
        packing_material_code=pm_code,
        packing_material_name=pm_name,
        packing_quantity=Decimal("0"),
        box_no=allocated_box,
        packing_level="carton",
        binding_method="scan",
        seal_status="bound",
        target_quantity=profile.max_quantity,
        packing_profile_id=profile.id,
        bound_by=bound_by,
        bound_by_name=operator_name_from_user(user),
        bound_at=now,
    )
    apply_create_audit(create_payload, user)
    return await PackingBinding.create(**create_payload)


async def scan_into_box_core(
    svc: Any,
    tenant_id: int,
    binding_id: int,
    *,
    serial_number: str,
    quantity: Decimal,
    scanned_by: int,
) -> Tuple[PackingBinding, PackingBindingLine]:
    binding = await PackingBinding.get_or_none(
        id=binding_id, tenant_id=tenant_id, deleted_at__isnull=True
    )
    if not binding:
        raise NotFoundError(f"装箱绑定记录不存在: {binding_id}")
    if binding.consumed_at is not None:
        raise BusinessLogicError("该箱已核销，不可再扫入")
    if str(binding.seal_status or "").strip().lower() == "sealed":
        profile = await PackingProfileService().get_effective_profile(
            tenant_id, material_id=int(binding.product_id)
        )
        if not profile.refill_open_box:
            raise BusinessLogicError("该箱已封箱，不可继续扫入")

    profile = await PackingProfile.get_or_none(id=binding.packing_profile_id) if binding.packing_profile_id else None
    if not profile:
        profile = await PackingProfileService().get_effective_profile(
            tenant_id, material_id=int(binding.product_id)
        )

    assert_mix_policy(profile, binding, int(binding.product_id))
    await assert_serial_available(tenant_id, serial_number, exclude_binding_id=binding_id)

    qty = _dec(quantity)
    if qty <= Decimal("0"):
        qty = Decimal("1")

    if binding.source_line_id:
        required = Decimal("0")
        if binding.finished_goods_receipt_id:
            from apps.kuaizhizao.models.finished_goods_receipt_item import FinishedGoodsReceiptItem

            line = await FinishedGoodsReceiptItem.get_or_none(id=binding.source_line_id, tenant_id=tenant_id)
            if line:
                required = svc._line_required_qty_receipt(line)
        elif binding.sales_delivery_id:
            from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem

            line = await SalesDeliveryItem.get_or_none(id=binding.source_line_id, tenant_id=tenant_id)
            if line:
                required = svc._line_required_qty_delivery(line)
        if required > 0:
            await svc._assert_remaining(
                tenant_id,
                finished_goods_receipt_id=binding.finished_goods_receipt_id,
                sales_delivery_id=binding.sales_delivery_id,
                source_line_id=int(binding.source_line_id),
                product_id=int(binding.product_id),
                packing_quantity=qty,
                required_quantity=required,
                exclude_binding_id=binding_id,
            )

    cap = profile.max_quantity
    if cap is not None and _dec(cap) > Decimal("0"):
        projected = _dec(binding.packing_quantity) + qty
        if projected > _dec(cap):
            raise BusinessLogicError(f"超过单箱目标容量 {cap}")

    now = resolve_business_datetime()
    line_row = await PackingBindingLine.create(
        tenant_id=tenant_id,
        uuid=str(uuid.uuid4()),
        binding_id=binding.id,
        product_id=int(binding.product_id),
        product_serial_no=serial_number.strip(),
        quantity=qty,
        line_status="active",
        scanned_at=now,
    )
    await sync_binding_quantity_and_serials(tenant_id, binding)
    binding = await PackingBinding.get(id=binding.id)

    if (profile.seal_policy or "").strip() == "auto_on_full" and cap is not None:
        if _dec(binding.packing_quantity) >= _dec(cap):
            binding.seal_status = "sealed"
            await binding.save()

    return binding, line_row


async def unbind_line_core(
    tenant_id: int,
    line_id: int,
    *,
    operator_id: int,
) -> PackingBinding:
    line = await PackingBindingLine.get_or_none(
        id=line_id, tenant_id=tenant_id, deleted_at__isnull=True
    )
    if not line:
        raise NotFoundError(f"装箱明细不存在: {line_id}")
    if line.line_status != "active":
        raise BusinessLogicError("仅有效明细可解绑")
    binding = await PackingBinding.get_or_none(
        id=line.binding_id, tenant_id=tenant_id, deleted_at__isnull=True
    )
    if not binding:
        raise NotFoundError("装箱绑定不存在")
    if binding.consumed_at is not None:
        raise BusinessLogicError("该箱已核销，不可解绑")
    if str(binding.seal_status or "").strip().lower() == "sealed":
        raise BusinessLogicError("已封箱须先拆封后再解绑明细")

    line.line_status = "unbound"
    line.unbound_at = resolve_business_datetime()
    await line.save()
    await sync_binding_quantity_and_serials(tenant_id, binding)
    return await PackingBinding.get(id=binding.id)


async def nest_boxes_on_pallet_core(
    tenant_id: int,
    *,
    pallet_no: str,
    box_nos: List[str],
) -> List[PackingBinding]:
    pallet = (pallet_no or "").strip()
    if not pallet:
        raise ValidationError("托盘号不能为空")
    cleaned_boxes = [str(b).strip() for b in box_nos if str(b or "").strip()]
    if not cleaned_boxes:
        raise ValidationError("请提供至少一个箱号")
    updated: List[PackingBinding] = []
    for box in cleaned_boxes:
        binding = await PackingBinding.get_or_none(
            tenant_id=tenant_id, box_no=box, deleted_at__isnull=True
        )
        if not binding:
            raise NotFoundError(f"箱号不存在: {box}")
        if str(binding.seal_status or "").strip().lower() != "sealed":
            raise BusinessLogicError(f"箱 {box} 须先封箱再组托")
        binding.pallet_no = pallet
        binding.packing_level = "carton"
        await binding.save()
        updated.append(binding)
    return updated


async def resolve_box_core(
    tenant_id: int,
    box_no: str,
) -> Dict[str, Any]:
    box = (box_no or "").strip()
    binding = await PackingBinding.get_or_none(
        tenant_id=tenant_id, box_no=box, deleted_at__isnull=True
    )
    if not binding:
        raise NotFoundError(f"箱号不存在: {box}")
    lines = await PackingBindingLine.filter(
        tenant_id=tenant_id,
        binding_id=binding.id,
        line_status="active",
        deleted_at__isnull=True,
    ).order_by("id")
    return {
        "binding": binding,
        "lines": lines,
    }


async def consume_boxes_core(
    svc: Any,
    tenant_id: int,
    *,
    source_type: str,
    source_id: int,
    box_nos: Optional[List[str]] = None,
    serial_numbers: Optional[List[str]] = None,
    operator_id: int,
) -> Dict[str, Any]:
    profile_svc = PackingProfileService()
    consumed_bindings: List[int] = []
    consumed_lines: List[int] = []
    now = resolve_business_datetime()

    boxes = [str(b).strip() for b in (box_nos or []) if str(b or "").strip()]
    sns = [str(s).strip() for s in (serial_numbers or []) if str(s or "").strip()]
    if not boxes and not sns:
        raise ValidationError("请提供箱码或序列号")

    async with in_transaction():
        if boxes:
            for box in boxes:
                resolved = await resolve_box_core(tenant_id, box)
                binding: PackingBinding = resolved["binding"]
                profile = await profile_svc.get_effective_profile(
                    tenant_id, material_id=int(binding.product_id)
                )
                if profile.require_sealed_for_consume and str(binding.seal_status or "").strip().lower() != "sealed":
                    raise BusinessLogicError(f"箱 {box} 须先封箱才能核销")
                if binding.consumed_at is not None:
                    raise BusinessLogicError(f"箱 {box} 已核销")
                if source_type == "sales_delivery" and int(binding.sales_delivery_id or 0) != int(source_id):
                    raise BusinessLogicError(f"箱 {box} 不属于当前销售出库单")
                if source_type == "finished_goods_receipt" and int(binding.finished_goods_receipt_id or 0) != int(source_id):
                    raise BusinessLogicError(f"箱 {box} 不属于当前成品入库单")

                binding.consumed_at = now
                await binding.save()
                consumed_bindings.append(int(binding.id))
                for line in resolved["lines"]:
                    line.line_status = "consumed"
                    line.consumed_at = now
                    await line.save()
                    consumed_lines.append(int(line.id))

        if sns:
            for sn in sns:
                line = await PackingBindingLine.filter(
                    tenant_id=tenant_id,
                    product_serial_no=sn,
                    line_status="active",
                    deleted_at__isnull=True,
                ).first()
                if not line:
                    raise NotFoundError(f"未找到有效装箱明细: {sn}")
                binding = await PackingBinding.get(id=line.binding_id, tenant_id=tenant_id)
                if source_type == "sales_delivery" and int(binding.sales_delivery_id or 0) != int(source_id):
                    raise BusinessLogicError(f"序列号 {sn} 不属于当前销售出库单")
                if source_type == "finished_goods_receipt" and int(binding.finished_goods_receipt_id or 0) != int(source_id):
                    raise BusinessLogicError(f"序列号 {sn} 不属于当前成品入库单")
                profile = await profile_svc.get_effective_profile(
                    tenant_id, material_id=int(binding.product_id)
                )
                if profile.require_sealed_for_consume and str(binding.seal_status or "").strip().lower() != "sealed":
                    raise BusinessLogicError(f"序列号 {sn} 所在箱须先封箱才能核销")

                line.line_status = "consumed"
                line.consumed_at = now
                await line.save()
                consumed_lines.append(int(line.id))
                await sync_binding_quantity_and_serials(tenant_id, binding)
                binding = await PackingBinding.get(id=binding.id)
                remaining = await PackingBindingLine.filter(
                    tenant_id=tenant_id,
                    binding_id=binding.id,
                    line_status="active",
                    deleted_at__isnull=True,
                ).count()
                if remaining == 0:
                    binding.consumed_at = now
                    await binding.save()
                    consumed_bindings.append(int(binding.id))

    return {
        "consumed_binding_ids": list(dict.fromkeys(consumed_bindings)),
        "consumed_line_ids": consumed_lines,
    }
