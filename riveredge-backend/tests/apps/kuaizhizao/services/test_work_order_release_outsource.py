"""工单下达：计划委外工序不再自动建委外草稿、不要求默认供应商。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.services.work_order_service import WorkOrderService


@pytest.mark.asyncio
async def test_release_work_order_skips_planned_outsource_draft_hook():
    svc = WorkOrderService()
    assert not hasattr(svc, "_ensure_planned_outsource_drafts")

    work_order = SimpleNamespace(
        id=42,
        status="draft",
        review_status=None,
        product_id=7,
        code="WO-TEST",
        quantity=10,
        created_by=1,
    )
    updated_wo = SimpleNamespace(
        id=work_order.id,
        status="released",
        product_id=work_order.product_id,
        code=work_order.code,
        quantity=work_order.quantity,
        created_by=work_order.created_by,
    )

    mock_in_tx = MagicMock()
    mock_in_tx.__aenter__ = AsyncMock(return_value=None)
    mock_in_tx.__aexit__ = AsyncMock(return_value=None)

    create_from_wo = AsyncMock()

    with patch(
        "apps.kuaizhizao.services.work_order_service.in_transaction",
        return_value=mock_in_tx,
    ), patch.object(
        svc,
        "get_by_id",
        new=AsyncMock(return_value=work_order),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.BusinessConfigService"
    ) as mock_biz_cfg_cls, patch(
        "apps.kuaizhizao.services.work_order_service.assert_work_order_capability",
    ), patch.object(
        svc,
        "update_with_user",
        new=AsyncMock(return_value=updated_wo),
    ), patch.object(
        svc,
        "get_work_order_by_id",
        new=AsyncMock(return_value={"id": 42, "status": "released"}),
    ), patch(
        "apps.kuaizhizao.services.work_order_service.Material.get_or_none",
        new=AsyncMock(return_value=None),
    ), patch(
        "apps.kuaizhizao.services.kuaizhizao_business_notification.dispatch_kuaizhizao_notification",
        new=AsyncMock(),
    ), patch(
        "apps.kuaizhizao.services.outsource_service.OutsourceService.create_outsource_order_from_work_order",
        create_from_wo,
    ):
        mock_biz = mock_biz_cfg_cls.return_value
        mock_biz.check_audit_required = AsyncMock(return_value=False)
        mock_biz.get_material_shortage_block_level = AsyncMock(return_value="none")

        await svc.release_work_order(
            tenant_id=1,
            work_order_id=42,
            released_by=9,
            check_shortage=False,
        )

    create_from_wo.assert_not_called()