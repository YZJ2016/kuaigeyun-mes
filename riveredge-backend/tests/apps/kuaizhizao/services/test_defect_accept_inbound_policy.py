"""让步接收：FQC/IQC 确认规则扩展。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.services.inspection_policy_service import (
    assert_fqc_for_finished_goods_receipt,
    defect_accept_material_ids_for_purchase_receipt,
    sum_defect_accept_quantity_for_finished_goods_receipt,
)


def test_sum_defect_accept_quantity_for_finished_goods_receipt():
    row = MagicMock(defect_quantity=Decimal("20"))
    with patch(
        "apps.kuaizhizao.models.defect_record.DefectRecord.filter",
    ) as filter_mock:
        filter_mock.return_value.all = AsyncMock(return_value=[row])
        total = asyncio.run(sum_defect_accept_quantity_for_finished_goods_receipt(1, 99))
    assert total == Decimal("20")


def test_fqc_assert_allows_concession_quantity_beyond_qualified_remaining():
    item = MagicMock(material_id=100, receipt_quantity=20, qualified_quantity=20)
    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
        new=AsyncMock(
            return_value={"gate": {"require_fqc_before_finished_goods_receipt": True}}
        ),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.sum_defect_accept_quantity_for_finished_goods_receipt",
        new=AsyncMock(return_value=Decimal("20")),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("plan", 1, None)),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.sum_fqc_inbound_qualified_quantity",
        new=AsyncMock(return_value=Decimal("180")),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_fqc_inbound_remaining_quantity",
        new=AsyncMock(return_value=Decimal("0")),
    ):
        asyncio.run(assert_fqc_for_finished_goods_receipt(1, 99, 10, [item]))


def test_fqc_assert_still_blocks_when_no_concession():
    item = MagicMock(material_id=100, receipt_quantity=20, qualified_quantity=20)
    with patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_quality_effective_config",
        new=AsyncMock(
            return_value={"gate": {"require_fqc_before_finished_goods_receipt": True}}
        ),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.sum_defect_accept_quantity_for_finished_goods_receipt",
        new=AsyncMock(return_value=Decimal("0")),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.resolve_inspection_policy",
        new=AsyncMock(return_value=("plan", 1, None)),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.sum_fqc_inbound_qualified_quantity",
        new=AsyncMock(return_value=Decimal("180")),
    ), patch(
        "apps.kuaizhizao.services.inspection_policy_service.get_fqc_inbound_remaining_quantity",
        new=AsyncMock(return_value=Decimal("0")),
    ), pytest.raises(Exception, match="超过可确认余量"):
        asyncio.run(assert_fqc_for_finished_goods_receipt(1, 99, 10, [item]))


def test_defect_accept_material_ids_for_purchase_receipt():
    row = MagicMock(product_id=100)
    with patch(
        "apps.kuaizhizao.models.defect_record.DefectRecord.filter",
    ) as filter_mock:
        filter_mock.return_value.all = AsyncMock(return_value=[row])
        mids = asyncio.run(defect_accept_material_ids_for_purchase_receipt(1, 55))
    assert mids == frozenset({100})
