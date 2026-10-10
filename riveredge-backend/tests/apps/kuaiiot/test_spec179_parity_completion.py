"""运营页面补齐：原子建机、内置产品与平台设备发现。"""
import pytest
from unittest.mock import AsyncMock

from apps.kuaiiot.models.device import KuaiiotDevice
from apps.kuaiiot.models.group import KuaiiotDeviceGroup
from apps.kuaiiot.models.product import KuaiiotProduct
from apps.kuaiiot.models.tag import KuaiiotTagDefinition
from apps.kuaiiot.schemas.control import DeviceCreate
from apps.kuaiiot.schemas.product import ProductCreate
from apps.kuaiiot.services import control_service, product_service
from infra.domain.tenant_context import set_current_tenant_id
from infra.exceptions.exceptions import ValidationError


async def product(tenant=1):
    return await product_service.create_product(tenant, ProductCreate(code="oven", name="炉", tags=[
        {"tag_key": "temperature", "name": "炉温", "map_target": "temperature", "fill_target": "spot_check.temp"}
    ]))


@pytest.mark.asyncio
async def test_single_device_product_group_and_tags(db):
    set_current_tenant_id(1)
    model = await product()
    group = await KuaiiotDeviceGroup.create(tenant_id=1, code="g", name="组")
    device = await control_service.create_device(1, DeviceCreate(
        code="d", name="设备", external_device_id="remote", product_id=model.id, group_id=group.id,
        template_code="generic_line",
    ), user_id=7)
    assert (device.product_id, device.group_id) == (model.id, group.id)
    tags = await KuaiiotTagDefinition.filter(tenant_id=1, device_id=device.id)
    assert len(tags) == 5
    temperature = next(tag for tag in tags if tag.tag_key == "temperature")
    assert temperature.name == "炉温"
    assert temperature.fill_target == "spot_check.temp"
    assert temperature.created_by == 7


@pytest.mark.asyncio
async def test_single_device_tag_failure_rolls_back(db, monkeypatch):
    set_current_tenant_id(1)
    model = await product()
    monkeypatch.setattr(KuaiiotTagDefinition, "create", AsyncMock(side_effect=RuntimeError("test failure")))
    with pytest.raises(RuntimeError):
        await control_service.create_device(1, DeviceCreate(code="d", name="D", external_device_id="x", product_id=model.id))
    assert await KuaiiotDevice.all().count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["product_id", "group_id"])
async def test_single_device_rejects_foreign_associations(db, field):
    set_current_tenant_id(2)
    model = await product(2)
    group = await KuaiiotDeviceGroup.create(tenant_id=2, code="g", name="组")
    set_current_tenant_id(1)
    with pytest.raises(ValidationError):
        await control_service.create_device(1, DeviceCreate(code="d", name="D", external_device_id="x",
            **{field: model.id if field == "product_id" else group.id}))
    assert await KuaiiotDevice.all().count() == 0


@pytest.mark.asyncio
async def test_builtin_load_idempotent_preserves_edits_and_deleted_codes(db):
    set_current_tenant_id(1)
    first = await product_service.load_builtin_products(1, user_id=7)
    assert first == {"created": 4, "skipped": 0}
    row = await KuaiiotProduct.get(tenant_id=1, code="generic_line")
    row.name = "用户修改"
    await row.save()
    deleted = await KuaiiotProduct.get(tenant_id=1, code="cnc")
    await product_service.delete_product(1, deleted.id)
    assert await product_service.load_builtin_products(1) == {"created": 0, "skipped": 4}
    assert (await KuaiiotProduct.get(id=row.id)).name == "用户修改"
    assert (await KuaiiotProduct.get(id=deleted.id)).deleted_at is not None
    set_current_tenant_id(2)
    assert await product_service.load_builtin_products(2) == {"created": 4, "skipped": 0}


@pytest.mark.asyncio
async def test_builtin_failure_rolls_back_all(db, monkeypatch):
    set_current_tenant_id(1)
    original = product_service.create_product
    async def fail_second(*args, **kwargs):
        if args[1].code == "injection_molding":
            raise RuntimeError("test failure")
        return await original(*args, **kwargs)
    monkeypatch.setattr(product_service, "create_product", fail_second)
    with pytest.raises(RuntimeError):
        await product_service.load_builtin_products(1)
    assert await KuaiiotProduct.all().count() == 0
