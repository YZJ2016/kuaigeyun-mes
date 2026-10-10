"""快数采 IoT 设备服务。"""

from __future__ import annotations

import secrets
from typing import Optional

from apps.kuaizhizao.services.equipment_service import EquipmentService
from apps.kuaiiot.constants import DEVICE_BATCH_MAX
from apps.kuaiiot.models.iot import IotDevice, IotTagSnapshot
from apps.kuaiiot.schemas.iot import (
    DeviceBatchCreate,
    DeviceBatchItemResponse,
    DeviceBatchResponse,
    DeviceCreate,
    DeviceUpdate,
    TagHistoryResponse,
)
from apps.kuaiiot.services.device_group_service import DeviceGroupService
from apps.kuaiiot.services.product_service import ProductService
from apps.kuaiiot.services.tag_apply_helper import apply_tag_definitions_to_device
from apps.kuaiiot.services.tag_history_store import TagHistoryStore
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class DeviceService:
    @staticmethod
    async def list_devices(
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        q: Optional[str] = None,
        connection_id: Optional[int] = None,
        group_id: Optional[int] = None,
        is_online: Optional[bool] = None,
    ) -> tuple[list[IotDevice], int]:
        query = IotDevice.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if q:
            query = query.filter(name__icontains=q)
        if connection_id is not None:
            query = query.filter(connection_id=connection_id)
        if group_id is not None:
            query = query.filter(group_id=group_id)
        if is_online is not None:
            query = query.filter(is_online=is_online)
        total = await query.count()
        items = await query.order_by("-created_at", "-id").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotDevice:
        item = await IotDevice.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"IoT 设备不存在: {uuid}")
        return item

    @staticmethod
    async def get_by_token(device_token: str) -> IotDevice:
        item = await IotDevice.filter(device_token=device_token, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError("无效的设备 token")
        return item

    @staticmethod
    async def _validate_equipment(tenant_id: int, equipment_uuid: Optional[str]) -> None:
        if equipment_uuid:
            await EquipmentService.get_equipment_by_uuid(tenant_id, equipment_uuid)

    @staticmethod
    async def _apply_initial_tags(tenant_id: int, device: IotDevice, tag_template_code: Optional[str]) -> None:
        if tag_template_code:
            from apps.kuaiiot.services.tag_template_service import TagTemplateService

            await TagTemplateService.apply_template_for_device_id(tenant_id, device, tag_template_code)
            return
        if not device.product_id:
            return
        product = await ProductService.get_by_id(tenant_id, device.product_id)
        tags = product.tags if isinstance(product.tags, list) else []
        await apply_tag_definitions_to_device(tenant_id, device, tags)

    @staticmethod
    async def create(tenant_id: int, data: DeviceCreate) -> IotDevice:
        exists = await IotDevice.filter(
            tenant_id=tenant_id, code=data.code, deleted_at__isnull=True
        ).exists()
        if exists:
            raise ValidationError(f"设备编码已存在: {data.code}")
        await DeviceService._validate_equipment(tenant_id, data.equipment_uuid)
        if data.group_id is not None:
            await DeviceGroupService.validate_group_id(tenant_id, data.group_id)
        payload = data.model_dump(exclude={"tag_template_code"})
        device = await IotDevice.create(
            tenant_id=tenant_id,
            device_token=secrets.token_urlsafe(32),
            **payload,
        )
        await DeviceService._apply_initial_tags(tenant_id, device, data.tag_template_code)
        return device

    @staticmethod
    async def batch_create(tenant_id: int, data: DeviceBatchCreate) -> DeviceBatchResponse:
        if data.count > DEVICE_BATCH_MAX:
            raise ValidationError(f"单次批量创建设备最多 {DEVICE_BATCH_MAX} 台")
        product = await ProductService.get_by_id(tenant_id, data.product_id)
        code_prefix = (data.code_prefix or data.name_prefix).strip() or "IOT"
        items: list[DeviceBatchItemResponse] = []
        for i in range(1, data.count + 1):
            code = f"{code_prefix}-{i:03d}"
            name = f"{data.name_prefix}{i:02d}"
            device = await DeviceService.create(
                tenant_id,
                DeviceCreate(
                    code=code,
                    name=name,
                    external_device_id=f"{code_prefix.lower()}-{i:03d}",
                    connection_id=data.connection_id,
                    product_id=product.id,
                    group_id=data.group_id,
                    equipment_uuid=data.equipment_uuid,
                    remark=data.remark,
                ),
            )
            items.append(
                DeviceBatchItemResponse(
                    uuid=device.uuid,
                    code=device.code,
                    name=device.name,
                    device_token=device.device_token,
                )
            )
        return DeviceBatchResponse(items=items, total=len(items))

    @staticmethod
    async def update(tenant_id: int, uuid: str, data: DeviceUpdate) -> IotDevice:
        item = await DeviceService.get_by_uuid(tenant_id, uuid)
        payload = data.model_dump(exclude_unset=True)
        if "equipment_uuid" in payload:
            await DeviceService._validate_equipment(tenant_id, payload["equipment_uuid"])
        if "group_id" in payload:
            await DeviceGroupService.validate_group_id(tenant_id, payload.get("group_id"))
        for key, value in payload.items():
            setattr(item, key, value)
        await item.save()
        return item

    @staticmethod
    async def delete(tenant_id: int, uuid: str) -> None:
        item = await DeviceService.get_by_uuid(tenant_id, uuid)
        item.deleted_at = resolve_business_datetime()
        await item.save()

    @staticmethod
    async def rotate_token(tenant_id: int, uuid: str) -> IotDevice:
        item = await DeviceService.get_by_uuid(tenant_id, uuid)
        item.device_token = secrets.token_urlsafe(32)
        await item.save()
        return item

    @staticmethod
    async def list_snapshots(tenant_id: int, device_id: int) -> list[IotTagSnapshot]:
        return await IotTagSnapshot.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            deleted_at__isnull=True,
        ).order_by("tag_key")

    @staticmethod
    async def list_history(
        tenant_id: int,
        device_id: int,
        tag_key: Optional[str] = None,
        limit: int = 100,
    ) -> list[TagHistoryResponse]:
        if not await TagHistoryStore.is_configured(tenant_id):
            return []
        return await TagHistoryStore.query_history(
            tenant_id=tenant_id,
            device_id=device_id,
            tag_key=tag_key,
            limit=limit,
        )
