"""金蝶外推单号解析"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaizhizao.services.kingdee_push_bill_resolver import (
    resolve_kingdee_push_bill_no,
    resolve_kingdee_stocktaking_push_bills,
)


def _mock_relation_queryset(rows: list) -> MagicMock:
    ordered = MagicMock()
    ordered.all = AsyncMock(return_value=rows)
    qs = MagicMock()
    qs.filter.return_value = qs
    qs.order_by.return_value = ordered
    return qs


@pytest.mark.asyncio
async def test_resolve_latest_non_empty_target_code():
    rel_new = MagicMock(target_code="KD-002", id=2)
    rel_old = MagicMock(target_code="KD-001", id=1)
    with patch(
        "apps.kuaizhizao.services.kingdee_push_bill_resolver.DocumentRelation"
    ) as mock_model:
        mock_model.filter.return_value = _mock_relation_queryset([rel_new, rel_old])
        bill = await resolve_kingdee_push_bill_no(1, "purchase_receipt", 9)
    assert bill == "KD-002"


@pytest.mark.asyncio
async def test_resolve_skips_empty_target_code():
    rel_blank = MagicMock(target_code="", id=2)
    rel_ok = MagicMock(target_code="KD-100", id=1)
    with patch(
        "apps.kuaizhizao.services.kingdee_push_bill_resolver.DocumentRelation"
    ) as mock_model:
        mock_model.filter.return_value = _mock_relation_queryset([rel_blank, rel_ok])
        bill = await resolve_kingdee_push_bill_no(1, "sales_delivery", 3)
    assert bill == "KD-100"


@pytest.mark.asyncio
async def test_resolve_stocktaking_surplus_and_deficit():
    with patch(
        "apps.kuaizhizao.services.kingdee_push_bill_resolver.resolve_kingdee_push_bill_no",
        new_callable=AsyncMock,
    ) as mock_resolve:
        mock_resolve.side_effect = ["SY-1", "SK-2"]
        bills = await resolve_kingdee_stocktaking_push_bills(1, 5)
    assert bills.kingdee_surplus_bill_no == "SY-1"
    assert bills.kingdee_deficit_bill_no == "SK-2"