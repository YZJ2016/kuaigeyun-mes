"""KR-PG1：入库读仓库管理标志失败必须拒绝；出库读失败仍原样冒泡。"""

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.services.inventory_service import InventoryService
from infra.exceptions.exceptions import BusinessLogicError


@asynccontextmanager
async def _noop_tx():
    conn = MagicMock()
    conn.execute_query = AsyncMock(return_value=None)
    yield conn


def _dedup_miss_queryset():
    qs = MagicMock()
    qs.using_db = MagicMock(return_value=qs)
    qs.values_list = AsyncMock(return_value=[])
    return qs


def _managed_material():
    material = MagicMock()
    material.batch_managed = True
    material.serial_managed = True
    material.name = "螺丝"
    material.code = "M1"
    material.main_code = "M1"
    material.uuid = "mat-uuid"
    return material


def _posting_patches(*, flags):
    wh = MagicMock()
    wh.warehouse_type = "normal"
    wh.name = "主仓"
    return (
        patch(
            "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction",
            _noop_tx,
        ),
        patch(
            "apps.kuaizhizao.models.material_stock_movement.MaterialStockMovement.filter",
            MagicMock(return_value=_dedup_miss_queryset()),
        ),
        patch(
            "apps.master_data.models.warehouse.Warehouse.get_or_none",
            new=AsyncMock(return_value=wh),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._get_warehouse_management_flags",
            new=flags,
        ),
        patch(
            "apps.master_data.models.material.Material.get_or_none",
            new=AsyncMock(return_value=_managed_material()),
        ),
        patch(
            "apps.master_data.services.material_batch_service.MaterialBatchService.generate_batch_no",
            new=AsyncMock(return_value="B1"),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._find_in_stock_material_batch",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._resolve_warehouse_name",
            new=AsyncMock(return_value="主仓"),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._material_batch_increase_or_restore",
            new=AsyncMock(),
        ),
        patch(
            "apps.kuaizhizao.services.inventory_service.InventoryService._record_stock_movement",
            new=AsyncMock(),
        ),
        patch(
            "apps.kuaizhizao.services.work_order_readiness_service.notify_inventory_changed",
            return_value=None,
        ),
    )


async def _increase():
    return await InventoryService._increase_stock_no_atomic(
        tenant_id=1,
        material_id=10,
        quantity=Decimal("1"),
        warehouse_id=2,
        ledger_production_date=date(2026, 1, 1),
        movement_type="purchase_inbound",
        source_type="purchase_inbound",
        source_doc_id=1,
        operator_id=1,
        operator_name="tester",
        idempotency_key="test:kr-pg1:increase",
    )


@pytest.mark.asyncio
async def test_increase_rejects_when_warehouse_flags_unreadable():
    secret = "postgres://user:secret@10.0.0.1/mes"
    flags = AsyncMock(side_effect=ConnectionError(secret))
    patches = _posting_patches(flags=flags)
    material_get = patches[4].new
    record = patches[8].new
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
        with pytest.raises(BusinessLogicError) as raised:
            await _increase()

    message = str(raised.value)
    assert message == "读取仓库批号或序列号管理开关失败，拒绝本笔入库"
    assert raised.value.__cause__ is None
    assert "postgres://" not in message
    assert "secret" not in message
    assert "10.0.0.1" not in message
    # 采购入库确认：__cause__ 为空时原样再抛，客户端拿到业务文案而不是读库异常
    propagated = raised.value.__cause__ if raised.value.__cause__ is not None else raised.value
    assert type(propagated) is BusinessLogicError
    assert str(propagated) == "读取仓库批号或序列号管理开关失败，拒绝本笔入库"
    material_get.assert_not_called()
    record.assert_not_called()


@pytest.mark.asyncio
async def test_increase_skips_forced_batch_serial_when_both_flags_false():
    flags = AsyncMock(return_value=(False, False))
    patches = _posting_patches(flags=flags)
    record = patches[8].new
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
        ok = await _increase()

    assert ok is True
    record.assert_awaited()


@pytest.mark.asyncio
async def test_decrease_bubbles_warehouse_flag_read_failure():
    secret = "postgres://user:secret@10.0.0.1/mes"
    wh = MagicMock()
    wh.warehouse_type = "normal"
    material_get = AsyncMock()
    with patch(
        "apps.kuaizhizao.utils.stock_posting.reuse_or_begin_transaction",
        _noop_tx,
    ), patch(
        "apps.kuaizhizao.models.material_stock_movement.MaterialStockMovement.filter",
        MagicMock(return_value=_dedup_miss_queryset()),
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService._get_allow_negative_inventory",
        new=AsyncMock(return_value=True),
    ), patch(
        "apps.master_data.models.warehouse.Warehouse.get_or_none",
        new=AsyncMock(return_value=wh),
    ), patch(
        "apps.kuaizhizao.services.inventory_service.InventoryService._get_warehouse_management_flags",
        new=AsyncMock(side_effect=ConnectionError(secret)),
    ), patch(
        "apps.master_data.models.material.Material.get_or_none",
        new=material_get,
    ):
        with pytest.raises(ConnectionError) as raised:
            await InventoryService._decrease_stock_no_atomic(
                tenant_id=1,
                material_id=10,
                quantity=Decimal("1"),
                warehouse_id=2,
                movement_type="sales_delivery",
                source_type="sales_delivery",
                source_doc_id=1,
                operator_id=1,
                operator_name="tester",
                idempotency_key="test:kr-pg1:decrease",
            )

    assert type(raised.value) is ConnectionError
    assert secret in str(raised.value)
    material_get.assert_not_called()
