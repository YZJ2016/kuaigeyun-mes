"""快数采点位定义服务。"""

from __future__ import annotations

from typing import Optional

from apps.kuaiiot.constants import FILL_TARGET_PREFIXES, MAP_TARGETS, TAG_VALUE_TYPES
from apps.kuaiiot.models.iot import IotDevice, IotTagDefinition
from apps.kuaiiot.schemas.iot import TagDefinitionCreate, TagDefinitionUpdate
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class TagService:
    @staticmethod
    def _validate_map_target(map_target: str) -> None:
        if map_target in MAP_TARGETS:
            return
        if map_target.startswith("other_parameters."):
            suffix = map_target.split(".", 1)[1]
            if suffix:
                return
        raise ValidationError(f"无效的映射目标: {map_target}")

    @staticmethod
    async def list_tags(
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        device_id: Optional[int] = None,
        q: Optional[str] = None,
    ) -> tuple[list[IotTagDefinition], int]:
        query = IotTagDefinition.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if device_id is not None:
            query = query.filter(device_id=device_id)
        if q:
            query = query.filter(name__icontains=q)
        total = await query.count()
        items = await query.order_by("device_id", "tag_key").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotTagDefinition:
        item = await IotTagDefinition.filter(
            tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True
        ).first()
        if not item:
            raise NotFoundError(f"点位不存在: {uuid}")
        return item

    @staticmethod
    async def create(tenant_id: int, data: TagDefinitionCreate) -> IotTagDefinition:
        if data.value_type not in TAG_VALUE_TYPES:
            raise ValidationError(f"无效的值类型: {data.value_type}")
        TagService._validate_map_target(data.map_target)

        device = await IotDevice.filter(
            id=data.device_id, tenant_id=tenant_id, deleted_at__isnull=True
        ).first()
        if not device:
            raise NotFoundError(f"IoT 设备不存在: {data.device_id}")

        exists = await IotTagDefinition.filter(
            tenant_id=tenant_id,
            device_id=data.device_id,
            tag_key=data.tag_key,
            deleted_at__isnull=True,
        ).exists()
        if exists:
            raise ValidationError(f"点位 key 已存在: {data.tag_key}")
        return await IotTagDefinition.create(tenant_id=tenant_id, **data.model_dump())

    @staticmethod
    async def update(tenant_id: int, uuid: str, data: TagDefinitionUpdate) -> IotTagDefinition:
        item = await TagService.get_by_uuid(tenant_id, uuid)
        payload = data.model_dump(exclude_unset=True)
        if "value_type" in payload and payload["value_type"] not in TAG_VALUE_TYPES:
            raise ValidationError(f"无效的值类型: {payload['value_type']}")
        if "map_target" in payload:
            TagService._validate_map_target(payload["map_target"])
        for key, value in payload.items():
            setattr(item, key, value)
        await item.save()
        return item

    @staticmethod
    async def delete(tenant_id: int, uuid: str) -> None:
        item = await TagService.get_by_uuid(tenant_id, uuid)
        item.deleted_at = resolve_business_datetime()
        await item.save()


# ---- 星数采本地执行版：点位映射与预填目标校验 ----

_LOCAL_MONITOR_COLUMNS = (
    "status",
    "is_online",
    "temperature",
    "pressure",
    "vibration",
    "other_parameters",
)
_LOCAL_OTHER_PARAMETERS_PREFIX = "other_parameters."
_LOCAL_FILL_PREFIXES = ("sop_parameters.", "spot_check.")


def _validate_map_target(map_target: str) -> str:
    text = (map_target or "").strip()
    if text in _LOCAL_MONITOR_COLUMNS:
        return text
    if text.startswith(_LOCAL_OTHER_PARAMETERS_PREFIX):
        key = text[len(_LOCAL_OTHER_PARAMETERS_PREFIX) :]
        if key and "." not in key and key.replace("_", "").isalnum():
            return text
    raise ValidationError("点位只能映射到监控字段")


def _validate_fill_target(fill_target: Optional[str]) -> Optional[str]:
    if fill_target is None:
        return None
    text = str(fill_target).strip()
    if not text:
        return None
    for prefix in _LOCAL_FILL_PREFIXES:
        suffix = text[len(prefix) :] if text.startswith(prefix) else ""
        if suffix and " " not in suffix and "." not in suffix:
            return text
    raise ValidationError("fill_target 仅允许 sop_parameters.* 或 spot_check.*")


# 本地测试与旧代码按类属性调用校验器
TagService._validate_fill_target = staticmethod(_validate_fill_target)
