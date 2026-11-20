"""物料辅单位同步：苍穹 bd_multimeasureunit → Material.units.units（保留 scenarios）。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from tortoise.expressions import Q

from infra.exceptions.exceptions import ValidationError
from infra.models.user import User

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.master_data.constants.material_conversion_type import (
    CONVERSION_TYPE_FIXED,
    CONVERSION_TYPE_FLOATING,
)
from apps.master_data.models.master_data_sync_binding import MaterialMultiUnitSyncBinding
from apps.master_data.models.material import Material
from apps.master_data.models.unit import MaterialUnit
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.master_data.services.material_service import _normalize_material_units_json
from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import (
    attach_sync_fetch_meta,
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


def _coerce_int_positive(raw: object, default: int = 1) -> int:
    try:
        val = int(raw if raw not in (None, "") else default)
    except (TypeError, ValueError):
        val = default
    if val <= 0:
        return default
    return val


def _conversion_type_from_kingdee(raw: object) -> Tuple[str, bool]:
    """converttype：1 固定，2 浮动；其它按 fixed 并标记需记日志。"""
    val = cell_str(raw)
    if val == "2":
        return CONVERSION_TYPE_FLOATING, False
    if val in ("1", ""):
        return CONVERSION_TYPE_FIXED, False
    return CONVERSION_TYPE_FIXED, True


def _build_aux_unit_row(mapped: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    unit_code = cell_str(mapped.get("unit_code"))
    if not unit_code:
        return None, "缺少辅单位编码"
    conv_raw = mapped.get("conversion_type")
    if conv_raw is None or not str(conv_raw).strip():
        conv_raw = mapped.get("converttype")
    conv_type, unknown_conv = _conversion_type_from_kingdee(conv_raw)
    row: Dict[str, Any] = {"unit": unit_code, "conversionType": conv_type}
    if conv_type == CONVERSION_TYPE_FLOATING:
        if unknown_conv:
            return row, f"辅单位 {unit_code} 换算类型 {cell_str(conv_raw)!r} 未识别，已按固定换算处理"
        return row, None
    row["numerator"] = _coerce_int_positive(mapped.get("numerator"), 1)
    row["denominator"] = _coerce_int_positive(mapped.get("denominator"), 1)
    if unknown_conv:
        return row, f"辅单位 {unit_code} 换算类型 {cell_str(conv_raw)!r} 未识别，已按固定换算处理"
    return row, None


class MaterialMultiUnitSyncService:
    MATCH_KEY = "material_code"

    def serialize_binding(
        self, row: Optional[MaterialMultiUnitSyncBinding]
    ) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await MaterialMultiUnitSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut(match_key_field=self.MATCH_KEY)
        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval, w_start, w_end = await resolve_upsert_schedule_from_body(
            MaterialMultiUnitSyncBinding, tenant_id, body
        )
        row = await upsert_sync_binding(
            MaterialMultiUnitSyncBinding,
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
        row = await MaterialMultiUnitSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: User,
        request: Optional[MasterDataSyncFromSourceRequest] = None,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            MaterialMultiUnitSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )
        binding = binding or await MaterialMultiUnitSyncBinding.filter(tenant_id=tenant_id).first()
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
            binding = await MaterialMultiUnitSyncBinding.filter(tenant_id=tenant_id).first()
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
            result = await self._apply_material_aux_units(
                tenant_id, current_user, rows, match_key
            )
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            attach_sync_fetch_meta(result, fetched=fetched, since=since, truncated=False)
            if binding:
                if result.failed and not (result.updated or result.created):
                    await mark_binding_failure(
                        binding, "; ".join(result.errors) or "物料多单位同步失败"
                    )
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    async def _ensure_material_unit(
        self,
        tenant_id: int,
        current_user: User,
        unit_code: str,
        unit_name: str,
    ) -> None:
        code = unit_code.strip()
        name = (unit_name or code).strip()
        existing = await MaterialUnit.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            code=code,
        ).first()
        if existing:
            if name and name != existing.name:
                existing.name = name
                apply_update_audit(existing, current_user)
                await existing.save(
                    update_fields=[
                        "name",
                        "updated_at",
                        "updated_by",
                        "updated_by_name",
                    ]
                )
            return
        by_name = await MaterialUnit.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
            name=name,
        ).first()
        if by_name:
            return
        payload: Dict[str, Any] = {
            "code": code,
            "name": name,
            "is_active": True,
            "is_system": False,
            "sort_order": 0,
        }
        apply_create_audit(payload, current_user)
        await MaterialUnit.create(tenant_id=tenant_id, **payload)

    async def _apply_material_aux_units(
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

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            material_code = cell_str(
                row.get(match_key)
                or row.get("material_code")
                or row.get("materialid_number")
            )
            if not material_code:
                skipped += 1
                errors.append("存在缺少物料编码的多单位行，已跳过")
                continue
            grouped[material_code.strip().upper()].append(row)

        if not grouped:
            return MasterDataSyncFromSourceOut(
                created=created,
                updated=updated,
                skipped=skipped,
                failed=failed,
                errors=errors[:20],
            )

        codes = list(grouped.keys())
        materials = await Material.filter(
            tenant_id=tenant_id,
            deleted_at__isnull=True,
        ).filter(Q(main_code__in=codes) | Q(code__in=codes)).all()
        by_main: Dict[str, Material] = {}
        for mat in materials:
            main = cell_str(mat.main_code or mat.code).upper()
            if main:
                by_main[main] = mat

        for material_code, group_rows in grouped.items():
            material = by_main.get(material_code)
            if not material:
                skipped += len(group_rows)
                continue
            base_unit = cell_str(material.base_unit).upper()
            aux_by_unit: Dict[str, Dict[str, Any]] = {}
            unit_names: Dict[str, str] = {}
            for mapped in group_rows:
                unit_code = cell_str(mapped.get("unit_code") or mapped.get("measureunitid_number"))
                if not unit_code:
                    skipped += 1
                    continue
                if unit_code.upper() == base_unit:
                    skipped += 1
                    continue
                unit_name = cell_str(
                    mapped.get("unit_name") or mapped.get("measureunitid_name") or unit_code
                )
                aux_row, warn = _build_aux_unit_row({**mapped, "unit_code": unit_code})
                if not aux_row:
                    skipped += 1
                    if warn:
                        errors.append(warn)
                    continue
                if warn:
                    errors.append(warn)
                key = unit_code.upper()
                aux_by_unit[key] = aux_row
                unit_names[key] = unit_name

            if not aux_by_unit:
                skipped += 1
                continue

            try:
                for u_code, u_name in unit_names.items():
                    await self._ensure_material_unit(
                        tenant_id, current_user, u_code, u_name
                    )
                existing_units = material.units if isinstance(material.units, dict) else {}
                payload = dict(existing_units)
                payload["units"] = list(aux_by_unit.values())
                normalized = _normalize_material_units_json(payload)
                if normalized == material.units:
                    skipped += 1
                    continue
                material.units = normalized
                apply_update_audit(material, current_user)
                await material.save(
                    update_fields=[
                        "units",
                        "updated_at",
                        "updated_by",
                        "updated_by_name",
                    ]
                )
                updated += 1
            except ValidationError as exc:
                failed += 1
                errors.append(f"物料 {material_code}：{exc}")
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
