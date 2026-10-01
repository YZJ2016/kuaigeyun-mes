"""工程 BOM 从数据接口/数据集同步。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.master_data.models.master_data_sync_binding import EngineeringBomSyncBinding
from apps.master_data.models.material import BOM, Material
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.master_data.services.master_data_sync_common import (
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

BOM_SYNC_STRING_FIELDS = frozenset({"unit", "description", "remark", "bom_code", "bom_name", "issue_method"})
BOM_SYNC_BOOL_FIELDS = frozenset({"is_required", "is_active", "is_alternative"})


def _to_decimal(value: Any, default: Decimal = Decimal("1")) -> Decimal:
    if value is None or str(value).strip() == "":
        return default
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return default


def _build_line_key(parent: str, version: str, component: str) -> str:
    return f"{parent}|{version}|{component}"


class EngineeringBomSyncService:
    MATCH_KEY = "line_key"

    def serialize_binding(self, row: Optional[EngineeringBomSyncBinding]) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await EngineeringBomSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut(match_key_field=self.MATCH_KEY)

        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval = normalize_schedule_interval(body.schedule_interval_minutes)
        row = await upsert_sync_binding(
            EngineeringBomSyncBinding,
            tenant_id,
            sources=sources,
            match_key_field=match_key,
            sync_mode=sync_mode,
            schedule_interval_minutes=interval,
        )
        return self.serialize_binding(row)

    async def get_binding(self, tenant_id: int) -> MasterDataSyncBindingOut:
        row = await EngineeringBomSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: Optional[User],
        request: Optional[MasterDataSyncFromSourceRequest] = None,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            EngineeringBomSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )

        binding = binding or await EngineeringBomSyncBinding.filter(tenant_id=tenant_id).first()
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
            binding = await EngineeringBomSyncBinding.filter(tenant_id=tenant_id).first()

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
            result = await self._upsert_bom_lines(tenant_id, current_user, rows, match_key)
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            if binding:
                if result.failed and not (result.created or result.updated):
                    await mark_binding_failure(binding, "; ".join(result.errors) or "BOM同步失败")
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    async def _upsert_bom_lines(
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

        materials = await Material.filter(tenant_id=tenant_id, deleted_at__isnull=True).all()
        by_code: Dict[str, Material] = {}
        for m in materials:
            for key in (
                str(getattr(m, "main_code", None) or "").strip(),
                str(getattr(m, "code", None) or "").strip(),
            ):
                if key and key not in by_code:
                    by_code[key] = m

        for row in rows:
            parent_code = cell_str(
                row.get("parent_code")
                or row.get("material_code")
                or row.get("parent_main_code")
            )
            component_code = cell_str(
                row.get("component_code")
                or row.get("child_code")
                or row.get("component_main_code")
            )
            version = cell_str(row.get("version")) or "1.0"
            if match_key == "line_key" and not parent_code:
                line_key = cell_str(row.get("line_key") or row.get(match_key))
                if line_key and "|" in line_key:
                    parts = line_key.split("|")
                    if len(parts) >= 3:
                        parent_code, version, component_code = parts[0], parts[1], parts[2]
            if not parent_code or not component_code:
                skipped += 1
                errors.append("存在缺少父件/子件编码的 BOM 行，已跳过")
                continue

            parent = by_code.get(parent_code)
            component = by_code.get(component_code)
            if not parent or not component:
                skipped += 1
                errors.append(f"BOM {parent_code}/{component_code} 物料不存在，已跳过")
                continue

            qty = _to_decimal(row.get("quantity"), Decimal("1"))
            base_qty = _to_decimal(row.get("base_quantity"), Decimal("1"))
            waste = _to_decimal(row.get("waste_rate"), Decimal("0"))
            bom_code = cell_str(row.get("bom_code")) or None
            bom_name = cell_str(row.get("bom_name")) or None
            unit = cell_str(row.get("unit")) or None
            is_required_raw = row.get("is_required")
            is_required = True
            if is_required_raw is not None and str(is_required_raw).strip():
                is_required = str(is_required_raw).strip().lower() not in (
                    "0",
                    "false",
                    "no",
                    "n",
                    "否",
                )

            try:
                existing = await BOM.filter(
                    tenant_id=tenant_id,
                    material_id=parent.id,
                    component_id=component.id,
                    version=version,
                    deleted_at__isnull=True,
                ).first()
                if existing:
                    existing.quantity = qty
                    existing.base_quantity = base_qty
                    existing.waste_rate = waste
                    existing.is_required = is_required
                    if unit is not None:
                        existing.unit = unit
                    if bom_code is not None:
                        existing.bom_code = bom_code
                    if bom_name is not None:
                        existing.bom_name = bom_name
                    existing.external_sync_at = sync_at
                    apply_update_audit(existing, current_user)
                    await existing.save()
                    await mark_external_sync_record(existing)
                    updated += 1
                else:
                    payload: Dict[str, Any] = {
                        "material_id": parent.id,
                        "component_id": component.id,
                        "quantity": qty,
                        "base_quantity": base_qty,
                        "waste_rate": waste,
                        "is_required": is_required,
                        "unit": unit,
                        "version": version,
                        "bom_code": bom_code,
                        "bom_name": bom_name,
                        "is_active": True,
                        "approval_status": "draft",
                        "external_sync_at": sync_at,
                    }
                    apply_create_audit(payload, current_user)
                    bom = await BOM.create(tenant_id=tenant_id, **payload)
                    await mark_external_sync_record(bom)
                    created += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                errors.append(f"BOM {_build_line_key(parent_code, version, component_code)}: {exc}")

        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
