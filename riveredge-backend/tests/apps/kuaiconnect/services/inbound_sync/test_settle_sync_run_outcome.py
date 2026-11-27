"""入站同步统一结果语义：finalize / settle。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import (
    SYNC_EMPTY_FILTERED,
    SYNC_EMPTY_MAPPING,
    SYNC_EMPTY_SOURCE,
    finalize_sync_run_outcome,
    settle_sync_run_outcome,
)


def _result(**kwargs):
    base = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "fetched": 0,
        "after_filter": 0,
        "empty_reason": None,
        "mode": "full",
        "errors": [],
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_finalize_source_empty():
    result = _result(fetched=0, after_filter=0)
    finalize_sync_run_outcome(result, since=None, mapped_count=0)
    assert result.empty_reason == SYNC_EMPTY_SOURCE
    assert result.errors and "fetched=0" in result.errors[0]


def test_finalize_filtered_all():
    result = _result(fetched=10, after_filter=0)
    finalize_sync_run_outcome(result, since=None, mapped_count=0)
    assert result.empty_reason == SYNC_EMPTY_FILTERED


def test_finalize_mapping_empty():
    result = _result(fetched=10, after_filter=5)
    finalize_sync_run_outcome(result, since=None, mapped_count=0)
    assert result.empty_reason == SYNC_EMPTY_MAPPING


def test_finalize_incremental_noop_not_empty():
    result = _result(fetched=0, after_filter=0)
    finalize_sync_run_outcome(result, since=__import__("datetime").datetime(2026, 1, 1))
    assert result.empty_reason is None
    assert result.errors == []


def test_finalize_wrote_skips_empty_reason():
    result = _result(created=1, fetched=0)
    finalize_sync_run_outcome(result, since=None, mapped_count=0)
    assert result.empty_reason is None


def test_finalize_source_empty_detail_override():
    result = _result(fetched=0)
    finalize_sync_run_outcome(
        result,
        since=None,
        mapped_count=0,
        source_empty_detail="单位专属空拉说明",
    )
    assert result.empty_reason == SYNC_EMPTY_SOURCE
    assert result.errors[0] == "单位专属空拉说明"


@pytest.mark.asyncio
async def test_settle_marks_binding_failure_on_empty_reason():
    result = _result()
    binding = SimpleNamespace()
    with (
        patch(
            "apps.kuaiconnect.services.inbound_sync.master_data_sync_common.mark_binding_failure",
            new_callable=AsyncMock,
        ) as fail,
        patch(
            "apps.kuaiconnect.services.inbound_sync.master_data_sync_common.mark_binding_success",
            new_callable=AsyncMock,
        ) as ok,
    ):
        await settle_sync_run_outcome(
            result,
            binding=binding,
            fetched=0,
            after_filter=0,
            mapped_count=0,
            since=None,
            failure_label="仓库同步失败",
        )
        fail.assert_awaited_once()
        ok.assert_not_awaited()
    assert result.fetched == 0
    assert result.empty_reason == SYNC_EMPTY_SOURCE
    assert result.mode == "full"


@pytest.mark.asyncio
async def test_settle_marks_binding_success_when_wrote():
    result = _result(created=2, updated=1)
    binding = SimpleNamespace()
    with (
        patch(
            "apps.kuaiconnect.services.inbound_sync.master_data_sync_common.mark_binding_failure",
            new_callable=AsyncMock,
        ) as fail,
        patch(
            "apps.kuaiconnect.services.inbound_sync.master_data_sync_common.mark_binding_success",
            new_callable=AsyncMock,
        ) as ok,
    ):
        await settle_sync_run_outcome(
            result,
            binding=binding,
            fetched=10,
            after_filter=8,
            mapped_count=8,
            since=None,
        )
        ok.assert_awaited_once()
        fail.assert_not_awaited()
    assert result.after_filter == 8
    assert result.empty_reason is None


@pytest.mark.asyncio
async def test_settle_merges_source_errors():
    result = _result(created=1)
    await settle_sync_run_outcome(
        result,
        binding=None,
        fetched=3,
        after_filter=3,
        mapped_count=1,
        since=None,
        source_errors=["源接口超时"],
        update_binding=False,
    )
    assert result.errors[0] == "源接口超时"
