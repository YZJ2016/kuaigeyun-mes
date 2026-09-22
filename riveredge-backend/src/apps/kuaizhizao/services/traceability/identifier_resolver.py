"""
追溯标识解析：序列号 / 批号 / 工单号（tenant 内精确匹配，找不到则 404）

序列号真源（按优先级）：
1. 物料序列号台账 MaterialSerial（入库过账后写入）
2. 工单跟踪字段 planned_serial_no / confirmed_serial_no（开单/下达占号，入库前即存在）
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from tortoise.expressions import Q

from apps.master_data.models.material_batch import MaterialBatch
from apps.master_data.models.material_serial import MaterialSerial
from apps.kuaizhizao.models.work_order import WorkOrder
from apps.kuaizhizao.schemas.traceability_schemas import TraceIdentifierType
from infra.exceptions.exceptions import NotFoundError


@dataclass
class ResolvedTraceAnchor:
    identifier_type: TraceIdentifierType
    code: str
    tenant_id: int
    material_id: Optional[int] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    material_model: Optional[str] = None
    status: Optional[str] = None
    inbound_date: Optional[date] = None
    serial_uuid: Optional[str] = None
    batch_uuid: Optional[str] = None
    work_order_id: Optional[int] = None
    batch_no: Optional[str] = None


class TraceIdentifierResolver:
    @staticmethod
    async def _resolve_work_order_by_serial(
        tenant_id: int, serial_no: str
    ) -> Optional[WorkOrder]:
        """工单跟踪序列号精确匹配（计划号或确认号）。"""
        return (
            await WorkOrder.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
            )
            .filter(Q(planned_serial_no=serial_no) | Q(confirmed_serial_no=serial_no))
            .order_by("id")
            .first()
        )

    @staticmethod
    async def resolve(tenant_id: int, code: str) -> ResolvedTraceAnchor:
        text = (code or "").strip()
        if not text:
            raise NotFoundError("追溯码不存在")

        serial = await MaterialSerial.filter(
            tenant_id=tenant_id,
            serial_no=text,
            deleted_at__isnull=True,
        ).prefetch_related("material").first()
        if serial:
            material = serial.material
            wo = await TraceIdentifierResolver._resolve_work_order_by_serial(tenant_id, text)
            return ResolvedTraceAnchor(
                identifier_type=TraceIdentifierType.serial,
                code=text,
                tenant_id=tenant_id,
                material_id=serial.material_id,
                material_code=getattr(material, "main_code", None) if material else None,
                material_name=getattr(material, "name", None) if material else None,
                material_model=getattr(material, "model", None) if material else None,
                status=serial.status,
                inbound_date=serial.production_date,
                serial_uuid=str(serial.uuid),
                work_order_id=wo.id if wo else None,
            )

        # 工单已占号但尚未入库过账时，台账可能尚无 MaterialSerial
        wo_by_serial = await TraceIdentifierResolver._resolve_work_order_by_serial(
            tenant_id, text
        )
        if wo_by_serial:
            return ResolvedTraceAnchor(
                identifier_type=TraceIdentifierType.serial,
                code=text,
                tenant_id=tenant_id,
                material_id=getattr(wo_by_serial, "product_id", None),
                material_code=getattr(wo_by_serial, "product_code", None),
                material_name=getattr(wo_by_serial, "product_name", None),
                status=getattr(wo_by_serial, "status", None),
                work_order_id=wo_by_serial.id,
            )

        batches = await MaterialBatch.filter(
            tenant_id=tenant_id,
            batch_no=text,
            deleted_at__isnull=True,
            material__deleted_at__isnull=True,
        ).prefetch_related("material").order_by("id").all()
        if batches:
            batch = batches[0]
            material = batch.material
            return ResolvedTraceAnchor(
                identifier_type=TraceIdentifierType.batch,
                code=text,
                tenant_id=tenant_id,
                material_id=batch.material_id,
                material_code=getattr(material, "main_code", None) if material else None,
                material_name=getattr(material, "name", None) if material else None,
                material_model=getattr(material, "model", None) if material else None,
                status=batch.status,
                inbound_date=batch.production_date,
                batch_uuid=str(batch.uuid),
                batch_no=batch.batch_no,
            )

        wo = await WorkOrder.filter(
            tenant_id=tenant_id,
            code=text,
            deleted_at__isnull=True,
        ).first()
        if wo:
            return ResolvedTraceAnchor(
                identifier_type=TraceIdentifierType.work_order,
                code=text,
                tenant_id=tenant_id,
                material_id=getattr(wo, "product_id", None),
                material_code=getattr(wo, "product_code", None),
                material_name=getattr(wo, "product_name", None),
                work_order_id=wo.id,
            )

        raise NotFoundError(f"未找到追溯码: {text}")

    @staticmethod
    async def resolve_serial_uuid(tenant_id: int, serial_uuid: str) -> ResolvedTraceAnchor:
        serial = await MaterialSerial.filter(
            tenant_id=tenant_id,
            uuid=serial_uuid,
            deleted_at__isnull=True,
        ).prefetch_related("material").first()
        if not serial:
            raise NotFoundError("物料序列号", serial_uuid)
        material = serial.material
        wo = await TraceIdentifierResolver._resolve_work_order_by_serial(
            tenant_id, serial.serial_no
        )
        return ResolvedTraceAnchor(
            identifier_type=TraceIdentifierType.serial,
            code=serial.serial_no,
            tenant_id=tenant_id,
            material_id=serial.material_id,
            material_code=getattr(material, "main_code", None) if material else None,
            material_name=getattr(material, "name", None) if material else None,
            material_model=getattr(material, "model", None) if material else None,
            status=serial.status,
            inbound_date=serial.production_date,
            serial_uuid=str(serial.uuid),
            work_order_id=wo.id if wo else None,
        )

    @staticmethod
    async def resolve_batch_uuid(tenant_id: int, batch_uuid: str) -> ResolvedTraceAnchor:
        batch = await MaterialBatch.filter(
            tenant_id=tenant_id,
            uuid=batch_uuid,
            deleted_at__isnull=True,
            material__deleted_at__isnull=True,
        ).prefetch_related("material").first()
        if not batch:
            raise NotFoundError("物料批号", batch_uuid)
        material = batch.material
        return ResolvedTraceAnchor(
            identifier_type=TraceIdentifierType.batch,
            code=batch.batch_no,
            tenant_id=tenant_id,
            material_id=batch.material_id,
            material_code=getattr(material, "main_code", None) if material else None,
            material_name=getattr(material, "name", None) if material else None,
            material_model=getattr(material, "model", None) if material else None,
            status=batch.status,
            inbound_date=batch.production_date,
            batch_uuid=str(batch.uuid),
            batch_no=batch.batch_no,
        )
