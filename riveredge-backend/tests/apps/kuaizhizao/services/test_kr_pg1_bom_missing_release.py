"""KR-PG1：没有 BOM 时下达缺料检查必须拒绝；开工等路径仍只看 has_shortage。"""

from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.schemas.work_order import MaterialShortageResponse
from apps.kuaizhizao.services.work_order_service import WorkOrderService
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError


@asynccontextmanager
async def _noop_tx():
    yield None


def _work_order():
    return SimpleNamespace(
        id=7,
        status="draft",
        code="WO-1",
        name="测试工单",
        product_id=3,
        product_name="成品",
        quantity=Decimal("2"),
        variant_attributes=None,
        configurable_selections=None,
        created_by=1,
        planned_start_date=None,
    )


def _requirement(**overrides):
    payload = dict(
        issue_method="pick",
        component_type="Make",
        component_id=9,
        component_code="C1",
        component_name="零件",
        net_requirement=Decimal("10"),
        unit="个",
    )
    payload.update(overrides)
    return SimpleNamespace(**payload)


@pytest.mark.asyncio
async def test_check_material_shortage_marks_missing_bom_without_shortage():
    wo = _work_order()
    service = WorkOrderService()
    service.get_by_id = AsyncMock(return_value=wo)
    with patch(
        "apps.kuaizhizao.services.work_order_service.calculate_material_requirements_from_bom",
        new=AsyncMock(side_effect=NotFoundError("产品没有BOM")),
    ):
        result = await service.check_material_shortage(tenant_id=1, work_order_id=7)

    assert result["bom_missing"] is True
    assert result["has_shortage"] is False
    assert result["shortage_items"] == []
    assert result["total_shortage_count"] == 0
    response = MaterialShortageResponse(**result)
    assert response.has_shortage is False
    assert "bom_missing" not in response.model_dump()


@pytest.mark.asyncio
async def test_check_material_shortage_with_bom_keeps_shortage_shape():
    wo = _work_order()
    service = WorkOrderService()
    service.get_by_id = AsyncMock(return_value=wo)
    requirements = [
        _requirement(component_type="Service", component_id=1, component_name="服务"),
        _requirement(),
    ]
    with patch(
        "apps.kuaizhizao.services.work_order_service.calculate_material_requirements_from_bom",
        new=AsyncMock(return_value=requirements),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.get_material_available_quantity",
        new=AsyncMock(return_value=Decimal("3")),
    ) as available:
        result = await service.check_material_shortage(tenant_id=1, work_order_id=7)

    assert result["bom_missing"] is False
    assert result["has_shortage"] is True
    assert result["total_shortage_count"] == 1
    assert result["shortage_items"] == [
        {
            "material_id": 9,
            "material_code": "C1",
            "material_name": "零件",
            "required_quantity": 10.0,
            "available_quantity": 3.0,
            "shortage_quantity": 7.0,
            "unit": "个",
        }
    ]
    available.assert_awaited_once()


def _config(block_level: int):
    cfg = MagicMock()
    cfg.check_audit_required = AsyncMock(return_value=False)
    cfg.get_material_shortage_block_level = AsyncMock(return_value=block_level)
    return cfg


def _timing():
    timing = MagicMock()
    timing.record_node_end = AsyncMock()
    timing.record_node_start = AsyncMock()
    return timing


async def _release(service, *, check_shortage=True, block_level=1, shortage=None):
    wo = _work_order()
    service.get_by_id = AsyncMock(return_value=wo)
    service.check_material_shortage = AsyncMock(return_value=shortage or {})
    service.update_with_user = AsyncMock(return_value=wo)
    service.get_user_info = AsyncMock(return_value={"name": "下达人"})
    service._ensure_planned_outsource_drafts = AsyncMock()
    service.get_work_order_by_id = AsyncMock(return_value=SimpleNamespace(status="released"))
    with patch(
        "apps.kuaizhizao.services.work_order_service.in_transaction",
        _noop_tx,
    ), patch(
        "apps.kuaizhizao.services.work_order_service.BusinessConfigService",
        return_value=_config(block_level),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.assert_work_order_capability",
    ), patch(
        "apps.kuaizhizao.services.work_order_service.Material.get_or_none",
        new=AsyncMock(return_value=None),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.DocumentTimingService",
        return_value=_timing(),
    ), patch(
        "apps.kuaizhizao.services.kuaizhizao_business_notification.dispatch_kuaizhizao_notification",
        new=AsyncMock(),
    ):
        result = await service.release_work_order(
            tenant_id=1,
            work_order_id=7,
            released_by=2,
            check_shortage=check_shortage,
        )
    return wo, result


@pytest.mark.asyncio
async def test_release_rejects_missing_bom_when_release_block_applies():
    service = WorkOrderService()
    with pytest.raises(BusinessLogicError, match="没有BOM") as raised:
        await _release(
            service,
            shortage={
                "has_shortage": False,
                "bom_missing": True,
                "shortage_items": [],
                "total_shortage_count": 0,
            },
        )

    assert "postgres://" not in str(raised.value)
    assert "/" not in str(raised.value)
    service.update_with_user.assert_not_called()
    assert service.get_by_id.return_value.status == "draft"


@pytest.mark.asyncio
async def test_release_keeps_shortage_rejection_when_bom_exists():
    service = WorkOrderService()
    with pytest.raises(BusinessLogicError, match="工单存在缺料，无法下达"):
        await _release(
            service,
            shortage={
                "has_shortage": True,
                "bom_missing": False,
                "shortage_items": [
                    {
                        "material_name": "零件",
                        "shortage_quantity": 7.0,
                        "unit": "个",
                    }
                ],
                "total_shortage_count": 1,
            },
        )

    service.update_with_user.assert_not_called()


@pytest.mark.asyncio
async def test_release_ignores_missing_bom_when_shortage_check_disabled():
    service = WorkOrderService()
    wo, result = await _release(
        service,
        check_shortage=False,
        shortage={"has_shortage": False, "bom_missing": True},
    )

    service.check_material_shortage.assert_not_called()
    service.update_with_user.assert_awaited()
    assert service.update_with_user.await_args.kwargs["status"] == "released"
    assert result.status == "released"
    assert wo.status == "draft"


@pytest.mark.asyncio
async def test_release_ignores_missing_bom_when_block_misses_release():
    service = WorkOrderService()
    await _release(
        service,
        block_level=0,
        shortage={"has_shortage": False, "bom_missing": True},
    )

    service.check_material_shortage.assert_not_called()
    service.update_with_user.assert_awaited()
