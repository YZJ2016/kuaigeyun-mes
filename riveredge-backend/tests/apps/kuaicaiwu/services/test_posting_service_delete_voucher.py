"""记账凭证删除：已作废可软删除。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kuaicaiwu.services.posting_service import PostingService
from infra.exceptions.exceptions import ValidationError


def test_delete_cancelled_voucher_soft_deletes():
    voucher = MagicMock(id=1, status="cancelled")
    svc = PostingService()
    with patch.object(svc, "_get", new=AsyncMock(return_value=voucher)), patch(
        "apps.kuaicaiwu.models.voucher_line.VoucherLine.filter"
    ) as line_filter_mock, patch(
        "tortoise.transactions.in_transaction",
        return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
    ):
        line_filter_mock.return_value.delete = AsyncMock()
        voucher.save = AsyncMock()
        asyncio.run(svc.delete_draft_voucher(1, 1))
    line_filter_mock.return_value.delete.assert_awaited_once()
    voucher.save.assert_awaited_once()


def test_delete_reviewed_voucher_rejected():
    voucher = MagicMock(id=1, status="reviewed")
    svc = PostingService()
    with patch.object(svc, "_get", new=AsyncMock(return_value=voucher)), pytest.raises(
        ValidationError, match="已作废"
    ):
        asyncio.run(svc.delete_draft_voucher(1, 1))
