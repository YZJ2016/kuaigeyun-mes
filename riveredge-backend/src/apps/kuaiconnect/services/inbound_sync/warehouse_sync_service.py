"""仓库从数据接口/数据集同步。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from infra.exceptions.exceptions import ValidationError
from infra.models.user import User

from apps.common.audit_actor import apply_create_audit, apply_restore_audit, apply_update_audit
from apps.master_data.models.master_data_sync_binding import WarehouseSyncBinding
from apps.master_data.models.warehouse import Warehouse
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import (
    apply_sync_extras_after_write,
    attach_sync_fetch_meta,
    cell_optional_bool,
    cell_str,
    collect_mapped_scalar_proposed,
    is_force_rewrite_sync_mode,
    load_custom_fields_by_code,
    mark_binding_failure,
    mark_binding_success,
    normalize_schedule_interval,
    normalize_sync_mode,
    resolve_incremental_since,
    resolve_sync_sources,
    serialize_binding_row,
    sources_from_upsert_body,
    sync_record_needs_update,
    upsert_sync_binding,
    resolve_upsert_schedule_from_body,
    resolve_schedule_window_for_sync_request,
)
from apps.kuaiconnect.services.inbound_sync.sync_binding_sources import fetch_mapped_rows_from_sources
from core.services.data.sync_progress import emit_sync_progress
from core.utils.timezone_utils import resolve_business_datetime

WAREHOUSE_CUSTOM_FIELD_TABLE = "master_data_warehouse_warehouses"
WAREHOUSE_SYNC_STRING_FIELDS = frozenset({"description", "warehouse_type"})
WAREHOUSE_SYNC_BOOL_FIELDS = frozenset({"is_active"})
WAREHOUSE_BULK_UPDATE_FIELDS = [
    "name",
    "is_active",
    "external_sync_at",
    "updated_at",
    "updated_by",
    "updated_by_name",
]
_WRITE_BATCH = 500


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


def _resolve_warehouse_is_active(row: Dict[str, Any]) -> bool:
    forbid_raw = row.get("forbid_status")
    if forbid_raw is not None and cell_str(forbid_raw):
        return _map_kingdee_forbid_to_is_active(forbid_raw)
    mapped_active = cell_optional_bool(row.get("is_active"))
    if mapped_active is not None:
        return bool(mapped_active)
    enable = str(row.get("enable") or "").strip()
    if enable == "0":
        return False
    return True


class WarehouseSyncService:
    MATCH_KEY = "code"

    def serialize_binding(self, row: Optional[WarehouseSyncBinding]) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await WarehouseSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut()
        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval, w_start, w_end = await resolve_upsert_schedule_from_body(
            WarehouseSyncBinding, tenant_id, body
        )
        row = await upsert_sync_binding(
            WarehouseSyncBinding,
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
        row = await WarehouseSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: User,
        request: Optional[MasterDataSyncFromSourceRequest] = None,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            WarehouseSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )
        binding = binding or await WarehouseSyncBinding.filter(tenant_id=tenant_id).first()
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
            binding = await WarehouseSyncBinding.filter(tenant_id=tenant_id).first()
        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )
        try:
            await emit_sync_progress("开始同步仓库…")
            rows, source_errors, fetched = await fetch_mapped_rows_from_sources(
                tenant_id,
                sources,
                since=since,
                active_only=req.active_only,
            )
            result = await self._upsert_warehouses(
                tenant_id,
                current_user,
                rows,
                match_key,
                force_rewrite=is_force_rewrite_sync_mode(sync_mode),
            )
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            attach_sync_fetch_meta(result, fetched=fetched, since=since, truncated=False)
            if binding:
                if result.failed and not (result.created or result.updated):
                    await mark_binding_failure(binding, "; ".join(result.errors) or "仓库同步失败")
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    async def _upsert_warehouses(
        self,
        tenant_id: int,
        current_user: User,
        rows: List[Dict[str, Any]],
        match_key: str,
        *,
        force_rewrite: bool = False,
    ) -> MasterDataSyncFromSourceOut:
        created = 0
        updated = 0
        skipped = 0
        failed = 0
        errors: List[str] = []
        sync_at = resolve_business_datetime()
        custom_fields_by_code = await load_custom_fields_by_code(
            tenant_id, WAREHOUSE_CUSTOM_FIELD_TABLE
        )

        PendingRow = Tuple[str, str, bool, Dict[str, Any]]
        pending_rows: List[PendingRow] = []
        for row in rows:
            code = cell_str(
                row.get(match_key if match_key == "code" else "code") or row.get(match_key)
            )
            name = cell_str(row.get("name"))
            if not code:
                skipped += 1
                errors.append("存在缺少仓库编码的行，已跳过")
                continue
            if not name:
                skipped += 1
                errors.append(f"仓库 {code} 缺少名称，已跳过")
                continue
            try:
                is_active = _resolve_warehouse_is_active(row)
            except ValidationError as exc:
                failed += 1
                errors.append(f"仓库 {code}：{exc}")
                continue
            pending_rows.append((code, name, is_active, row))

        if not pending_rows:
            return MasterDataSyncFromSourceOut(
                created=created,
                updated=updated,
                skipped=skipped,
                failed=failed,
                errors=errors[:20],
            )

        total = len(pending_rows)
        await emit_sync_progress(f"正在预加载本地仓库，准备写入 {total} 条…")

        lookup_keys = [item[0].upper() for item in pending_rows]
        existing_by_key: Dict[str, Warehouse] = {}
        soft_deleted_by_key: Dict[str, Warehouse] = {}
        lookup_chunk = 2000
        raw_codes = [item[0] for item in pending_rows]
        for offset in range(0, len(raw_codes), lookup_chunk):
            chunk_codes = raw_codes[offset : offset + lookup_chunk]
            active_rows = await Warehouse.filter(
                tenant_id=tenant_id,
                code__in=chunk_codes,
                deleted_at__isnull=True,
            ).all()
            for item in active_rows:
                existing_by_key[item.code.upper()] = item
            deleted_rows = await Warehouse.filter(
                tenant_id=tenant_id,
                code__in=chunk_codes,
                deleted_at__isnull=False,
            ).all()
            for item in deleted_rows:
                soft_deleted_by_key[item.code.upper()] = item

        to_update: List[Warehouse] = []
        to_create: List[Warehouse] = []
        custom_payload_by_key: Dict[str, Dict[str, Any]] = {}

        for index, (code, name, is_active, mapped_row) in enumerate(pending_rows, start=1):
            code_key = code.upper()
            if index == 1 or index == total or index % 500 == 0:
                await emit_sync_progress(f"正在解析仓库 {index}/{total}：{code}")
            custom_payload_by_key[code_key] = mapped_row
            try:
                proposed = collect_mapped_scalar_proposed(
                    mapped_row,
                    string_fields=WAREHOUSE_SYNC_STRING_FIELDS,
                    bool_fields=frozenset(),
                    always={"name": name, "is_active": is_active},
                )
                existing = existing_by_key.get(code_key)
                if existing:
                    has_custom = any(str(k).startswith("custom:") for k in mapped_row.keys())
                    if not has_custom and not sync_record_needs_update(
                        existing, proposed, force=force_rewrite
                    ):
                        skipped += 1
                        continue
                    existing.name = name
                    existing.is_active = is_active
                    existing.external_sync_at = sync_at
                    existing.updated_at = sync_at
                    if current_user is not None:
                        apply_update_audit(existing, current_user)
                    to_update.append(existing)
                    continue

                soft = soft_deleted_by_key.get(code_key)
                if soft:
                    soft.deleted_at = None
                    soft.name = name
                    soft.is_active = is_active
                    soft.external_sync_at = sync_at
                    soft.updated_at = sync_at
                    apply_restore_audit(soft, current_user)
                    to_update.append(soft)
                    continue

                payload: Dict[str, Any] = {
                    "tenant_id": tenant_id,
                    "code": code,
                    "name": name,
                    "is_active": is_active,
                    "external_sync_at": sync_at,
                }
                if current_user is not None:
                    apply_create_audit(payload, current_user)
                to_create.append(Warehouse(**payload))
            except Exception as exc:
                failed += 1
                errors.append(f"仓库 {code}：{exc}")

        async def _write_extras(records: List[Warehouse]) -> None:
            for record in records:
                mapped = custom_payload_by_key.get(record.code.upper())
                if not mapped:
                    continue
                try:
                    await apply_sync_extras_after_write(
                        tenant_id=tenant_id,
                        record=record,
                        mapped_row=mapped,
                        record_table=WAREHOUSE_CUSTOM_FIELD_TABLE,
                        fields_by_code=custom_fields_by_code,
                        string_fields=WAREHOUSE_SYNC_STRING_FIELDS,
                        bool_fields=WAREHOUSE_SYNC_BOOL_FIELDS,
                    )
                except Exception as cf_exc:
                    errors.append(f"仓库 {record.code} 扩展字段：{cf_exc}")

        async def _flush_updates(batch: List[Warehouse], start_index: int) -> None:
            nonlocal updated, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量更新仓库 {start_index}-{end_index}/{len(to_update)}…"
            )
            try:
                await Warehouse.bulk_update(
                    batch, fields=WAREHOUSE_BULK_UPDATE_FIELDS, batch_size=_WRITE_BATCH
                )
                updated += len(batch)
                await _write_extras(batch)
            except Exception:
                for record in batch:
                    try:
                        await record.save(update_fields=WAREHOUSE_BULK_UPDATE_FIELDS)
                        updated += 1
                        await _write_extras([record])
                    except Exception as row_exc:
                        failed += 1
                        errors.append(f"仓库 {record.code}：{row_exc}")

        async def _flush_creates(batch: List[Warehouse], start_index: int) -> None:
            nonlocal created, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量新建仓库 {start_index}-{end_index}/{len(to_create)}…"
            )
            try:
                await Warehouse.bulk_create(batch, batch_size=_WRITE_BATCH)
                created += len(batch)
                codes_created = [item.code for item in batch]
                persisted = await Warehouse.filter(
                    tenant_id=tenant_id,
                    code__in=codes_created,
                    deleted_at__isnull=True,
                ).all()
                await _write_extras(persisted)
            except Exception:
                for record in batch:
                    try:
                        await record.save()
                        created += 1
                        await _write_extras([record])
                    except Exception as row_exc:
                        failed += 1
                        errors.append(f"仓库 {record.code}：{row_exc}")

        for offset in range(0, len(to_update), _WRITE_BATCH):
            await _flush_updates(to_update[offset : offset + _WRITE_BATCH], offset + 1)
        for offset in range(0, len(to_create), _WRITE_BATCH):
            await _flush_creates(to_create[offset : offset + _WRITE_BATCH], offset + 1)

        await emit_sync_progress(
            f"仓库写入完成：新建 {created}，更新 {updated}，跳过 {skipped}，失败 {failed}"
        )
        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
