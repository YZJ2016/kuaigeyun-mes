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
from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import (
    apply_mapped_custom_field_values,
    apply_mapped_scalar_fields,
    apply_proposed_fields_to_record,
    attach_sync_fetch_meta,
    cell_optional_bool,
    cell_optional_decimal,
    cell_optional_int,
    cell_str,
    collect_mapped_scalar_proposed,
    expand_legacy_partner_settlement_mapped_row,
    fetch_sync_rows,
    filter_kingdee_approved_active_master_rows,
    is_force_rewrite_sync_mode,
    load_custom_fields_by_code,
    map_sync_rows,
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
from apps.master_data.services.supply_chain_service import _normalize_partner_name
from core.services.data.sync_progress import emit_sync_progress
from core.utils.timezone_utils import resolve_business_datetime

SUPPLIER_CUSTOM_FIELD_TABLE = "master_data_suppliers"
SUPPLIER_SYNC_STRING_FIELDS = frozenset({
    "short_name", "contact_person", "phone", "email", "address", "category", "contact_title",
    "industry_code", "source_channel_code", "tax_registration_no", "invoice_title",
    "invoice_address", "invoice_phone", "invoice_bank_name", "invoice_bank_account",
    "invoice_type_code", "taxpayer_type_code", "legal_representative",
    "enterprise_type_code", "default_payment_method_code", "settlement_terms_code", "buyer_name",
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
    """只收录映射行出现的可写字段 + name；未映射字段不进 proposed（禁止误清空）。"""
    return collect_mapped_scalar_proposed(
        mapped_row,
        string_fields=SUPPLIER_SYNC_STRING_FIELDS,
        bool_fields=SUPPLIER_SYNC_BOOL_FIELDS,
        decimal_fields=SUPPLIER_SYNC_DECIMAL_FIELDS,
        int_fields=SUPPLIER_SYNC_INT_FIELDS,
        always={"name": _normalize_partner_name(name)},
    )


def _apply_supplier_mapped_fields(record: Supplier, mapped_row: Dict[str, Any]) -> List[str]:
    mapped_row = expand_legacy_partner_settlement_mapped_row(mapped_row)
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
        interval, w_start, w_end = await resolve_upsert_schedule_from_body(
            SupplierSyncBinding, tenant_id, body
        )
        row = await upsert_sync_binding(
            SupplierSyncBinding,
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
            from core.services.integration.kingdee_cosmic_supplier_org_scope import (
                fetch_cosmic_supplier_org_allowed_numbers,
                filter_cosmic_supplier_rows_active,
                is_cosmic_supplier_getsupplier_api,
                is_cosmic_supplier_row_active,
                resolve_connector_org_for_supplier_scope,
            )
            from core.services.integration.kingdee_galaxy_material_active import (
                filter_galaxy_material_rows_active,
                is_galaxy_execute_bill_query_path,
                is_galaxy_material_row_active,
            )

            for src in sources:
                api_uuid = str(src.get("api_uuid") or "").strip() or None
                if not api_uuid:
                    continue
                api_obj = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
                if not api_obj:
                    continue
                path_lower = str(getattr(api_obj, "path", "") or "").lower().replace("\\", "/")
                last_source_api_path = path_lower
                api_code = str(getattr(api_obj, "code", "") or "").strip()
                is_getsupplier = is_cosmic_supplier_getsupplier_api(
                    path=path_lower,
                    code=api_code,
                )
                # 标品 query；勿用裸子串误伤 pbdfl
                is_query = (
                    path_lower.rstrip("/").endswith("/bd_supplier/query")
                    or "/bd_supplier/query?" in path_lower
                ) and not is_getsupplier
                if not is_query and not is_getsupplier:
                    # pbdfl / 其它扩展接口：不做 suppliercommon 组织交集，但仍记录 path 供有效过滤
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

            # pbdfl 等扩展源：上面 loop 可能 continue 掉，补抓 path
            if not last_source_api_path:
                for src in sources:
                    api_uuid = str(src.get("api_uuid") or "").strip() or None
                    if not api_uuid:
                        continue
                    api_obj = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
                    if api_obj:
                        last_source_api_path = str(
                            getattr(api_obj, "path", "") or ""
                        ).lower().replace("\\", "/")
                        break

            def _filter_raw(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                path_for_active = last_source_api_path
                is_galaxy = is_galaxy_execute_bill_query_path(path_for_active)

                out = raw_rows
                if req.active_only:
                    if is_galaxy:
                        before = len(out)
                        out = filter_galaxy_material_rows_active(out)
                        invalid_skipped_holder["n"] += before - len(out)
                    else:
                        # 星空列（FDocumentStatus）无则原样放行；苍穹再按 path 分支
                        # pbdfl 无 status：filter_cosmic_supplier_rows_active 仅看 enable
                        kept, skipped = filter_kingdee_approved_active_master_rows(out)
                        invalid_skipped_holder["n"] += skipped
                        out = kept
                        before = len(out)
                        out = filter_cosmic_supplier_rows_active(
                            out, path=path_for_active
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
                # 写入 is_active：含不启用时停用行也要落库，不能一律 True
                stamped: List[Dict[str, Any]] = []
                for row in out:
                    if not isinstance(row, dict):
                        continue
                    item = dict(row)
                    if is_galaxy:
                        item["sync_is_active"] = is_galaxy_material_row_active(item)
                    else:
                        item["sync_is_active"] = is_cosmic_supplier_row_active(
                            item, path=path_for_active
                        )
                    stamped.append(item)
                return stamped

            sources_for_fetch: List[Dict[str, Any]] = []
            for src in sources:
                src_for_fetch = dict(src)
                mapping = dict(src_for_fetch.get("field_mapping") or {})
                mapping["sync_is_active"] = "is_active"
                src_for_fetch["field_mapping"] = mapping
                sources_for_fetch.append(src_for_fetch)

            rows, source_errors, fetched = await fetch_mapped_rows_from_sources(
                tenant_id,
                sources_for_fetch,
                since=since,
                active_only=req.active_only,
                transform_raw_rows=_filter_raw,
            )
            invalid_skipped = invalid_skipped_holder["n"]
            raw_fetched = int(fetched or 0) + int(invalid_skipped or 0)
            if invalid_skipped:
                await emit_sync_progress(
                    f"已排除无效供应商 {invalid_skipped} 条，剩余 {len(rows)} 条…"
                )
            await emit_sync_progress(f"字段映射完成，准备写入 {len(rows)} 条供应商…")
            result = await self._upsert_suppliers(
                tenant_id,
                current_user,
                rows,
                match_key,
                force_rewrite=is_force_rewrite_sync_mode(sync_mode),
            )
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            attach_sync_fetch_meta(result, fetched=raw_fetched, since=since)
            result.after_filter = len(rows)
            if invalid_skipped:
                result.skipped = int(getattr(result, "skipped", 0) or 0) + invalid_skipped
            if (
                since is None
                and raw_fetched > 0
                and len(rows) == 0
                and not (result.created or result.updated)
            ):
                result.empty_reason = "filtered_all"
                result.errors = (
                    [
                        "源端已拉取供应商行，但经「仅有效」或组织过滤后为 0 条。"
                        "定制 pbdfl 接口无 status 字段时须按 enable 判定；"
                        "请确认已部署最新同步过滤逻辑后重试。"
                    ]
                    + list(result.errors)
                )[:20]
            elif (
                since is None
                and raw_fetched == 0
                and not (result.created or result.updated)
                and not source_errors
            ):
                result.empty_reason = "source_empty"
            # 全量：getsupplier 按组织过滤后，清掉历史多拉的集团/他组织供应商，与金蝶完全一致
            if since is None and not source_errors:
                synced_codes = {
                    cell_str(
                        row.get(match_key if match_key == "code" else "code")
                        or row.get(match_key)
                        or row.get("number")
                    )
                    for row in rows
                    if isinstance(row, dict)
                }
                synced_codes.discard("")
                if synced_codes:
                    if req.active_only:
                        deactivated = await Supplier.filter(
                            tenant_id=tenant_id,
                            deleted_at__isnull=True,
                            is_active=True,
                            external_sync_at__isnull=False,
                        ).exclude(code__in=list(synced_codes)).update(is_active=False)
                        if deactivated:
                            await emit_sync_progress(
                                f"已将 {deactivated} 条不在本次同步范围内的历史同步供应商标为停用"
                            )
                    else:
                        pruned = await Supplier.filter(
                            tenant_id=tenant_id,
                            deleted_at__isnull=True,
                            external_sync_at__isnull=False,
                        ).exclude(code__in=list(synced_codes)).update(
                            deleted_at=resolve_business_datetime(),
                            is_active=False,
                        )
                        if pruned:
                            await emit_sync_progress(
                                f"已将 {pruned} 条不在本次同步范围内的历史同步供应商软删除"
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
                        and not sync_record_needs_update(
                            existing, proposed, force=force_rewrite
                        )
                    ):
                        skipped += 1
                        continue
                    apply_proposed_fields_to_record(existing, proposed)
                    existing.external_sync_at = sync_at
                    existing.updated_at = sync_at
                    # 标量已由 proposed 写入；此处只补结算账户（不在 proposed 标量集合）
                    apply_supplier_payment_account_sync(
                        existing, expand_legacy_partner_settlement_mapped_row(mapped_row)
                    )
                    if current_user is not None:
                        apply_update_audit(existing, current_user)
                    to_update.append(existing)
                else:
                    active_flag = cell_optional_bool(mapped_row.get("is_active"))
                    payload: Dict[str, Any] = {
                        "tenant_id": tenant_id,
                        "code": code_key,
                        "name": _normalize_partner_name(name),
                        "short_name": cell_str(mapped_row.get("short_name")) or None,
                        "is_active": True if active_flag is None else bool(active_flag),
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
