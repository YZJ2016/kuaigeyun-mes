"""客户从数据接口/数据集同步。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from infra.exceptions.exceptions import ValidationError
from infra.models.user import User

from apps.master_data.models.customer import Customer
from apps.master_data.models.master_data_sync_binding import CustomerSyncBinding
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.master_data.schemas.supply_chain_schemas import CustomerCreate, CustomerUpdate
from apps.master_data.services.master_data_sync_common import (
    apply_sync_extras_after_write,
    attach_sync_fetch_meta,
    cell_str,
    collect_mapped_scalar_proposed,
    fetch_sync_rows,
    filter_kingdee_approved_active_master_rows,
    is_force_rewrite_sync_mode,
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
    sync_record_needs_update,
    upsert_sync_binding,
    resolve_schedule_window_for_sync_request,
    resolve_upsert_schedule_from_body,
)
from core.services.data.sync_binding_sources import fetch_mapped_rows_from_sources
from apps.master_data.services.supply_chain_service import SupplyChainService
from core.services.data.sync_progress import emit_sync_progress

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
        "settlement_method_code",
        "finance_contact_name",
        "finance_contact_phone",
        "finance_contact_email",
        "delivery_contact_name",
        "delivery_contact_phone",
        "delivery_address",
        "salesman_name",
    }
)
CUSTOMER_SYNC_BOOL_FIELDS = frozenset({"is_active"})
CUSTOMER_SYNC_DECIMAL_FIELDS = frozenset({"estimated_annual_purchase", "credit_limit"})
CUSTOMER_SYNC_INT_FIELDS = frozenset({"payment_terms_days"})


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
        total = len(rows)
        custom_fields_by_code = await load_custom_fields_by_code(
            tenant_id, CUSTOMER_CUSTOM_FIELD_TABLE
        )

        for index, row in enumerate(rows, start=1):
            code = cell_str(row.get(match_key if match_key == "code" else "code") or row.get(match_key))
            name = cell_str(row.get("name"))
            if not code:
                skipped += 1
                errors.append("存在缺少客户编码的行，已跳过")
                continue
            if not name:
                skipped += 1
                errors.append(f"客户 {code} 缺少名称，已跳过")
                continue
            if index == 1 or index == total or index % 25 == 0:
                await emit_sync_progress(f"正在写入客户 {index}/{total}：{code}")
            try:
                existing = await Customer.filter(
                    tenant_id=tenant_id,
                    code=code.upper(),
                    deleted_at__isnull=True,
                ).first()
                if existing:
                    # 仅映射字段更新契约：proposed 只收录映射行出现的字段；
                    # 无变更且未映射自定义字段时整行跳过
                    proposed = collect_mapped_scalar_proposed(
                        row,
                        string_fields=CUSTOMER_SYNC_STRING_FIELDS,
                        bool_fields=CUSTOMER_SYNC_BOOL_FIELDS,
                        decimal_fields=CUSTOMER_SYNC_DECIMAL_FIELDS,
                        int_fields=CUSTOMER_SYNC_INT_FIELDS,
                        always={"name": name},
                    )
                    has_custom_mapping = bool(custom_fields_by_code) and any(
                        str(key).startswith("custom:") for key in row.keys()
                    )
                    if not has_custom_mapping and not sync_record_needs_update(
                        existing, proposed, force=force_rewrite
                    ):
                        skipped += 1
                        continue
                    update_payload: Dict[str, Any] = {"name": name}
                    short_name = cell_str(row.get("short_name"))
                    contact_person = cell_str(row.get("contact_person"))
                    phone = cell_str(row.get("phone"))
                    email = cell_str(row.get("email"))
                    address = cell_str(row.get("address"))
                    if short_name:
                        update_payload["short_name"] = short_name
                    if contact_person:
                        update_payload["contact_person"] = contact_person
                    if phone:
                        update_payload["phone"] = phone
                    if email:
                        update_payload["email"] = email
                    if address:
                        update_payload["address"] = address
                    update_data = CustomerUpdate(**update_payload)
                    await SupplyChainService.update_customer(
                        tenant_id,
                        existing.uuid,
                        update_data,
                        current_user,
                        require_contact_channel=False,
                    )
                    await existing.refresh_from_db()
                    await apply_sync_extras_after_write(
                        tenant_id=tenant_id,
                        record=existing,
                        mapped_row=row,
                        record_table=CUSTOMER_CUSTOM_FIELD_TABLE,
                        fields_by_code=custom_fields_by_code,
                        string_fields=CUSTOMER_SYNC_STRING_FIELDS,
                        bool_fields=CUSTOMER_SYNC_BOOL_FIELDS,
                        decimal_fields=CUSTOMER_SYNC_DECIMAL_FIELDS,
                        int_fields=CUSTOMER_SYNC_INT_FIELDS,
                    )
                    await mark_external_sync_record(existing)
                    updated += 1
                else:
                    create_data = CustomerCreate(
                        code=code,
                        name=name,
                        short_name=cell_str(row.get("short_name")) or None,
                        contact_person=cell_str(row.get("contact_person")) or None,
                        phone=cell_str(row.get("phone")) or None,
                        email=cell_str(row.get("email")) or None,
                        address=cell_str(row.get("address")) or None,
                    )
                    created_customer = await SupplyChainService.create_customer(
                        tenant_id,
                        create_data,
                        current_user,
                        require_contact_channel=False,
                    )
                    customer_row = await Customer.filter(
                        tenant_id=tenant_id,
                        uuid=created_customer.uuid,
                        deleted_at__isnull=True,
                    ).first()
                    if customer_row:
                        await apply_sync_extras_after_write(
                            tenant_id=tenant_id,
                            record=customer_row,
                            mapped_row=row,
                            record_table=CUSTOMER_CUSTOM_FIELD_TABLE,
                            fields_by_code=custom_fields_by_code,
                            string_fields=CUSTOMER_SYNC_STRING_FIELDS,
                            bool_fields=CUSTOMER_SYNC_BOOL_FIELDS,
                            decimal_fields=CUSTOMER_SYNC_DECIMAL_FIELDS,
                            int_fields=CUSTOMER_SYNC_INT_FIELDS,
                        )
                        await mark_external_sync_record(customer_row)
                    created += 1
            except Exception as exc:
                failed += 1
                errors.append(f"客户 {code}：{exc}")

        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
