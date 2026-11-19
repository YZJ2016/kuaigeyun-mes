"""供应商从数据接口/数据集同步。"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from infra.exceptions.exceptions import ValidationError
from infra.models.user import User
from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.master_data.models.master_data_sync_binding import SupplierSyncBinding
from apps.master_data.models.supplier import Supplier
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.master_data.services.master_data_sync_common import (
    apply_mapped_custom_field_values,
    apply_mapped_scalar_fields,
    cell_optional_bool,
    cell_optional_decimal,
    cell_optional_int,
    cell_str,
    fetch_sync_rows,
    filter_kingdee_approved_active_master_rows,
    load_custom_fields_by_code,
    map_sync_rows,
    mark_binding_failure,
    mark_binding_success,
    normalize_schedule_interval,
    normalize_sync_mode,
    record_fields_unchanged,
    resolve_incremental_since,
    resolve_sync_sources,
    serialize_binding_row,
    sources_from_upsert_body,
    upsert_sync_binding,
)
from core.services.data.sync_binding_sources import fetch_mapped_rows_from_sources
from apps.master_data.services.supply_chain_service import _normalize_partner_name
from core.services.data.sync_progress import emit_sync_progress
from core.utils.timezone_utils import resolve_business_datetime

SUPPLIER_CUSTOM_FIELD_TABLE = "master_data_suppliers"
SUPPLIER_SYNC_STRING_FIELDS = frozenset({
    "contact_person", "phone", "email", "address", "category", "contact_title",
    "industry_code", "source_channel_code", "tax_registration_no", "invoice_title",
    "invoice_address", "invoice_phone", "invoice_bank_name", "invoice_bank_account",
    "invoice_type_code", "taxpayer_type_code", "legal_representative",
    "enterprise_type_code", "settlement_method_code", "buyer_name",
})
SUPPLIER_SYNC_BOOL_FIELDS = frozenset({"is_active"})
SUPPLIER_SYNC_DECIMAL_FIELDS = frozenset({"estimated_annual_purchase", "credit_limit"})
SUPPLIER_SYNC_INT_FIELDS = frozenset({"payment_terms_days"})
SUPPLIER_PAYMENT_ACCOUNT_SYNC_FIELDS = (
    "payment_account_name",
    "payment_bank_name",
    "payment_bank_account",
)
_PAYMENT_ACCOUNT_COLUMN = {
    "payment_account_name": "account_name",
    "payment_bank_name": "bank_name",
    "payment_bank_account": "bank_account",
}

SUPPLIER_BULK_UPDATE_FIELDS = sorted(
    {
        "name",
        "short_name",
        "external_sync_at",
        "updated_at",
        "updated_by",
        "updated_by_name",
        "settlement_accounts",
        *SUPPLIER_SYNC_STRING_FIELDS,
        *SUPPLIER_SYNC_BOOL_FIELDS,
        *SUPPLIER_SYNC_DECIMAL_FIELDS,
        *SUPPLIER_SYNC_INT_FIELDS,
    }
)


def apply_supplier_payment_account_sync(record: Supplier, mapped_row: Dict[str, Any]) -> bool:
    """把同步行里的付款户名、开户银行、付款账号写入默认付款账户。"""
    present = [key for key in SUPPLIER_PAYMENT_ACCOUNT_SYNC_FIELDS if key in mapped_row]
    if not present:
        return False
    rows = record.settlement_accounts if isinstance(record.settlement_accounts, list) else []
    accounts = [dict(row) for row in rows if isinstance(row, dict)]
    target = next((row for row in accounts if row.get("is_default")), None)
    if target is None and accounts:
        target = accounts[0]
    if target is None:
        target = {
            "account_name": None,
            "bank_name": None,
            "bank_account": None,
            "is_default": True,
        }
        accounts = [target]
    for key in present:
        target[_PAYMENT_ACCOUNT_COLUMN[key]] = cell_str(mapped_row.get(key)) or None
    kept = [
        row
        for row in accounts
        if any(row.get(column) for column in ("account_name", "bank_name", "bank_account"))
    ]
    if kept and not any(row.get("is_default") for row in kept):
        kept[0]["is_default"] = True
    record.settlement_accounts = kept
    return True


def _supplier_sync_has_custom_mapping(mapped_row: Dict[str, Any]) -> bool:
    return any(str(key).startswith("custom:") for key in mapped_row)


def _supplier_sync_proposed_core(
    name: str,
    mapped_row: Dict[str, Any],
) -> Dict[str, Any]:
    proposed: Dict[str, Any] = {
        "name": _normalize_partner_name(name),
        "short_name": cell_str(mapped_row.get("short_name")) or None,
    }
    for field_name in SUPPLIER_SYNC_STRING_FIELDS:
        if field_name in mapped_row:
            proposed[field_name] = cell_str(mapped_row.get(field_name)) or None
    for field_name in SUPPLIER_SYNC_BOOL_FIELDS:
        if field_name in mapped_row:
            coerced = cell_optional_bool(mapped_row.get(field_name))
            if coerced is not None:
                proposed[field_name] = coerced
    for field_name in SUPPLIER_SYNC_DECIMAL_FIELDS:
        if field_name in mapped_row:
            coerced = cell_optional_decimal(mapped_row.get(field_name))
            if coerced is not None:
                proposed[field_name] = coerced
    for field_name in SUPPLIER_SYNC_INT_FIELDS:
        if field_name in mapped_row:
            coerced = cell_optional_int(mapped_row.get(field_name))
            if coerced is not None:
                proposed[field_name] = coerced
    return proposed


def _apply_supplier_mapped_fields(record: Supplier, mapped_row: Dict[str, Any]) -> List[str]:
    touched = apply_mapped_scalar_fields(
        record,
        mapped_row,
        string_fields=SUPPLIER_SYNC_STRING_FIELDS,
        bool_fields=SUPPLIER_SYNC_BOOL_FIELDS,
        decimal_fields=SUPPLIER_SYNC_DECIMAL_FIELDS,
        int_fields=SUPPLIER_SYNC_INT_FIELDS,
    )
    if apply_supplier_payment_account_sync(record, mapped_row):
        touched.append("settlement_accounts")
    return touched


class SupplierSyncService:
    MATCH_KEY = "code"
    def serialize_binding(self, row: Optional[SupplierSyncBinding]) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)
    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await SupplierSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut()
        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval = normalize_schedule_interval(body.schedule_interval_minutes)
        row = await upsert_sync_binding(
            SupplierSyncBinding,
            tenant_id,
            sources=sources,
            match_key_field=match_key,
            sync_mode=sync_mode,
            schedule_interval_minutes=interval,
        )
        return self.serialize_binding(row)
    async def get_binding(self, tenant_id: int) -> MasterDataSyncBindingOut:
        row = await SupplierSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)
    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: User,
        request: Optional[MasterDataSyncFromSourceRequest] = None,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            SupplierSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )
        binding = binding or await SupplierSyncBinding.filter(tenant_id=tenant_id).first()
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
            binding = await SupplierSyncBinding.filter(tenant_id=tenant_id).first()
        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )
        try:
            from core.models.api import API

            invalid_skipped_holder = {"n": 0}
            org_allowed = None
            management_org: Optional[str] = None
            use_getsupplier_org_rows = False
            last_source_api_path = ""
            for src in sources:
                api_uuid = str(src.get("api_uuid") or "").strip() or None
                if not api_uuid:
                    continue
                api_obj = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
                if not api_obj:
                    continue
                path_lower = str(getattr(api_obj, "path", "") or "").lower().replace("\\", "/")
                last_source_api_path = path_lower
                from core.services.integration.kingdee_cosmic_supplier_org_scope import (
                    fetch_cosmic_supplier_org_allowed_numbers,
                    is_cosmic_supplier_getsupplier_api,
                    resolve_connector_org_for_supplier_scope,
                )

                api_code = str(getattr(api_obj, "code", "") or "").strip()
                is_getsupplier = is_cosmic_supplier_getsupplier_api(
                    path=path_lower,
                    code=api_code,
                )
                is_query = "/bd_supplier/query" in path_lower and not is_getsupplier
                if not is_query and not is_getsupplier:
                    continue
                await api_obj.fetch_related("integration_config")
                conn = getattr(api_obj, "integration_config", None)
                conn_type = str(getattr(conn, "type", "") or "").strip()
                if conn and conn_type in (
                    "kingdee_cosmic",
                    "kingdee_xinghan",
                    "kingdee_ai_suite",
                ):
                    org = resolve_connector_org_for_supplier_scope(conn.get_config())
                    if org and org.upper() != "BU-00000":
                        if is_getsupplier:
                            use_getsupplier_org_rows = True
                            management_org = org
                            await emit_sync_progress(
                                f"按使用组织 {org} 过滤自定义 getsupplier 返回行…"
                            )
                        elif is_query:
                            await emit_sync_progress(
                                f"拉取管理组织 {org} 的供应商使用范围（bd_suppliercommon）…"
                            )
                            org_allowed = await fetch_cosmic_supplier_org_allowed_numbers(
                                tenant_id,
                                connection_uuid=conn.uuid,
                                org_number=org,
                                active_only=req.active_only,
                            )
                            await emit_sync_progress(
                                f"管理组织供应商使用范围 {len(org_allowed)} 个编码"
                            )
                break

            def _filter_raw(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                out = raw_rows
                if req.active_only:
                    kept, skipped = filter_kingdee_approved_active_master_rows(out)
                    invalid_skipped_holder["n"] += skipped
                    out = kept
                    from core.services.integration.kingdee_cosmic_supplier_org_scope import (
                        filter_cosmic_supplier_rows_active,
                    )

                    before = len(out)
                    out = filter_cosmic_supplier_rows_active(
                        out, path=last_source_api_path
                    )
                    invalid_skipped_holder["n"] += before - len(out)
                if use_getsupplier_org_rows and management_org:
                    from core.services.integration.kingdee_cosmic_supplier_org_scope import (
                        filter_cosmic_supplier_rows_by_management_org_number,
                    )

                    before = len(out)
                    out = filter_cosmic_supplier_rows_by_management_org_number(
                        out, management_org
                    )
                    invalid_skipped_holder["n"] += before - len(out)
                elif org_allowed is not None:
                    from core.services.integration.kingdee_cosmic_supplier_org_scope import (
                        filter_cosmic_supplier_rows_by_org_numbers,
                    )

                    before = len(out)
                    out = filter_cosmic_supplier_rows_by_org_numbers(out, org_allowed)
                    invalid_skipped_holder["n"] += before - len(out)
                return out

            rows, source_errors, _fetched = await fetch_mapped_rows_from_sources(
                tenant_id,
                sources,
                since=since,
                active_only=req.active_only,
                transform_raw_rows=_filter_raw,
            )
            invalid_skipped = invalid_skipped_holder["n"]
            result = await self._upsert_suppliers(tenant_id, current_user, rows, match_key)
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            if invalid_skipped:
                result.skipped = int(getattr(result, "skipped", 0) or 0) + invalid_skipped
                await emit_sync_progress(
                    f"已排除无效供应商 {invalid_skipped} 条，剩余 {len(rows)} 条…"
                )
            if binding:
                if result.failed and not (result.created or result.updated):
                    await mark_binding_failure(binding, "; ".join(result.errors) or "供应商同步失败")
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise
    async def _upsert_suppliers(
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
        custom_fields_by_code = await load_custom_fields_by_code(
            tenant_id, SUPPLIER_CUSTOM_FIELD_TABLE
        )

        PendingRow = Tuple[str, str, Dict[str, Any]]
        pending_rows: List[PendingRow] = []
        for row in rows:
            code = cell_str(
                row.get(match_key if match_key == "code" else "code") or row.get(match_key)
            )
            name = cell_str(row.get("name"))
            if not code:
                skipped += 1
                errors.append("存在缺少供应商编码的行，已跳过")
                continue
            if not name:
                skipped += 1
                errors.append(f"供应商 {code} 缺少名称，已跳过")
                continue
            pending_rows.append((code.upper(), name, row))

        if not pending_rows:
            return MasterDataSyncFromSourceOut(
                created=created,
                updated=updated,
                skipped=skipped,
                failed=failed,
                errors=errors[:20],
            )

        total = len(pending_rows)
        await emit_sync_progress(f"正在预加载本地供应商，准备写入 {total} 条…")

        from apps.master_data.services.supplier_governance import (
            QUALIFICATION_APPROVED,
            QUALIFICATION_POTENTIAL,
            is_supplier_qualification_required,
        )

        qualification_required = await is_supplier_qualification_required(tenant_id)
        create_qualification_status = (
            QUALIFICATION_POTENTIAL if qualification_required else QUALIFICATION_APPROVED
        )

        codes = [item[0] for item in pending_rows]
        existing_by_code: Dict[str, Supplier] = {}
        lookup_chunk = 2000
        for offset in range(0, len(codes), lookup_chunk):
            chunk_codes = codes[offset : offset + lookup_chunk]
            existing_rows = await Supplier.filter(
                tenant_id=tenant_id,
                code__in=chunk_codes,
                deleted_at__isnull=True,
            ).all()
            for item in existing_rows:
                existing_by_code[item.code.upper()] = item

        to_update: List[Supplier] = []
        to_create: List[Supplier] = []
        custom_payload_by_code: Dict[str, Dict[str, Any]] = {}

        for index, (code_key, name, mapped_row) in enumerate(pending_rows, start=1):
            if index == 1 or index == total or index % 500 == 0:
                await emit_sync_progress(f"正在解析供应商 {index}/{total}：{code_key}")
            try:
                custom_payload_by_code[code_key] = mapped_row
                existing = existing_by_code.get(code_key)
                if existing:
                    proposed = _supplier_sync_proposed_core(name, mapped_row)
                    has_custom = _supplier_sync_has_custom_mapping(mapped_row)
                    has_payment = any(
                        key in mapped_row for key in SUPPLIER_PAYMENT_ACCOUNT_SYNC_FIELDS
                    )
                    if (
                        not has_custom
                        and not has_payment
                        and record_fields_unchanged(existing, proposed)
                    ):
                        skipped += 1
                        continue
                    existing.name = proposed["name"]
                    existing.short_name = proposed.get("short_name")
                    existing.external_sync_at = sync_at
                    existing.updated_at = sync_at
                    _apply_supplier_mapped_fields(existing, mapped_row)
                    if current_user is not None:
                        apply_update_audit(existing, current_user)
                    to_update.append(existing)
                else:
                    payload: Dict[str, Any] = {
                        "tenant_id": tenant_id,
                        "code": code_key,
                        "name": _normalize_partner_name(name),
                        "short_name": cell_str(mapped_row.get("short_name")) or None,
                        "is_active": True,
                        "qualification_status": create_qualification_status,
                        "qualifications": [],
                        "external_sync_at": sync_at,
                    }
                    if current_user is not None:
                        apply_create_audit(payload, current_user)
                    supplier = Supplier(**payload)
                    _apply_supplier_mapped_fields(supplier, mapped_row)
                    to_create.append(supplier)
            except Exception as exc:
                failed += 1
                errors.append(f"供应商 {code_key}：{exc}")

        write_batch = 500

        async def _write_custom_fields_for_suppliers(suppliers: List[Supplier]) -> None:
            if not custom_fields_by_code or not suppliers:
                return
            for supplier in suppliers:
                mapped = custom_payload_by_code.get(supplier.code.upper())
                if not mapped:
                    continue
                try:
                    await apply_mapped_custom_field_values(
                        tenant_id=tenant_id,
                        record_table=SUPPLIER_CUSTOM_FIELD_TABLE,
                        record_id=int(supplier.id),
                        mapped_row=mapped,
                        fields_by_code=custom_fields_by_code,
                    )
                except Exception as cf_exc:
                    errors.append(f"供应商 {supplier.code} 自定义字段：{cf_exc}")

        async def _flush_updates(batch: List[Supplier], start_index: int) -> None:
            nonlocal updated, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量更新供应商 {start_index}-{end_index}/{len(to_update)}…"
            )
            try:
                await Supplier.bulk_update(
                    batch, fields=SUPPLIER_BULK_UPDATE_FIELDS, batch_size=write_batch
                )
                updated += len(batch)
                await _write_custom_fields_for_suppliers(batch)
            except Exception:
                for supplier in batch:
                    try:
                        await supplier.save(update_fields=SUPPLIER_BULK_UPDATE_FIELDS)
                        updated += 1
                        await _write_custom_fields_for_suppliers([supplier])
                    except Exception as row_exc:
                        failed += 1
                        errors.append(f"供应商 {supplier.code}：{row_exc}")

        async def _flush_creates(batch: List[Supplier], start_index: int) -> None:
            nonlocal created, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量新建供应商 {start_index}-{end_index}/{len(to_create)}…"
            )
            try:
                await Supplier.bulk_create(batch, batch_size=write_batch)
                created += len(batch)
                codes_created = [item.code for item in batch]
                persisted = await Supplier.filter(
                    tenant_id=tenant_id,
                    code__in=codes_created,
                    deleted_at__isnull=True,
                ).all()
                await _write_custom_fields_for_suppliers(persisted)
            except Exception:
                for supplier in batch:
                    try:
                        await supplier.save()
                        created += 1
                        await _write_custom_fields_for_suppliers([supplier])
                    except Exception as row_exc:
                        failed += 1
                        errors.append(f"供应商 {supplier.code}：{row_exc}")

        for offset in range(0, len(to_update), write_batch):
            await _flush_updates(to_update[offset : offset + write_batch], offset + 1)
        for offset in range(0, len(to_create), write_batch):
            await _flush_creates(to_create[offset : offset + write_batch], offset + 1)

        await emit_sync_progress(
            f"供应商写入完成：新建 {created}，更新 {updated}，跳过 {skipped}，失败 {failed}"
        )
        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
