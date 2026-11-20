"""core_sync_run_logs 只读列表（Hub / 主数据入站同步共用）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from tortoise import Tortoise

from apps.kuaizhizao.api._kuaizhizao_document_gate import resolve_history_inbound_entity_type

_INBOUND_HISTORY_SELECT_COLUMNS = """
    id,
    entity_type,
    mode,
    status,
    created,
    updated,
    skipped,
    failed,
    fetched,
    truncated,
    duration_ms,
    error_summary,
    started_at,
    finished_at,
    created_at,
    trigger_kind
"""


async def list_inbound_entity_sync_run_history_rows(
    tenant_id: int,
    entity_type: str,
    *,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[Dict[str, Any]], int]:
    """按 entity_type 只读列表（主数据入站同步 Modal 用）。"""
    et = str(entity_type or "").strip()
    conn = Tortoise.get_connection("default")
    count_rows = await conn.execute_query_dict(
        "SELECT COUNT(*) AS total FROM core_sync_run_logs WHERE tenant_id = $1 AND entity_type = $2",
        [tenant_id, et],
    )
    rows = await conn.execute_query_dict(
        f"""
        SELECT {_INBOUND_HISTORY_SELECT_COLUMNS}
        FROM core_sync_run_logs
        WHERE tenant_id = $1 AND entity_type = $2
        ORDER BY created_at DESC
        OFFSET $3 LIMIT $4
        """,
        [tenant_id, et, skip, limit],
    )
    total = int(count_rows[0]["total"]) if count_rows else 0
    return rows, total


async def list_sync_run_history_rows(
    tenant_id: int,
    source_type: str,
    *,
    target_profiles: Optional[List[str]] = None,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[Dict[str, Any]], int]:
    st = str(source_type or "").strip()
    inbound_entity = resolve_history_inbound_entity_type(st)
    profiles = [p.strip() for p in (target_profiles or []) if p and str(p).strip()]
    summary_prefix = f"{st}/%"
    profiles_empty = len(profiles) == 0
    profile_params = profiles if profiles else [""]

    conn = Tortoise.get_connection("default")
    where_sql = """
        tenant_id = $1
        AND (
            ($2::text IS NOT NULL AND entity_type = $2)
            OR (
                entity_type = 'document_push'
                AND error_summary LIKE $3
                AND ($4::boolean OR target_profile = ANY($5::text[]))
            )
        )
    """
    params_base = [tenant_id, inbound_entity, summary_prefix, profiles_empty, profile_params]
    count_rows = await conn.execute_query_dict(
        f"SELECT COUNT(*) AS total FROM core_sync_run_logs WHERE {where_sql}",
        params_base,
    )
    rows = await conn.execute_query_dict(
        f"""
        SELECT
            id,
            entity_type,
            mode,
            status,
            created,
            updated,
            skipped,
            failed,
            fetched,
            truncated,
            duration_ms,
            error_summary,
            started_at,
            finished_at,
            created_at,
            category,
            connector_type,
            target_profile,
            trigger_kind
        FROM core_sync_run_logs
        WHERE {where_sql}
        ORDER BY created_at DESC
        OFFSET $6
        LIMIT $7
        """,
        [*params_base, skip, limit],
    )
    total = int(count_rows[0]["total"]) if count_rows else 0
    return rows, total
