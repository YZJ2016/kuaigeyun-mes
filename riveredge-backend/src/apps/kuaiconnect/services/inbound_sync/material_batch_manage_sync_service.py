"""物料批号管理同步：金蝶物料库存信息（bd_materialinventoryinfo.enablelot）→ Material.batch_managed。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from tortoise.expressions import Q

from infra.exceptions.exceptions import ValidationError
from infra.models.user import User

from apps.common.audit_actor import apply_update_audit
from apps.master_data.models.master_data_sync_binding import MaterialBatchManageSyncBinding
from apps.master_data.models.material import Material
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import (
    attach_sync_fetch_meta,
    cell_optional_bool,
    cell_str,
    mark_binding_failure,
    mark_binding_success,
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


def _path_is_material_inventory_info(path: str) -> bool:
    lower = (path or "").lower().replace("\\", "/")
    return "bd_materialinventoryinfo" in lower


class MaterialBatchManageSyncService:
    MATCH_KEY = "material_code"

    def serialize_binding(
        self, row: Optional[MaterialBatchManageSyncBinding]
    ) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await MaterialBatchManageSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut(match_key_field=self.MATCH_KEY)
        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval, w_start, w_end = await resolve_upsert_schedule_from_body(
            MaterialBatchManageSyncBinding, tenant_id, body
        )
        row = await upsert_sync_binding(
            MaterialBatchManageSyncBinding,
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
        row = await MaterialBatchManageSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def _resolve_inventory_helper_context(
        self,
        tenant_id: int,
        sources: List[Dict[str, Any]],
    ) -> Optional[Tuple[UUID, Optional[str]]]:
        """绑定接口为物料库存信息时，走专用拉取（含 612 路径回退）。"""
        from core.models.api import API
        from core.services.integration.kingdee_cosmic_material_org_scope import (
            resolve_connector_org_for_material_scope,
        )

        for src in sources:
            api_uuid = str(src.get("api_uuid") or "").strip() or None
            if not api_uuid:
                continue
            api_obj = await API.filter(
                tenant_id=tenant_id,
                uuid=api_uuid,
                deleted_at__isnull=True,
            ).first()
            if api_obj is None:
                continue
            if not _path_is_material_inventory_info(str(getattr(api_obj, "path", "") or "")):
                continue
            await api_obj.fetch_related("integration_config")
            conn = getattr(api_obj, "integration_config", None)
            if conn is None:
                continue
            conn_type = str(getattr(conn, "type", "") or "").strip()
            if conn_type not in ("kingdee_cosmic", "kingdee_xinghan", "kingdee_ai_suite"):
                continue
            org = resolve_connector_org_for_material_scope(conn.get_config())
            return conn.uuid, org or None
        return None

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: User,
        request: Optional[MasterDataSyncFromSourceRequest] = None,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            MaterialBatchManageSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )
        binding = binding or await MaterialBatchManageSyncBinding.filter(tenant_id=tenant_id).first()
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
            binding = await MaterialBatchManageSyncBinding.filter(tenant_id=tenant_id).first()
        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )
        try:
            helper_ctx = await self._resolve_inventory_helper_context(tenant_id, sources)
            source_errors: List[str] = []
            if helper_ctx is not None:
                from core.services.integration.kingdee_cosmic_material_inventory_info import (
                    fetch_cosmic_material_inventory_tracking_by_number,
                )

                connection_uuid, org_number = helper_ctx
                tracking = await fetch_cosmic_material_inventory_tracking_by_number(
                    tenant_id,
                    connection_uuid=connection_uuid,
                    org_number=org_number,
                    active_only=req.active_only,
                )
                rows = [
                    {
                        "material_code": number,
                        "batch_managed": flags.get("enablelot"),
                    }
                    for number, flags in tracking.items()
                    if isinstance(flags, dict) and flags.get("enablelot") is not None
                ]
                fetched = len(tracking)
            else:
                rows, source_errors, fetched = await fetch_mapped_rows_from_sources(
                    tenant_id,
                    sources,
                    since=since,
                    active_only=req.active_only,
                )
            result = await self._apply_batch_managed(
                tenant_id, current_user, rows, match_key
            )
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            attach_sync_fetch_meta(result, fetched=fetched, since=since, truncated=False)
            if binding:
                if result.failed and not (result.updated or result.created):
                    await mark_binding_failure(
                        binding, "; ".join(result.errors) or "物料批号管理同步失败"
                    )
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    async def _apply_batch_managed(
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

        desired: Dict[str, bool] = {}
        for row in rows:
            material_code = cell_str(
                row.get(match_key)
                or row.get("material_code")
                or row.get("masterid_number")
                or row.get("number")
            )
            if not material_code:
                skipped += 1
                continue
            try:
                flag = cell_optional_bool(
                    row.get("batch_managed")
                    if "batch_managed" in row
                    else row.get("enablelot")
                )
            except ValidationError as exc:
                failed += 1
                errors.append(f"物料 {material_code}：{exc}")
                continue
            if flag is None:
                skipped += 1
                continue
            desired[material_code.strip().upper()] = flag

        if not desired:
            return MasterDataSyncFromSourceOut(
                created=created,
                updated=updated,
                skipped=skipped,
                failed=failed,
                errors=errors[:20],
            )

        codes = list(desired.keys())
        materials = await Material.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).filter(Q(main_code__in=codes) | Q(code__in=codes)).all()
        by_main: Dict[str, Material] = {}
        for mat in materials:
            main = cell_str(mat.main_code or mat.code).upper()
            if main:
                by_main[main] = mat

        for material_code, flag in desired.items():
            material = by_main.get(material_code)
            if not material:
                skipped += 1
                continue
            if bool(getattr(material, "batch_managed", False)) is flag:
                skipped += 1
                continue
            try:
                material.batch_managed = flag
                apply_update_audit(material, current_user)
                await material.save(
                    update_fields=[
                        "batch_managed",
                        "updated_at",
                        "updated_by",
                        "updated_by_name",
                    ]
                )
                updated += 1
            except Exception as exc:
                failed += 1
                errors.append(f"物料 {material_code}：{exc}")

        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
