"""IoT 设备 MES 绑定唯一性单元测试。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaiiot.schemas.iot import DeviceBatchCreate, DeviceCreate
from apps.kuaiiot.services.device_service import DeviceService
from infra.exceptions.exceptions import ValidationError


@pytest.mark.asyncio
async def test_validate_equipment_unique_bind():
    conflict = MagicMock()
    conflict.code = "IOT-001"

    filter_qs = MagicMock()
    filter_qs.exclude = MagicMock(return_value=filter_qs)
    filter_qs.first = AsyncMock(return_value=conflict)

    with patch(
        "apps.kuaiiot.services.device_service.EquipmentService.get_equipment_by_uuid",
        new=AsyncMock(return_value=MagicMock()),
    ), patch(
        "apps.kuaiiot.services.device_service.IotDevice.filter",
        return_value=filter_qs,
    ):
        with pytest.raises(ValidationError, match="已绑定"):
            await DeviceService._validate_equipment(1, "eq-uuid-1", exclude_device_id=9)


@pytest.mark.asyncio
async def test_batch_create_rejects_shared_equipment_uuid():
    with pytest.raises(ValidationError, match="不能共用"):
        await DeviceService.batch_create(
            1,
            DeviceBatchCreate(
                count=2,
                name_prefix="线边",
                product_id=1,
                equipment_uuid="eq-shared",
            ),
        )


@pytest.mark.asyncio
async def test_create_calls_unique_equipment_validation():
    with patch(
        "apps.kuaiiot.services.device_service.IotDevice.filter",
        return_value=AsyncMock(exists=AsyncMock(return_value=False)),
    ), patch(
        "apps.kuaiiot.services.device_service.DeviceService._validate_equipment",
        new=AsyncMock(),
    ) as mock_validate, patch(
        "apps.kuaiiot.services.device_service.IotDevice.create",
        new=AsyncMock(return_value=MagicMock(id=1, uuid="d1")),
    ), patch(
        "apps.kuaiiot.services.device_service.DeviceService._apply_initial_tags",
        new=AsyncMock(),
    ):
        await DeviceService.create(
            1,
            DeviceCreate(
                code="IOT-A",
                name="A",
                external_device_id="ext-a",
                equipment_uuid="eq-1",
            ),
        )
        mock_validate.assert_awaited()
