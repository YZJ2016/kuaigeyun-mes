"""库位从数据接口/数据集同步（对齐苍穹 bd_location；可不挂库区）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from infra.exceptions.exceptions import ValidationError
from infra.models.user import User

from apps.master_data.models.master_data_sync_binding import StorageLocationSyncBinding
from apps.master_data.models.warehouse import StorageLocation
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.master_data.schemas.warehouse_schemas import StorageLocationCreate, StorageLocationUpdate
from apps.master_data.services.warehouse_service import WarehouseService
from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import (
    apply_sync_extras_after_write,
    attach_sync_fetch_meta,
    cell_str,
    load_custom_fields_by_code,
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
    resolve_upsert_schedule_from_body,
    resolve_schedule_window_for_sync_request,
)
from apps.kuaiconnect.services.inbound_sync.sync_binding_sources import fetch_mapped_rows_from_sources

STORAGE_LOCATION_CUSTOM_FIELD_TABLE = "master_data_warehouse_storage_locations"
STORAGE_LOCATION_SYNC_STRING_FIELDS = frozenset({"description"})
STORAGE_LOCATION_SYNC_BOOL_FIELDS = frozenset({"is_active"})


def _map_kingdee_forbid_to_is_active(forbid_status: object) -> bool:
    """金蝶 FForbidStatus：A=未禁用，B=已禁用。"""
    val = cell_str(forbid_status).upper()
    if not val:
        raise ValidationError("FForbidStatus 不能为空")
    if val == "A":
        return True
    if val == "B":
        return False
    raise ValidationError(f"未知禁用状态 FForbidStatus={forbid_status}")


def _resolve_location_is_active(row: Dict[str, Any]) -> bool:
    forbid_raw = row.get("forbid_status")
    if forbid_raw is not None and cell_str(forbid_raw):
        return _map_kingdee_forbid_to_is_active(forbid_raw)
    enable_raw = row.get("enable")
    if enable_raw is None:
        enable_raw = row.get("is_active")
    if enable_raw is None:
        return True
    if isinstance(enable_raw, bool):
        return enable_raw
    val = cell_str(enable_raw).upper()
    if val in ("1", "TRUE", "Y", "YES", "启用", "A"):
        return True
    if val in ("0", "FALSE", "N", "NO", "停用", "B"):
        return False
    return True


class StorageLocationSyncService:
    MATCH_KEY = "code"

    def serialize_binding(self, row: Optional[StorageLocationSyncBinding]) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await StorageLocationSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut()
        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval, w_start, w_end = await resolve_upsert_schedule_from_body(
            StorageLocationSyncBinding, tenant_id, body
        )
        row = await upsert_sync_binding(
            StorageLocationSyncBinding,
            tenant_id,
            sources=sources,
            match_key_field=match_key,
            sync_mode=sync_mode,
            schedule_interval_minutes=interval,
            schedule_window_start=w_start,
            schedule_window_end=w_end,
        )
        return self.serialize_binding(row)

    async def get_binding(self, tenant_id: int) -> MasterDataSyncBindingOut:
        row = await StorageLocationSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: User,
        request: Optional[MasterDataSyncFromSourceRequest] = None,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            StorageLocationSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )
        binding = binding or await StorageLocationSyncBinding.filter(tenant_id=tenant_id).first()
        sync_mode = normalize_sync_mode(
            req.sync_mode or (binding.sync_mode if binding else None)
        )
        interval = normalize_schedule_interval(
            req.schedule_interval_minutes
            if req.schedule_interval_minutes is not None
            else (binding.schedule_interval_minutes if binding else None)
        )
        w_start, w_end = resolve_schedule_window_for_sync_request(req, binding)
        if req.save_binding:
            await self.upsert_binding(
                tenant_id,
                MasterDataSyncBindingUpsert(
                    sources=req.sources,
                    match_key_field=match_key,
                    sync_mode=sync_mode,
                    schedule_interval_minutes=interval,
                    schedule_window_start=w_start,
                    schedule_window_end=w_end,
                ),
            )
            binding = await StorageLocationSyncBinding.filter(tenant_id=tenant_id).first()
        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )
        try:
            rows, source_errors, fetched = await fetch_mapped_rows_from_sources(
                tenant_id,
                sources,
                since=since,
                active_only=req.active_only,
            )
            result = await self._upsert_locations(tenant_id, current_user, rows, match_key)
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            attach_sync_fetch_meta(result, fetched=fetched, since=since, truncated=False)
            if binding:
                if result.failed and not (result.created or result.updated):
                    await mark_binding_failure(
                        binding, "; ".join(result.errors) or "库位同步失败"
                    )
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    async def _upsert_locations(
        self,
        tenant_id: int,
        current_user: User,
        rows: List[Dict[str, Any]],
        match_key: str,
    ) -> MasterDataSyncFromSourceOut:
        created = 0
        updated = 0
        skipped = 0
        failed = 0
        errors: List[str] = []
        custom_fields_by_code = await load_custom_fields_by_code(
            tenant_id, STORAGE_LOCATION_CUSTOM_FIELD_TABLE
        )
        for row in rows:
            code = cell_str(
                row.get(match_key if match_key == "code" else "code") or row.get(match_key)
            )
            name = cell_str(row.get("name"))
            if not code:
                skipped += 1
                errors.append("存在缺少库位编码的行，已跳过")
                continue
            if not name:
                skipped += 1
                errors.append(f"库位 {code} 缺少名称，已跳过")
                continue
            is_active = _resolve_location_is_active(row)
            try:
                existing = await StorageLocation.filter(
                    tenant_id=tenant_id,
                    code=code.upper(),
                    deleted_at__isnull=True,
                ).first()
                if existing:
                    update_data = StorageLocationUpdate(
                        name=name,
                        is_active=is_active,
                        source_location_code=code.strip().upper(),
                    )
                    await WarehouseService.update_storage_location(
                        tenant_id,
                        existing.uuid,
                        update_data,
                        current_user=current_user,
                    )
                    await existing.refresh_from_db()
                    await apply_sync_extras_after_write(
                        tenant_id=tenant_id,
                        record=existing,
                        mapped_row=row,
                        record_table=STORAGE_LOCATION_CUSTOM_FIELD_TABLE,
                        fields_by_code=custom_fields_by_code,
                        string_fields=STORAGE_LOCATION_SYNC_STRING_FIELDS,
                        bool_fields=STORAGE_LOCATION_SYNC_BOOL_FIELDS,
                    )
                    await mark_external_sync_record(existing)
                    updated += 1
                else:
                    create_data = StorageLocationCreate(
                        code=code,
                        source_location_code=code.strip().upper(),
                        name=name,
                        is_active=is_active,
                        storage_area_id=None,
                    )
                    created_loc = await WarehouseService.create_storage_location(
                        tenant_id, create_data, current_user=current_user
                    )
                    loc_row = await StorageLocation.filter(
                        tenant_id=tenant_id,
                        uuid=created_loc.uuid,
                        deleted_at__isnull=True,
                    ).first()
                    if loc_row:
                        await apply_sync_extras_after_write(
                            tenant_id=tenant_id,
                            record=loc_row,
                            mapped_row=row,
                            record_table=STORAGE_LOCATION_CUSTOM_FIELD_TABLE,
                            fields_by_code=custom_fields_by_code,
                            string_fields=STORAGE_LOCATION_SYNC_STRING_FIELDS,
                            bool_fields=STORAGE_LOCATION_SYNC_BOOL_FIELDS,
                        )
                        await mark_external_sync_record(loc_row)
                    created += 1
            except Exception as exc:
                failed += 1
                errors.append(f"库位 {code}：{exc}")
        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
