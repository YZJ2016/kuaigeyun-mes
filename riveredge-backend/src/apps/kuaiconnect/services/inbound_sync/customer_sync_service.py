"""客户从数据接口/数据集同步。"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from infra.models.user import User

from apps.master_data.models.customer import Customer
from apps.master_data.models.master_data_sync_binding import CustomerSyncBinding
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
    cell_str,
    collect_mapped_scalar_proposed,
    expand_legacy_partner_settlement_mapped_row,
    filter_kingdee_approved_active_master_rows,
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
    resolve_schedule_window_for_sync_request,
    resolve_upsert_schedule_from_body,
    resolve_schedule_window_for_sync_request,
)
from apps.kuaiconnect.services.inbound_sync.sync_binding_sources import fetch_mapped_rows_from_sources
from core.services.data.sync_progress import emit_sync_progress
from core.utils.timezone_utils import resolve_business_datetime

CUSTOMER_CUSTOM_FIELD_TABLE = "master_data_customers"
CUSTOMER_SYNC_STRING_FIELDS = frozenset(
    {
        "short_name",
        "contact_person",
        "phone",
        "email",
        "address",
        "category",
        "contact_title",
        "industry_code",
        "customer_level_code",
        "lead_source_code",
        "tax_registration_no",
        "invoice_title",
        "invoice_address",
        "invoice_phone",
        "invoice_bank_name",
        "invoice_bank_account",
        "invoice_type_code",
        "taxpayer_type_code",
        "legal_representative",
        "enterprise_type_code",
        "default_payment_method_code",
        "settlement_terms_code",
        "finance_contact_name",
        "finance_contact_phone",
        "finance_contact_email",
        "delivery_contact_name",
        "delivery_contact_phone",
        "delivery_address",
        "salesman_name",
        "partner_type",
        "biz_function",
    }
)
CUSTOMER_SYNC_BOOL_FIELDS = frozenset({"is_active"})
CUSTOMER_SYNC_DECIMAL_FIELDS = frozenset({"estimated_annual_purchase", "credit_limit"})
CUSTOMER_SYNC_INT_FIELDS = frozenset({"payment_terms_days"})
_LOOKUP_CHUNK = 2000
_WRITE_BATCH = 500
_UPDATE_CONCURRENCY = 50


class CustomerSyncService:
    MATCH_KEY = "code"

    def serialize_binding(self, row: Optional[CustomerSyncBinding]) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await CustomerSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut()

        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval, w_start, w_end = await resolve_upsert_schedule_from_body(
            CustomerSyncBinding, tenant_id, body
        )
        row = await upsert_sync_binding(
            CustomerSyncBinding,
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
        row = await CustomerSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: User,
        request: Optional[MasterDataSyncFromSourceRequest] = None,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            CustomerSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )

        binding = binding or await CustomerSyncBinding.filter(tenant_id=tenant_id).first()
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
            binding = await CustomerSyncBinding.filter(tenant_id=tenant_id).first()

        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )
        try:
            await emit_sync_progress("开始同步客户…")
            invalid_skipped_holder = {"n": 0}
            management_org: Optional[str] = None
            use_getcustomer_org_rows = False

            # 对齐供应商 getsupplier：自定义 getcustomer 按连接器组织过滤返回行
            from core.models.api import API
            from core.services.integration.kingdee_cosmic_customer_org_scope import (
                is_cosmic_customer_getcustomer_api,
                resolve_connector_org_for_customer_scope,
            )

            for src in sources:
                api_uuid = str(src.get("api_uuid") or "").strip() or None
                if not api_uuid:
                    continue
                api_obj = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
                if not api_obj:
                    continue
                path_lower = str(getattr(api_obj, "path", "") or "").lower().replace("\\", "/")
                api_code = str(getattr(api_obj, "code", "") or "").strip()
                if not is_cosmic_customer_getcustomer_api(path=path_lower, code=api_code):
                    continue
                await api_obj.fetch_related("integration_config")
                conn = getattr(api_obj, "integration_config", None)
                conn_type = str(getattr(conn, "type", "") or "").strip()
                if conn and conn_type in (
                    "kingdee_cosmic",
                    "kingdee_xinghan",
                    "kingdee_ai_suite",
                ):
                    org = resolve_connector_org_for_customer_scope(conn.get_config())
                    if org and org.upper() != "BU-00000":
                        use_getcustomer_org_rows = True
                        management_org = org
                        await emit_sync_progress(
                            f"按使用组织 {org} 过滤自定义 getcustomer 返回行…"
                        )
                break

            def _filter_raw(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                from core.services.integration.kingdee_cosmic_material_active import (
                    is_cosmic_material_row_active,
                )

                out = raw_rows
                if req.active_only:
                    kept, skipped = filter_kingdee_approved_active_master_rows(out)
                    invalid_skipped_holder["n"] += skipped
                    out = kept
                if use_getcustomer_org_rows and management_org:
                    from core.services.integration.kingdee_cosmic_customer_org_scope import (
                        filter_cosmic_customer_rows_by_management_org_number,
                    )

                    before = len(out)
                    out = filter_cosmic_customer_rows_by_management_org_number(
                        out, management_org
                    )
                    invalid_skipped_holder["n"] += before - len(out)
                stamped: List[Dict[str, Any]] = []
                for row in out:
                    if not isinstance(row, dict):
                        continue
                    item = dict(row)
                    item["sync_is_active"] = is_cosmic_material_row_active(item)
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
            if invalid_skipped:
                await emit_sync_progress(
                    f"已排除无效客户 {invalid_skipped} 条（未审核或已禁用），"
                    f"剩余 {len(rows)} 条…"
                )
                fetched += invalid_skipped
            await emit_sync_progress(f"字段映射完成，准备写入 {len(rows)} 条客户…")
            result = await self._upsert_customers(
                tenant_id,
                current_user,
                rows,
                match_key,
                force_rewrite=is_force_rewrite_sync_mode(sync_mode),
            )
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            attach_sync_fetch_meta(result, fetched=fetched, since=since)
            if invalid_skipped:
                result.skipped = int(getattr(result, "skipped", 0) or 0) + invalid_skipped
            # 全量：按组织过滤后清掉历史多拉，与金蝶使用组织口径完全一致
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
                        deactivated = await Customer.filter(
                            tenant_id=tenant_id,
                            deleted_at__isnull=True,
                            is_active=True,
                            external_sync_at__isnull=False,
                        ).exclude(code__in=list(synced_codes)).update(is_active=False)
                        if deactivated:
                            await emit_sync_progress(
                                f"已将 {deactivated} 条不在本次同步范围内的历史同步客户标为停用"
                            )
                    else:
                        pruned = await Customer.filter(
                            tenant_id=tenant_id,
                            deleted_at__isnull=True,
                            external_sync_at__isnull=False,
                        ).exclude(code__in=list(synced_codes)).update(
                            deleted_at=resolve_business_datetime(),
                            is_active=False,
                        )
                        if pruned:
                            await emit_sync_progress(
                                f"已将 {pruned} 条不在本次同步范围内的历史同步客户软删除"
                            )
            if binding:
                if result.failed and not (result.created or result.updated):
                    await mark_binding_failure(binding, "; ".join(result.errors) or "客户同步失败")
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    @staticmethod
    def _row_code(row: Dict[str, Any], match_key: str) -> str:
        return cell_str(
            row.get(match_key if match_key == "code" else "code") or row.get(match_key)
        )

    @staticmethod
    def _has_custom_mapping(mapped_row: Dict[str, Any]) -> bool:
        return any(str(key).startswith("custom:") for key in mapped_row.keys())

    @staticmethod
    def _customer_sync_proposed(name: str, mapped_row: Dict[str, Any]) -> Dict[str, Any]:
        """只收录映射行出现的可写字段 + name。"""
        return collect_mapped_scalar_proposed(
            mapped_row,
            string_fields=CUSTOMER_SYNC_STRING_FIELDS,
            bool_fields=CUSTOMER_SYNC_BOOL_FIELDS,
            decimal_fields=CUSTOMER_SYNC_DECIMAL_FIELDS,
            int_fields=CUSTOMER_SYNC_INT_FIELDS,
            always={"name": name},
        )

    async def _upsert_customers(
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
            tenant_id, CUSTOMER_CUSTOM_FIELD_TABLE
        )

        pending_by_code: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            code = self._row_code(row, match_key)
            name = cell_str(row.get("name")).strip()
            if not code:
                skipped += 1
                errors.append("存在缺少客户编码的行，已跳过")
                continue
            if not name:
                skipped += 1
                errors.append(f"客户 {code} 缺少名称，已跳过")
                continue
            # 同批重复编码：后者覆盖前者
            pending_by_code[code.upper()] = {
                **expand_legacy_partner_settlement_mapped_row(row),
                "code": code.upper(),
                "name": name,
            }

        pending_rows = list(pending_by_code.values())
        total = len(pending_rows)
        if not pending_rows:
            return MasterDataSyncFromSourceOut(
                created=created,
                updated=updated,
                skipped=skipped,
                failed=failed,
                errors=errors[:20],
            )

        await emit_sync_progress(f"正在预加载已有客户（待处理 {total}）…")
        existing_by_code: Dict[str, Customer] = {}
        codes = [row["code"] for row in pending_rows]
        for offset in range(0, len(codes), _LOOKUP_CHUNK):
            chunk = codes[offset : offset + _LOOKUP_CHUNK]
            existing_rows = await Customer.filter(
                tenant_id=tenant_id,
                code__in=chunk,
                deleted_at__isnull=True,
            ).all()
            for item in existing_rows:
                existing_by_code[str(item.code).upper()] = item

        to_update: List[Tuple[Customer, List[str], Dict[str, Any]]] = []
        to_create: List[Tuple[Customer, Dict[str, Any]]] = []
        custom_payload_by_code: Dict[str, Dict[str, Any]] = {}

        await emit_sync_progress(f"正在解析客户 1/{total}…")
        for index, mapped_row in enumerate(pending_rows, start=1):
            code = mapped_row["code"]
            name = mapped_row["name"]
            if index == 1 or index == total or index % 500 == 0:
                await emit_sync_progress(f"正在解析客户 {index}/{total}：{code}")
            try:
                custom_payload_by_code[code] = mapped_row
                existing = existing_by_code.get(code)
                proposed = self._customer_sync_proposed(name, mapped_row)
                if existing:
                    has_custom = bool(custom_fields_by_code) and self._has_custom_mapping(
                        mapped_row
                    )
                    if not has_custom and not sync_record_needs_update(
                        existing, proposed, force=force_rewrite
                    ):
                        skipped += 1
                        continue

                    update_fields = ["external_sync_at", "updated_at"]
                    touched = apply_proposed_fields_to_record(existing, proposed)
                    for field_name in touched:
                        if field_name not in update_fields:
                            update_fields.append(field_name)
                    existing.external_sync_at = sync_at
                    apply_update_audit(existing, current_user)
                    for audit_field in ("updated_by", "updated_by_name"):
                        if audit_field not in update_fields and hasattr(existing, audit_field):
                            update_fields.append(audit_field)
                    to_update.append((existing, update_fields, mapped_row))
                else:
                    active_flag = cell_optional_bool(mapped_row.get("is_active"))
                    payload: Dict[str, Any] = {
                        "tenant_id": tenant_id,
                        "code": code,
                        "name": name,
                        "short_name": cell_str(mapped_row.get("short_name")) or None,
                        "contact_person": cell_str(mapped_row.get("contact_person")) or None,
                        "phone": cell_str(mapped_row.get("phone")) or None,
                        "email": cell_str(mapped_row.get("email")) or None,
                        "address": cell_str(mapped_row.get("address")) or None,
                        "is_active": True if active_flag is None else bool(active_flag),
                        "pool_status": "pool",
                        "salesman_id": None,
                        "salesman_name": None,
                        "assigned_at": None,
                        "recycle_at": None,
                        "follow_status": "pending",
                        "market_scope": "domestic",
                        "external_sync_at": sync_at,
                    }
                    apply_create_audit(payload, current_user)
                    customer = Customer(**payload)
                    apply_mapped_scalar_fields(
                        customer,
                        mapped_row,
                        string_fields=CUSTOMER_SYNC_STRING_FIELDS,
                        bool_fields=CUSTOMER_SYNC_BOOL_FIELDS,
                        decimal_fields=CUSTOMER_SYNC_DECIMAL_FIELDS,
                        int_fields=CUSTOMER_SYNC_INT_FIELDS,
                    )
                    to_create.append((customer, mapped_row))
            except Exception as exc:
                failed += 1
                errors.append(f"客户 {code}：{exc}")

        async def _write_custom_fields(customers: List[Customer]) -> None:
            if not custom_fields_by_code or not customers:
                return
            for customer in customers:
                mapped = custom_payload_by_code.get(str(customer.code).upper())
                if not mapped or not self._has_custom_mapping(mapped):
                    continue
                try:
                    await apply_mapped_custom_field_values(
                        tenant_id=tenant_id,
                        record_table=CUSTOMER_CUSTOM_FIELD_TABLE,
                        record_id=int(customer.id),
                        mapped_row=mapped,
                        fields_by_code=custom_fields_by_code,
                    )
                except Exception as cf_exc:
                    errors.append(f"客户 {customer.code} 自定义字段：{cf_exc}")

        async def _flush_updates(
            batch: List[Tuple[Customer, List[str], Dict[str, Any]]],
            start_index: int,
        ) -> None:
            nonlocal updated, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量更新客户 {start_index}-{end_index}/{len(to_update)}…"
            )
            sem = asyncio.Semaphore(_UPDATE_CONCURRENCY)

            async def _save_one(
                customer: Customer, update_fields: List[str]
            ) -> Optional[str]:
                async with sem:
                    try:
                        # Customer.save 按 tenant_id+id 更新，避免多租户 id 复用误改
                        await customer.save(update_fields=update_fields)
                        return None
                    except Exception as row_exc:
                        return f"客户 {customer.code}：{row_exc}"

            results = await asyncio.gather(
                *[_save_one(customer, fields) for customer, fields, _ in batch]
            )
            ok_customers: List[Customer] = []
            for (customer, _, _), err in zip(batch, results):
                if err:
                    failed += 1
                    errors.append(err)
                else:
                    updated += 1
                    ok_customers.append(customer)
            await _write_custom_fields(ok_customers)

        async def _flush_creates(
            batch: List[Tuple[Customer, Dict[str, Any]]],
            start_index: int,
        ) -> None:
            nonlocal created, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量新建客户 {start_index}-{end_index}/{len(to_create)}…"
            )
            customers = [item[0] for item in batch]
            try:
                await Customer.bulk_create(customers, batch_size=_WRITE_BATCH)
                created += len(customers)
                codes_created = [str(item.code).upper() for item in customers]
                persisted = await Customer.filter(
                    tenant_id=tenant_id,
                    code__in=codes_created,
                    deleted_at__isnull=True,
                ).all()
                await _write_custom_fields(persisted)
            except Exception:
                for customer, _mapped in batch:
                    try:
                        await customer.save()
                        created += 1
                        await _write_custom_fields([customer])
                    except Exception as row_exc:
                        failed += 1
                        errors.append(f"客户 {customer.code}：{row_exc}")

        for offset in range(0, len(to_update), _WRITE_BATCH):
            await _flush_updates(to_update[offset : offset + _WRITE_BATCH], offset + 1)
        for offset in range(0, len(to_create), _WRITE_BATCH):
            await _flush_creates(to_create[offset : offset + _WRITE_BATCH], offset + 1)

        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
