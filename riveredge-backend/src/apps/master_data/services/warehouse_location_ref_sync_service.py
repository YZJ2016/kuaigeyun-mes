"""仓库库位关系同步：苍穹 bd_warelocareference → 本地库位 warehouse_id。"""
from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from infra.exceptions.exceptions import ValidationError
from infra.models.user import User

from apps.master_data.models.master_data_sync_binding import WarehouseLocationRefSyncBinding
from apps.master_data.models.warehouse import StorageLocation, Warehouse
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.common.audit_actor import apply_create_audit, apply_restore_audit, apply_update_audit
from apps.master_data.services.master_data_sync_common import (
    attach_sync_fetch_meta,
    cell_str,
    mark_binding_failure,
    mark_binding_success,
    normalize_schedule_interval,
    normalize_sync_mode,
    sync_record_needs_update,
    resolve_incremental_since,
    resolve_sync_sources,
    serialize_binding_row,
    sources_from_upsert_body,
    upsert_sync_binding,
    resolve_upsert_schedule_from_body,
    resolve_schedule_window_for_sync_request,
)
from core.services.data.sync_binding_sources import fetch_mapped_rows_from_sources
from core.services.data.sync_progress import emit_sync_progress
from core.utils.timezone_utils import resolve_business_datetime

LOCATION_REF_BULK_UPDATE_FIELDS = [
    "name",
    "warehouse_id",
    "source_location_code",
    "external_sync_at",
    "updated_at",
    "updated_by",
    "updated_by_name",
]
_WRITE_BATCH = 500


def _coerce_is_default_loc(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    val = cell_str(raw).upper()
    return val in ("1", "TRUE", "Y", "YES", "T")


async def _inject_warehouse_batch_fill_sources(
    tenant_id: int,
    sources: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """未配置批量填入时，按本地仓库编码分批调用 data.warehouse_number。"""
    out = copy.deepcopy(sources)
    wh_rows = await Warehouse.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        is_active=True,
    ).values_list("code", flat=True)
    codes = [str(code).strip() for code in wh_rows if str(code).strip()]
    if not codes:
        raise ValidationError("本地尚无仓库编码，请先同步仓库后再同步库位关系")
    for src in out:
        if str(src.get("kind") or "").strip() != "api":
            continue
        existing = src.get("batch_fill_values")
        if isinstance(existing, list) and [str(v).strip() for v in existing if str(v).strip()]:
            continue
        if str(src.get("batch_fill_path") or "").strip():
            continue
        src["batch_fill_path"] = "data.warehouse_number"
        src["batch_fill_values"] = codes
    return out


def _warehouse_codes_per_source_location(rows: List[Dict[str, Any]], match_key: str) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = defaultdict(set)
    for row in rows:
        loc_code = cell_str(
            row.get("location_code")
            if match_key == "location_code"
            else row.get(match_key) or row.get("location_code")
        )
        wh_code = cell_str(row.get("warehouse_code"))
        if not loc_code or not wh_code:
            continue
        out[loc_code.strip().upper()].add(wh_code.strip().upper())
    return out


def _resolve_local_storage_location_code(
    source_location_code: str,
    warehouse_code: str,
    *,
    multi_warehouse_source_locations: Set[str],
) -> str:
    """
    同一苍穹库位编码挂多仓（如「无货架」）时，本地编码按 仓库_库位 区分；
    一仓一码的库位仍用原编码。
    """
    loc = source_location_code.strip().upper()
    wh = warehouse_code.strip().upper()
    if loc not in multi_warehouse_source_locations:
        return loc
    composite = f"{wh}_{loc}"
    if len(composite) <= 50:
        return composite
    budget = 50 - len(wh) - 1
    if budget < 1:
        return wh[:50]
    return f"{wh}_{loc[:budget]}"


def _pick_warehouse_row(group_rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], int]:
    """同一库位多行：优先 isdefaultloc，否则第一条；返回选中行与忽略条数。"""
    default_rows = [row for row in group_rows if _coerce_is_default_loc(row.get("is_default_loc"))]
    if default_rows:
        winner = default_rows[0]
        ignored = len(group_rows) - 1
        return winner, ignored
    return group_rows[0], len(group_rows) - 1


class WarehouseLocationRefSyncService:
    MATCH_KEY = "location_code"

    def serialize_binding(
        self, row: Optional[WarehouseLocationRefSyncBinding]
    ) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await WarehouseLocationRefSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut()
        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval, w_start, w_end = await resolve_upsert_schedule_from_body(
            WarehouseLocationRefSyncBinding, tenant_id, body
        )
        row = await upsert_sync_binding(
            WarehouseLocationRefSyncBinding,
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
        row = await WarehouseLocationRefSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: User,
        request: Optional[MasterDataSyncFromSourceRequest] = None,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            WarehouseLocationRefSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )
        binding = binding or await WarehouseLocationRefSyncBinding.filter(tenant_id=tenant_id).first()
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
            binding = await WarehouseLocationRefSyncBinding.filter(tenant_id=tenant_id).first()
        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )
        try:
            await emit_sync_progress("开始同步仓库库位关系…")
            sources = await _inject_warehouse_batch_fill_sources(tenant_id, sources)
            rows, source_errors, fetched = await fetch_mapped_rows_from_sources(
                tenant_id,
                sources,
                since=since,
                active_only=req.active_only,
            )
            result = await self._apply_location_warehouse_refs(
                tenant_id, current_user, rows, match_key
            )
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            attach_sync_fetch_meta(result, fetched=fetched, since=since, truncated=False)
            if binding:
                if result.failed and not (result.created or result.updated):
                    await mark_binding_failure(
                        binding, "; ".join(result.errors) or "仓库库位关系同步失败"
                    )
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    async def _apply_location_warehouse_refs(
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
        sync_at = resolve_business_datetime()

        loc_to_whs = _warehouse_codes_per_source_location(rows, match_key)
        multi_wh_locs = {loc for loc, whs in loc_to_whs.items() if len(whs) > 1}

        grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            loc_code = cell_str(
                row.get("location_code")
                if match_key == "location_code"
                else row.get(match_key) or row.get("location_code")
            )
            wh_code = cell_str(row.get("warehouse_code"))
            if not loc_code:
                skipped += 1
                errors.append("存在缺少库位编码的关系行，已跳过")
                continue
            if not wh_code:
                skipped += 1
                errors.append(f"库位 {loc_code} 缺少仓库编码，已跳过")
                continue
            loc_key = loc_code.strip().upper()
            wh_key = wh_code.strip().upper()
            grouped[(loc_key, wh_key)].append(row)

        PendingRow = Tuple[str, str, str, str]
        pending: List[PendingRow] = []
        for (source_loc_code, wh_key), group_rows in grouped.items():
            winner, ignored = _pick_warehouse_row(group_rows)
            if ignored > 0:
                skipped += ignored
                errors.append(
                    f"库位 {source_loc_code} / 仓库 {wh_key}：重复关系已忽略（共 {ignored} 条）"
                )
            loc_name = cell_str(winner.get("location_name"))
            local_code = _resolve_local_storage_location_code(
                source_loc_code,
                wh_key,
                multi_warehouse_source_locations=multi_wh_locs,
            )
            if not loc_name:
                failed += 1
                errors.append(
                    f"库位 {source_loc_code}（本地 {local_code}）缺少名称（请映射 location_name），无法创建"
                )
                continue
            pending.append((source_loc_code, wh_key, local_code, loc_name))

        if not pending:
            return MasterDataSyncFromSourceOut(
                created=created,
                updated=updated,
                skipped=skipped,
                failed=failed,
                errors=errors[:20],
            )

        total = len(pending)
        await emit_sync_progress(f"正在预加载仓库与库位，准备写入 {total} 条关系…")

        wh_codes = sorted({item[1] for item in pending})
        warehouse_by_code: Dict[str, Warehouse] = {}
        for offset in range(0, len(wh_codes), 2000):
            chunk = wh_codes[offset : offset + 2000]
            for wh in await Warehouse.filter(
                tenant_id=tenant_id,
                code__in=chunk,
                deleted_at__isnull=True,
            ).all():
                warehouse_by_code[wh.code.upper()] = wh

        local_codes = [item[2] for item in pending]
        location_by_code: Dict[str, StorageLocation] = {}
        soft_deleted_by_code: Dict[str, StorageLocation] = {}
        for offset in range(0, len(local_codes), 2000):
            chunk = local_codes[offset : offset + 2000]
            for loc in await StorageLocation.filter(
                tenant_id=tenant_id,
                code__in=chunk,
                deleted_at__isnull=True,
            ).all():
                location_by_code[loc.code.upper()] = loc
            for loc in await StorageLocation.filter(
                tenant_id=tenant_id,
                code__in=chunk,
                deleted_at__isnull=False,
            ).all():
                soft_deleted_by_code[loc.code.upper()] = loc

        to_update: List[StorageLocation] = []
        to_create: List[StorageLocation] = []

        for index, (source_loc_code, wh_key, local_code, loc_name) in enumerate(
            pending, start=1
        ):
            if index == 1 or index == total or index % 200 == 0:
                await emit_sync_progress(f"正在解析库位关系 {index}/{total}：{local_code}")
            warehouse = warehouse_by_code.get(wh_key)
            if not warehouse:
                failed += 1
                errors.append(f"仓库 {wh_key} 不存在，请先同步仓库")
                continue
            wh_id = int(warehouse.id)
            loc_key = local_code.upper()
            existing = location_by_code.get(loc_key)
            proposed = {
                "name": loc_name,
                "warehouse_id": wh_id,
                "source_location_code": source_loc_code,
            }
            try:
                if existing:
                    if not sync_record_needs_update(existing, proposed):
                        skipped += 1
                        continue
                    existing.name = loc_name
                    existing.warehouse_id = wh_id
                    existing.source_location_code = source_loc_code
                    existing.external_sync_at = sync_at
                    existing.updated_at = sync_at
                    if current_user is not None:
                        apply_update_audit(existing, current_user)
                    to_update.append(existing)
                    continue
                soft = soft_deleted_by_code.get(loc_key)
                if soft:
                    soft.deleted_at = None
                    soft.name = loc_name
                    soft.warehouse_id = wh_id
                    soft.source_location_code = source_loc_code
                    soft.is_active = True
                    soft.external_sync_at = sync_at
                    soft.updated_at = sync_at
                    apply_restore_audit(soft, current_user)
                    to_update.append(soft)
                    continue
                payload: Dict[str, Any] = {
                    "tenant_id": tenant_id,
                    "code": local_code,
                    "name": loc_name,
                    "source_location_code": source_loc_code,
                    "warehouse_id": wh_id,
                    "storage_area_id": None,
                    "is_active": True,
                    "external_sync_at": sync_at,
                }
                if current_user is not None:
                    apply_create_audit(payload, current_user)
                to_create.append(StorageLocation(**payload))
            except Exception as exc:
                failed += 1
                errors.append(f"库位 {source_loc_code}（本地 {local_code}）：{exc}")

        async def _flush_updates(batch: List[StorageLocation], start_index: int) -> None:
            nonlocal updated, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量更新库位 {start_index}-{end_index}/{len(to_update)}…"
            )
            try:
                await StorageLocation.bulk_update(
                    batch, fields=LOCATION_REF_BULK_UPDATE_FIELDS, batch_size=_WRITE_BATCH
                )
                updated += len(batch)
            except Exception:
                for record in batch:
                    try:
                        await record.save(update_fields=LOCATION_REF_BULK_UPDATE_FIELDS)
                        updated += 1
                    except Exception as row_exc:
                        failed += 1
                        errors.append(f"库位 {record.code}：{row_exc}")

        async def _flush_creates(batch: List[StorageLocation], start_index: int) -> None:
            nonlocal created, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量新建库位 {start_index}-{end_index}/{len(to_create)}…"
            )
            try:
                await StorageLocation.bulk_create(batch, batch_size=_WRITE_BATCH)
                created += len(batch)
            except Exception:
                for record in batch:
                    try:
                        await record.save()
                        created += 1
                    except Exception as row_exc:
                        failed += 1
                        errors.append(f"库位 {record.code}：{row_exc}")

        for offset in range(0, len(to_update), _WRITE_BATCH):
            await _flush_updates(to_update[offset : offset + _WRITE_BATCH], offset + 1)
        for offset in range(0, len(to_create), _WRITE_BATCH):
            await _flush_creates(to_create[offset : offset + _WRITE_BATCH], offset + 1)

        await emit_sync_progress(
            f"库位关系写入完成：新建 {created}，更新 {updated}，跳过 {skipped}，失败 {failed}"
        )
        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
