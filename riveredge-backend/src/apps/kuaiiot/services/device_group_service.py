"""快数采设备分组服务。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaiiot.models.iot import IotDevice, IotDeviceGroup
from apps.kuaiiot.schemas.iot import DeviceGroupCreate, DeviceGroupTreeNode, DeviceGroupUpdate
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class DeviceGroupService:
    @staticmethod
    async def list_groups(tenant_id: int) -> list[IotDeviceGroup]:
        return await IotDeviceGroup.filter(tenant_id=tenant_id, deleted_at__isnull=True).order_by(
            "sort_order", "name"
        )

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotDeviceGroup:
        item = await IotDeviceGroup.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"设备分组不存在: {uuid}")
        return item

    @staticmethod
    async def _validate_parent(tenant_id: int, parent_id: Optional[int], self_id: Optional[int] = None) -> None:
        if parent_id is None:
            return
        if self_id is not None and parent_id == self_id:
            raise ValidationError("分组不能设置自身为父分组")
        parent = await IotDeviceGroup.filter(
            tenant_id=tenant_id, id=parent_id, deleted_at__isnull=True
        ).first()
        if not parent:
            raise ValidationError(f"父分组不存在: {parent_id}")

    @staticmethod
    async def create(tenant_id: int, data: DeviceGroupCreate) -> IotDeviceGroup:
        exists = await IotDeviceGroup.filter(tenant_id=tenant_id, code=data.code, deleted_at__isnull=True).exists()
        if exists:
            raise ValidationError(f"分组编码已存在: {data.code}")
        await DeviceGroupService._validate_parent(tenant_id, data.parent_id)
        return await IotDeviceGroup.create(tenant_id=tenant_id, **data.model_dump())

    @staticmethod
    async def update(tenant_id: int, uuid: str, data: DeviceGroupUpdate) -> IotDeviceGroup:
        item = await DeviceGroupService.get_by_uuid(tenant_id, uuid)
        payload = data.model_dump(exclude_unset=True)
        if "parent_id" in payload:
            await DeviceGroupService._validate_parent(tenant_id, payload["parent_id"], self_id=item.id)
        for key, value in payload.items():
            setattr(item, key, value)
        await item.save()
        return item

    @staticmethod
    async def delete(tenant_id: int, uuid: str) -> None:
        item = await DeviceGroupService.get_by_uuid(tenant_id, uuid)
        child_exists = await IotDeviceGroup.filter(
            tenant_id=tenant_id, parent_id=item.id, deleted_at__isnull=True
        ).exists()
        if child_exists:
            raise ValidationError("存在子分组，无法删除")
        device_exists = await IotDevice.filter(
            tenant_id=tenant_id, group_id=item.id, deleted_at__isnull=True
        ).exists()
        if device_exists:
            raise ValidationError("分组下仍有设备，无法删除")
        item.deleted_at = resolve_business_datetime()
        await item.save()

    @staticmethod
    def build_tree(groups: list[IotDeviceGroup]) -> list[DeviceGroupTreeNode]:
        by_parent: dict[Optional[int], list[IotDeviceGroup]] = {}
        for group in groups:
            by_parent.setdefault(group.parent_id, []).append(group)

        def walk(parent_id: Optional[int]) -> list[DeviceGroupTreeNode]:
            nodes: list[DeviceGroupTreeNode] = []
            for group in by_parent.get(parent_id, []):
                nodes.append(
                    DeviceGroupTreeNode(
                        uuid=group.uuid,
                        id=group.id,
                        code=group.code,
                        name=group.name,
                        parent_id=group.parent_id,
                        sort_order=group.sort_order,
                        remark=group.remark,
                        children=walk(group.id),
                    )
                )
            return nodes

        return walk(None)

    @staticmethod
    async def validate_group_id(tenant_id: int, group_id: Optional[int]) -> None:
        if group_id is None:
            return
        exists = await IotDeviceGroup.filter(tenant_id=tenant_id, id=group_id, deleted_at__isnull=True).exists()
        if not exists:
            raise ValidationError(f"设备分组不存在: {group_id}")
