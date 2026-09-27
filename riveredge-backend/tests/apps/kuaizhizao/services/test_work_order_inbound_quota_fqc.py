"""工单入库额度：FQC 不应阻塞待入库单创建。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaizhizao.services.warehouse_service import FinishedGoodsReceiptService


def _quota_mocks(work_order, policy):
    resolver = MagicMock()
    resolver.return_value.resolve_over_receipt_pct = AsyncMock(return_value=Decimal("0"))
    return (
        patch(
            "apps.kuaizhizao.models.work_order.WorkOrder.get_or_none",
            new=AsyncMock(return_value=work_order),
        ),
        patch.object(
            FinishedGoodsReceiptService,
            "_sum_work_order_inbound_quantity",
            new=AsyncMock(return_value=0.0),
        ),
        patch(
            "apps.kuaizhizao.utils.over_qty_tolerance.OverQtyToleranceResolver",
            new=resolver,
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
            new=AsyncMock(return_value=policy),
        ),
        patch(
            "apps.kuaizhizao.services.inspection_policy_service.get_fqc_inbound_remaining_quantity",
            new=AsyncMock(return_value=Decimal("0")),
        ),
    )


def test_inbound_quota_pending_not_capped_by_fqc_when_no_inspection():
    """物料级显式免检（source=material 且 eff=none）时 pending 不按 FQC 余量封顶。"""
    work_order = MagicMock(id=10, product_id=99, quantity=Decimal("2"))

    mocks = _quota_mocks(work_order, ("none", None, "material"))
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        quota = asyncio.run(
            FinishedGoodsReceiptService()._get_work_order_inbound_quota(1, 10)
        )

    assert quota["pending"] == 2.0
    assert quota["fqc_qualified_remaining"] is None


def test_inbound_quota_pending_capped_by_fqc_when_required_without_inspection():
    """spec 140 规则 9：FQC 必检物料（含 default_none 无策略）无合格检验时 pending 封顶为 0。"""
    work_order = MagicMock(id=10, product_id=99, quantity=Decimal("2"))

    mocks = _quota_mocks(work_order, ("none", None, "default_none"))
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        quota = asyncio.run(
            FinishedGoodsReceiptService()._get_work_order_inbound_quota(1, 10)
        )

    assert quota["pending"] == 0.0
    assert quota["fqc_qualified_remaining"] == 0.0


def test_assert_inbound_quantity_allows_create_when_fqc_remaining_zero():
    svc = FinishedGoodsReceiptService()
    with patch.object(
        svc,
        "_get_work_order_inbound_quota",
        new=AsyncMock(
            return_value={
                "planned": 2.0,
                "max_quantity": 2.0,
                "received": 0.0,
                "pending": 2.0,
                "fqc_qualified_remaining": 0.0,
            }
        ),
    ):
        pending = asyncio.run(svc._assert_work_order_inbound_quantity(1, 10, 2.0))
    assert pending == 2.0
