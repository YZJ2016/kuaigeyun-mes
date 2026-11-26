"""其他出库编辑明细持久化回归测试。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kuaizhizao.models.other_outbound_item import OtherOutboundItem
from apps.kuaizhizao.services.warehouse_service import (
    _delete_omitted_other_outbound_items,
)


def test_delete_omitted_other_outbound_items_removes_missing_rows():
    query = MagicMock()
    query.delete = AsyncMock(return_value=1)

    with patch.object(OtherOutboundItem, "filter", return_value=query) as filter_mock:
        removed_ids = asyncio.run(
            _delete_omitted_other_outbound_items(
                tenant_id=7,
                outbound_id=19,
                existing_item_ids={101, 102, 103},
                submitted_item_ids={102, 103},
            )
        )

    assert removed_ids == [101]
    filter_mock.assert_called_once_with(
        tenant_id=7,
        outbound_id=19,
        id__in=[101],
    )
    query.delete.assert_awaited_once()


def test_delete_omitted_other_outbound_items_skips_delete_when_unchanged():
    with patch.object(OtherOutboundItem, "filter") as filter_mock:
        removed_ids = asyncio.run(
            _delete_omitted_other_outbound_items(
                tenant_id=7,
                outbound_id=19,
                existing_item_ids={101, 102},
                submitted_item_ids={101, 102},
            )
        )

    assert removed_ids == []
    filter_mock.assert_not_called()
