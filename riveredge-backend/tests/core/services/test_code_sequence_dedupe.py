"""编码序号重复行解析测试。"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.services.business.code_generation_service import CodeGenerationService


def _seq_row(seq_id: int) -> SimpleNamespace:
    row = SimpleNamespace(
        id=seq_id,
        deleted_at=None,
        save=AsyncMock(),
    )
    return row


@pytest.mark.asyncio
async def test_resolve_active_code_sequence_returns_none_when_empty():
    with patch(
        "core.services.business.code_generation_service.CodeSequence.filter",
        return_value=SimpleNamespace(order_by=lambda *_: SimpleNamespace(all=AsyncMock(return_value=[]))),
    ):
        result = await CodeGenerationService._resolve_active_code_sequence(
            code_rule_id=1,
            tenant_id=10,
            scope_key="",
        )
    assert result is None


@pytest.mark.asyncio
async def test_resolve_active_code_sequence_soft_deletes_duplicates():
    keep = _seq_row(1)
    dup = _seq_row(2)
    rows = [keep, dup]

    with patch(
        "core.services.business.code_generation_service.CodeSequence.filter",
        return_value=SimpleNamespace(order_by=lambda *_: SimpleNamespace(all=AsyncMock(return_value=rows))),
    ), patch(
        "core.services.business.code_generation_service.now_utc",
        return_value=datetime(2026, 9, 13, tzinfo=timezone.utc),
    ):
        result = await CodeGenerationService._resolve_active_code_sequence(
            code_rule_id=1,
            tenant_id=10,
            scope_key="",
        )

    assert result is keep
    assert dup.deleted_at is not None
    dup.save.assert_awaited_once_with(update_fields=["deleted_at", "updated_at"])
