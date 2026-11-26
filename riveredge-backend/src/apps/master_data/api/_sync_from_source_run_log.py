"""主数据 sync-from-source：统一写入 core_sync_run_logs。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Type

from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import run_inbound_sync_with_run_log
from core.services.data.sync_trigger_kind import SYNC_TRIGGER_KIND_MANUAL, sync_run_trigger_kind


async def master_data_sync_from_source_with_run_log(
    *,
    tenant_id: int,
    entity_type: str,
    binding_model: Type[Any],
    run_sync: Callable[[], Awaitable[Any]],
    stream: bool = False,
):
    binding = await binding_model.filter(tenant_id=tenant_id).first()

    async def invoke() -> Any:
        with sync_run_trigger_kind(SYNC_TRIGGER_KIND_MANUAL):
            return await run_inbound_sync_with_run_log(
                tenant_id=tenant_id,
                entity_type=entity_type,
                binding=binding,
                run=run_sync,
            )

    if stream:
        from core.services.data.sync_progress_stream import stream_sync_ndjson

        return await stream_sync_ndjson(invoke)
    return await invoke()
