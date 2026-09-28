"""设备分组。只改 IoT 设备的 group_id，不写星制造设备台账。"""

from __future__ import annotations

from typing import Optional

from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.group import KuaiiotDeviceGroup
from infra.domain.tenant_context import TenantContextError, get_current_tenant_id
from infra.exceptions.exceptions import NotFoundError, ValidationError


def _require_tenant(explicit: int) -> int:
    current = get_current_tenant_id()
    if current is None:
        raise TenantContextError("组织上下文未设置")
    if int(current) != int(explicit):
        raise ValidationError("租户上下文不匹配")
    return int(current)


async def _assert_parent(tenant_id: int, parent_id: Optional[int], self_id: Optional[int] = None) -> None:
    if parent_id is None:
        return
    if self_id is not None and int(parent_id) == int(self_id):
        raise ValidationError("分组不能以自己为上级")
    seen: set[int] = set()
    current: Optional[int] = int(parent_id)
    while current is not None:
        if current in seen or (self_id is not None and current == int(self_id)):
            raise ValidationError("分组上级形成循环")
        seen.add(current)
        parent = await KuaiiotDeviceGroup.filter(
            tenant_id=tenant_id,
            id=current,
            deleted_at__isnull=True,
        ).first()
        if parent is None:
            raise ValidationError("上级分组不属于当前租户")
        current = parent.parent_id
        if len(seen) > 32:
            raise ValidationError("分组层级过深")


async def create_group(
    tenant_id: int,
    *,
    code: str,
    name: str,
    parent_id: Optional[int] = None,
    sort_order: int = 0,
    remark: Optional[str] = None,
    user_id: Optional[int] = None,
) -> KuaiiotDeviceGroup:
    tid = _require_tenant(tenant_id)
    text = (code or "").strip()
    title = (name or "").strip()
    if not text or not title:
        raise ValidationError("分组编码和名称不能为空")
    if isinstance(sort_order, bool) or not isinstance(sort_order, int):
        raise ValidationError("sort_order 无效")
    if await KuaiiotDeviceGroup.filter(tenant_id=tid, code=text, deleted_at__isnull=True).exists():
        raise ValidationError("分组编码已存在")
    await _assert_parent(tid, parent_id)
    return await KuaiiotDeviceGroup.create(
        tenant_id=tid,
        code=text,
        name=title,
        parent_id=parent_id,
        sort_order=sort_order,
        remark=remark,
        created_by=user_id,
        updated_by=user_id,
    )


async def list_groups(tenant_id: int) -> list[KuaiiotDeviceGroup]:
    tid = _require_tenant(tenant_id)
    return await KuaiiotDeviceGroup.filter(tenant_id=tid, deleted_at__isnull=True).order_by("sort_order", "id")


async def update_group(
    tenant_id: int,
    group_id: int,
    *,
    name: Optional[str] = None,
    parent_id: Optional[int] = None,
    parent_set: bool = False,
    sort_order: Optional[int] = None,
    remark: Optional[str] = None,
    user_id: Optional[int] = None,
) -> KuaiiotDeviceGroup:
    tid = _require_tenant(tenant_id)
    row = await KuaiiotDeviceGroup.filter(tenant_id=tid, id=group_id, deleted_at__isnull=True).first()
    if row is None:
        raise NotFoundError("分组不存在")
    if name is not None:
        title = name.strip()
        if not title:
            raise ValidationError("分组名称不能为空")
        row.name = title
    if sort_order is not None:
        if isinstance(sort_order, bool) or not isinstance(sort_order, int):
            raise ValidationError("sort_order 无效")
        row.sort_order = sort_order
    if remark is not None:
        row.remark = remark
    if parent_set:
        await _assert_parent(tid, parent_id, self_id=row.id)
        row.parent_id = parent_id
    row.updated_by = user_id
    await row.save()
    return row


async def assign_device_group(
    tenant_id: int,
    device_id: int,
    group_id: Optional[int],
    *,
    user_id: Optional[int] = None,
) -> KuaiiotDevice:
    tid = _require_tenant(tenant_id)
    device = await KuaiiotDevice.filter(tenant_id=tid, id=device_id, deleted_at__isnull=True).first()
    if device is None:
        raise NotFoundError("设备不存在")
    if group_id is not None:
        group = await KuaiiotDeviceGroup.filter(tenant_id=tid, id=group_id, deleted_at__isnull=True).first()
        if group is None:
            raise ValidationError("分组不属于当前租户")
    device.group_id = group_id
    device.updated_by = user_id
    await device.save(update_fields=["group_id", "updated_by", "updated_at"])
    return device
