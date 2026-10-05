"""工序从数据接口/数据集同步。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.master_data.models.master_data_sync_binding import OperationSyncBinding
from apps.master_data.models.process import Operation
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.master_data.services.master_data_sync_common import (
    apply_sync_extras_after_write,
    cell_str,
    mark_binding_failure,
    mark_binding_success,
    mark_external_sync_record,
    normalize_schedule_interval,
    normalize_sync_mode,
    resolve_incremental_since,
    resolve_sync_sources,
    serialize_binding_row,
    sources_from_upsert_body,
    upsert_sync_binding,
)
from core.services.data.sync_binding_sources import fetch_mapped_rows_from_sources
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import ValidationError
from infra.models.user import User

OPERATION_SYNC_STRING_FIELDS = frozenset({"description", "reporting_type", "over_report_mode", "inspection_mode"})
OPERATION_SYNC_BOOL_FIELDS = frozenset({"is_active", "allow_jump", "is_node_operation"})


class OperationSyncService:
    MATCH_KEY = "code"

    def serialize_binding(self, row: Optional[OperationSyncBinding]) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await OperationSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut(match_key_field=self.MATCH_KEY)

        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval = normalize_schedule_interval(body.schedule_interval_minutes)
        row = await upsert_sync_binding(
            OperationSyncBinding,
            tenant_id,
            sources=sources,
            match_key_field=match_key,
            sync_mode=sync_mode,
            schedule_interval_minutes=interval,
        )
        return self.serialize_binding(row)

    async def get_binding(self, tenant_id: int) -> MasterDataSyncBindingOut:
        row = await OperationSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: Optional[User],
        request: Optional[MasterDataSyncFromSourceRequest] = None,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            OperationSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )

        binding = binding or await OperationSyncBinding.filter(tenant_id=tenant_id).first()
        sync_mode = normalize_sync_mode(
            req.sync_mode or (binding.sync_mode if binding else None)
        )
        interval = normalize_schedule_interval(
            req.schedule_interval_minutes
            if req.schedule_interval_minutes is not None
            else (binding.schedule_interval_minutes if binding else None)
        )

        if req.save_binding:
            await self.upsert_binding(
                tenant_id,
                MasterDataSyncBindingUpsert(
                    sources=req.sources,
                    match_key_field=match_key,
                    sync_mode=sync_mode,
                    schedule_interval_minutes=interval,
                ),
            )
            binding = await OperationSyncBinding.filter(tenant_id=tenant_id).first()

        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )
        try:
            rows, source_errors, _fetched = await fetch_mapped_rows_from_sources(
                tenant_id,
                sources,
                since=since,
                active_only=req.active_only,
            )
            result = await self._upsert_operations(tenant_id, current_user, rows, match_key)
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            if binding:
                if result.failed and not (result.created or result.updated):
                    await mark_binding_failure(binding, "; ".join(result.errors) or "工序同步失败")
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    async def _upsert_operations(
        self,
        tenant_id: int,
        current_user: Optional[User],
        rows: List[Dict[str, Any]],
        match_key: str,
    ) -> MasterDataSyncFromSourceOut:
        created = 0
        updated = 0
        skipped = 0
        failed = 0
        errors: List[str] = []
        sync_at = resolve_business_datetime()

        pending: List[tuple[str, str, bool, Dict[str, Any]]] = []
        for row in rows:
            code = cell_str(row.get(match_key) or row.get("code"))
            name = cell_str(row.get("name"))
            if not code:
                skipped += 1
                errors.append("存在缺少工序编码的行，已跳过")
                continue
            if not name:
                skipped += 1
                errors.append(f"工序 {code} 缺少名称，已跳过")
                continue
            is_active_raw = row.get("is_active")
            is_active = True
            if is_active_raw is not None and str(is_active_raw).strip():
                is_active = str(is_active_raw).strip().lower() not in (
                    "0",
                    "false",
                    "no",
                    "n",
                    "否",
                    "停用",
                    "inactive",
                    "disabled",
                )
            pending.append((code, name, is_active, row))

        if not pending:
            return MasterDataSyncFromSourceOut(
                created=created,
                updated=updated,
                skipped=skipped,
                failed=failed,
                errors=errors[:20],
            )

        codes = [item[0] for item in pending]
        existing_rows = await Operation.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            code__in=codes,
        ).all()
        existing_by_code = {item.code: item for item in existing_rows}

        for code, name, is_active, mapped_row in pending:
            try:
                existing = existing_by_code.get(code)
                if existing:
                    existing.name = name
                    existing.is_active = is_active
                    desc = cell_str(mapped_row.get("description"))
                    if desc is not None:
                        existing.description = desc or None
                    existing.external_sync_at = sync_at
                    apply_update_audit(existing, current_user)
                    await existing.save()
                    await apply_sync_extras_after_write(
                        tenant_id=tenant_id,
                        record=existing,
                        mapped_row=mapped_row,
                        record_table="",
                        fields_by_code={},
                        string_fields=OPERATION_SYNC_STRING_FIELDS,
                        bool_fields=OPERATION_SYNC_BOOL_FIELDS,
                        int_fields=frozenset(),
                    )
                    await mark_external_sync_record(existing)
                    existing_by_code[existing.code] = existing
                    updated += 1
                else:
                    payload: Dict[str, Any] = {
                        "code": code,
                        "name": name,
                        "is_active": is_active,
                        "description": cell_str(mapped_row.get("description")) or None,
                        "external_sync_at": sync_at,
                    }
                    apply_create_audit(payload, current_user)
                    op = await Operation.create(tenant_id=tenant_id, **payload)
                    await apply_sync_extras_after_write(
                        tenant_id=tenant_id,
                        record=op,
                        mapped_row=mapped_row,
                        record_table="",
                        fields_by_code={},
                        string_fields=OPERATION_SYNC_STRING_FIELDS,
                        bool_fields=OPERATION_SYNC_BOOL_FIELDS,
                        int_fields=frozenset(),
                    )
                    await mark_external_sync_record(op)
                    existing_by_code[op.code] = op
                    created += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                errors.append(f"工序 {code}: {exc}")

        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
