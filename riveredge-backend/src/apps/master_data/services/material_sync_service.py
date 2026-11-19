"""物料从数据接口/数据集同步。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from infra.exceptions.exceptions import ValidationError
from infra.models.user import User

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.master_data.constants.material_source_type import require_canonical_material_source_type
from apps.master_data.models.material import Material
from apps.master_data.models.master_data_sync_binding import MaterialSyncBinding
from apps.master_data.schemas.master_data_sync import (
    MasterDataSyncBindingOut,
    MasterDataSyncBindingUpsert,
    MasterDataSyncFromSourceOut,
    MasterDataSyncFromSourceRequest,
)
from apps.master_data.services.master_data_sync_common import (
    apply_mapped_custom_field_values,
    attach_sync_fetch_meta,
    cell_optional_bool,
    cell_optional_decimal,
    cell_optional_int,
    cell_str,
    fetch_sync_rows,
    load_custom_fields_by_code,
    map_sync_rows,
    mark_binding_failure,
    mark_binding_success,
    is_force_rewrite_sync_mode,
    normalize_schedule_interval,
    normalize_sync_mode,
    resolve_incremental_since,
    sync_record_needs_update,
    resolve_sync_sources,
    serialize_binding_row,
    sources_from_upsert_body,
    upsert_sync_binding,
    resolve_schedule_window_for_sync_request,
    resolve_upsert_schedule_from_body,
)
from core.services.data.sync_binding_sources import fetch_mapped_rows_from_sources
from apps.master_data.services.sync_association_service import (
    ensure_material_groups_from_material_rows,
    load_material_group_id_lookup,
    load_material_unit_lookup,
    resolve_material_base_unit_from_lookup,
    resolve_material_group_id_from_lookup,
    run_material_prerequisite_syncs,
)
from core.services.data.sync_progress import emit_sync_progress
from core.utils.timezone_utils import resolve_business_datetime

MATERIAL_CUSTOM_FIELD_TABLE = "master_data_materials"

# 映射目标中可直接写入 Material 标量列的字段（不含 main_code / name / 解析型辅助字段）
MATERIAL_SYNC_EXTRA_SCALAR_FIELDS = frozenset(
    {
        "description",
        "brand",
        "model",
        "texture",
        "barcode",
        "source_type",
        "is_active",
        "batch_managed",
        "serial_managed",
        "variant_managed",
        "weight",
        "volume",
        "shelf_life_managed",
        "shelf_life_days",
        "is_giftable",
        "reference_cost",
        "country_of_origin",
        "customs_code",
        "over_report_mode",
        "over_report_value",
        "over_receipt_tolerance_pct",
        "over_issue_tolerance_pct",
        "inspection_mode",
    }
)

MATERIAL_SYNC_BOOL_FIELDS = frozenset(
    {
        "is_active",
        "batch_managed",
        "serial_managed",
        "variant_managed",
        "shelf_life_managed",
        "is_giftable",
    }
)

MATERIAL_SYNC_DECIMAL_FIELDS = frozenset(
    {
        "weight",
        "volume",
        "reference_cost",
        "over_report_value",
        "over_receipt_tolerance_pct",
        "over_issue_tolerance_pct",
    }
)
MATERIAL_SYNC_INT_FIELDS = frozenset({"shelf_life_days"})

# 批号/序列号：映射为空或绑错列时仍从金蝶主档开关列回填
MATERIAL_SYNC_MAP_EMPTY_FALLBACKS: Dict[str, List[str]] = {
    "batch_managed": ["enablelot", "enableLot", "FIsBatchManage"],
    "serial_managed": ["enableserial", "enableSerial", "FIsSNManage"],
}


def _merge_material_sync_field_mapping(field_mapping: Dict[str, Any]) -> Dict[str, str]:
    """合并同步映射：启用状态 + 批号/序列号主档列（不被错误 batch_managed 映射挡住）。"""
    mapping = {str(k): str(v) for k, v in (field_mapping or {}).items() if str(k).strip() and str(v).strip()}
    mapping["sync_is_active"] = "is_active"
    if "FIsBatchManage" not in mapping:
        mapping["FIsBatchManage"] = "batch_managed"
    if "FIsSNManage" not in mapping:
        mapping["FIsSNManage"] = "serial_managed"
    # 苍穹 enablelot 优先于星空 FIsBatchManage（同 dict 内后写覆盖）
    if "enablelot" not in mapping:
        mapping["enablelot"] = "batch_managed"
    if "enableserial" not in mapping:
        mapping["enableserial"] = "serial_managed"
    return mapping


def _coerce_material_extra_value(
    field_name: str,
    raw: Any,
    conversion_entries: Optional[List[Dict[str, Any]]] = None,
    source_field_names: Optional[set[str]] = None,
) -> Any:
    if field_name in MATERIAL_SYNC_BOOL_FIELDS:
        return cell_optional_bool(raw)
    if field_name in MATERIAL_SYNC_DECIMAL_FIELDS:
        return cell_optional_decimal(raw)
    if field_name in MATERIAL_SYNC_INT_FIELDS:
        return cell_optional_int(raw)
    if field_name == "source_type":
        text = cell_str(raw)
        if conversion_entries:
            for entry in conversion_entries:
                if not isinstance(entry, dict):
                    continue
                entry_field_name = cell_str(entry.get("field_name"))
                if entry_field_name != field_name and entry_field_name not in (source_field_names or set()):
                    continue
                mapping = entry.get("mapping")
                if isinstance(mapping, dict) and text in mapping:
                    return mapping[text]
        if not text:
            return None
        return require_canonical_material_source_type(text)
    text = cell_str(raw)
    return text or None


def _apply_material_extra_scalars(
    material: Material,
    row: Dict[str, Any],
    update_fields: List[str],
    *,
    conversion_entries: Optional[List[Dict[str, Any]]] = None,
    source_field_names: Optional[set[str]] = None,
) -> None:
    for field_name in MATERIAL_SYNC_EXTRA_SCALAR_FIELDS:
        if field_name not in row:
            continue
        coerced = _coerce_material_extra_value(
            field_name,
            row.get(field_name),
            conversion_entries,
            source_field_names,
        )
        if coerced is None and field_name in MATERIAL_SYNC_BOOL_FIELDS:
            continue
        if coerced is None and field_name in {"weight", "volume", "over_report_value"}:
            # Decimal 列有 default；空映射跳过，避免清零
            continue
        setattr(material, field_name, coerced)
        if field_name not in update_fields:
            update_fields.append(field_name)


class MaterialSyncService:
    MATCH_KEY = "main_code"

    def serialize_binding(self, row: Optional[MaterialSyncBinding]) -> MasterDataSyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return MasterDataSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: MasterDataSyncBindingUpsert,
    ) -> MasterDataSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await MaterialSyncBinding.filter(tenant_id=tenant_id).delete()
            return MasterDataSyncBindingOut(match_key_field=self.MATCH_KEY)

        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval, w_start, w_end = await resolve_upsert_schedule_from_body(
            MaterialSyncBinding, tenant_id, body
        )
        row = await upsert_sync_binding(
            MaterialSyncBinding,
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
        row = await MaterialSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: Optional[User],
        request: Optional[MasterDataSyncFromSourceRequest] = None,
        *,
        skip_prerequisite_syncs: bool = False,
    ) -> MasterDataSyncFromSourceOut:
        req = request or MasterDataSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            MaterialSyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )

        binding = binding or await MaterialSyncBinding.filter(tenant_id=tenant_id).first()
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
            binding = await MaterialSyncBinding.filter(tenant_id=tenant_id).first()

        prerequisite_errors: List[str] = []
        if not skip_prerequisite_syncs and not req.skip_prerequisite_syncs:
            if current_user is None:
                raise ValidationError("关联同步须指定操作用户")
            prerequisite_errors = await run_material_prerequisite_syncs(tenant_id, current_user)

        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )

        try:
            await emit_sync_progress("开始同步物料…")
            from core.models.api import API

            result = MasterDataSyncFromSourceOut()
            fetched_total = 0
            fetch_had_source_errors = False
            last_source_api_path = ""
            inventory_tracking_by_number: Dict[str, Dict[str, Any]] = {}
            for src in sources:
                field_mapping = src.get("field_mapping") or {}
                source_field_names = {
                    str(source).strip()
                    for source, target in field_mapping.items()
                    if str(target).strip() == "source_type"
                }
                conversion_entries = None
                api_uuid = str(src.get("api_uuid") or "").strip() or None
                org_allowed = None
                if api_uuid:
                    api_obj = await API.filter(
                        tenant_id=tenant_id,
                        uuid=api_uuid,
                        deleted_at__isnull=True,
                    ).first()
                    if api_obj is None:
                        raise ValidationError(
                            f"物料同步绑定的接口不存在或已删除（api_uuid={api_uuid}）。"
                            "请在物料管理「来源设置」中重新选择接口。"
                        )
                    conv = getattr(api_obj, "source_type_conversion_map", None) if api_obj else None
                    if isinstance(conv, list):
                        conversion_entries = conv
                    elif isinstance(conv, dict):
                        conversion_entries = [{"field_name": "source_type", "mapping": conv}]
                    if api_obj:
                        last_source_api_path = str(getattr(api_obj, "path", "") or "").lower()
                    path_norm = last_source_api_path.replace("\\", "/")
                    if api_obj and "/bd_material/batchquery" in path_norm:
                        from core.services.integration.kingdee_cosmic_api_presets import (
                            MATERIAL_SYNC_SELECT,
                        )

                        src = {
                            **src,
                            "request_body": {
                                **(src.get("request_body") or {}),
                                "select": MATERIAL_SYNC_SELECT,
                            },
                            "request_params": {
                                **(src.get("request_params") or {}),
                                "select": MATERIAL_SYNC_SELECT,
                            },
                        }
                    elif api_obj and "executebillquery" in path_norm:
                        from core.services.integration.kingdee_galaxy_api_presets import (
                            MATERIAL_QUERY_FIELD_KEYS,
                            _parse_execute_bill_query,
                        )

                        base_body = _parse_execute_bill_query(
                            getattr(api_obj, "request_body", None)
                        ) or {}
                        form_id = str(
                            base_body.get("FormId") or base_body.get("formId") or ""
                        ).strip()
                        if form_id.upper() == "BD_MATERIAL":
                            merged_keys = str(
                                base_body.get("FieldKeys")
                                or base_body.get("fieldKeys")
                                or ""
                            ).strip()
                            for part in MATERIAL_QUERY_FIELD_KEYS.split(","):
                                key = part.strip()
                                if key and key not in merged_keys:
                                    merged_keys = (
                                        f"{merged_keys},{key}" if merged_keys else key
                                    )
                            src = {
                                **src,
                                "request_body": {**base_body, "FieldKeys": merged_keys},
                            }
                    if api_obj and "/bd_material/batchquery" in path_norm:
                        await api_obj.fetch_related("integration_config")
                        conn = getattr(api_obj, "integration_config", None)
                        conn_type = str(getattr(conn, "type", "") or "").strip()
                        if conn and conn_type in (
                            "kingdee_cosmic",
                            "kingdee_xinghan",
                            "kingdee_ai_suite",
                        ):
                            from core.services.integration.kingdee_cosmic_material_org_scope import (
                                fetch_cosmic_material_org_allowed_numbers,
                                resolve_connector_org_for_material_scope,
                            )

                            org = resolve_connector_org_for_material_scope(conn.get_config())
                            if org and org.upper() != "BU-00000":
                                await emit_sync_progress(
                                    f"拉取管理组织 {org} 的物料使用范围（bd_materialcommon）…"
                                )
                                org_allowed = await fetch_cosmic_material_org_allowed_numbers(
                                    tenant_id,
                                    connection_uuid=conn.uuid,
                                    org_number=org,
                                    active_only=req.active_only,
                                )
                                await emit_sync_progress(
                                    f"管理组织物料使用范围 {len(org_allowed)} 个编码"
                                )
                            try:
                                from core.services.integration.kingdee_cosmic_material_inventory_info import (
                                    fetch_cosmic_material_inventory_tracking_by_number,
                                )

                                await emit_sync_progress(
                                    "拉取物料库存信息（批号/序列号开关）…"
                                )
                                inventory_tracking_by_number = (
                                    await fetch_cosmic_material_inventory_tracking_by_number(
                                        tenant_id,
                                        connection_uuid=conn.uuid,
                                        org_number=org or None,
                                        active_only=req.active_only,
                                    )
                                )
                                await emit_sync_progress(
                                    f"库存信息批号/序列号 {len(inventory_tracking_by_number)} 个物料编码"
                                )
                            except ValidationError as inv_exc:
                                fetch_had_source_errors = True
                                result.errors = (
                                    [str(inv_exc)]
                                    + list(getattr(result, "errors", None) or [])
                                )[:20]

                def transform_raw(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                    from core.services.integration.kingdee_cosmic_material_active import (
                        filter_cosmic_material_rows_active,
                        is_cosmic_material_row_active,
                    )
                    from core.services.integration.kingdee_cosmic_material_inventory_info import (
                        apply_inventory_tracking_to_material_rows,
                    )
                    from core.services.integration.kingdee_galaxy_material_active import (
                        filter_galaxy_material_rows_active,
                        is_galaxy_execute_bill_query_path,
                        is_galaxy_material_row_active,
                    )

                    path_for_active = last_source_api_path.replace("\\", "/")
                    is_cosmic_material = "/bd_material/batchquery" in path_for_active
                    is_galaxy_material = is_galaxy_execute_bill_query_path(path_for_active)

                    out = rows
                    # 苍穹看 status/enable；星空看 FDocumentStatus/FForbidStatus。
                    # 禁止对星空行套用苍穹过滤器，否则「仅有效」会把全部行滤成 fetched=0。
                    if req.active_only:
                        if is_cosmic_material:
                            out = filter_cosmic_material_rows_active(out)
                        elif is_galaxy_material:
                            out = filter_galaxy_material_rows_active(out)
                    if org_allowed is not None:
                        from core.services.integration.kingdee_cosmic_material_org_scope import (
                            filter_cosmic_material_rows_by_org_numbers,
                        )

                        out = filter_cosmic_material_rows_by_org_numbers(out, org_allowed)
                    out = apply_inventory_tracking_to_material_rows(
                        out, inventory_tracking_by_number
                    )
                    # 写入 is_active：映射目标列，避免「仅有效」关掉后仍全量标启用
                    stamped: List[Dict[str, Any]] = []
                    for row in out:
                        if not isinstance(row, dict):
                            continue
                        item = dict(row)
                        if is_cosmic_material:
                            item["sync_is_active"] = is_cosmic_material_row_active(item)
                        elif is_galaxy_material:
                            item["sync_is_active"] = is_galaxy_material_row_active(item)
                        else:
                            item["sync_is_active"] = True
                        stamped.append(item)
                    return stamped

                src_for_fetch = dict(src)
                src_for_fetch["field_mapping"] = _merge_material_sync_field_mapping(
                    src_for_fetch.get("field_mapping") or {}
                )

                rows, source_errors, fetched = await fetch_mapped_rows_from_sources(
                    tenant_id,
                    [src_for_fetch],
                    since=since,
                    active_only=req.active_only,
                    transform_raw_rows=transform_raw,
                    empty_fallbacks=MATERIAL_SYNC_MAP_EMPTY_FALLBACKS,
                )
                if source_errors:
                    fetch_had_source_errors = True
                fetched_total += fetched
                one = await self._upsert_materials(
                    tenant_id,
                    current_user,
                    rows,
                    match_key,
                    conversion_entries=conversion_entries,
                    source_field_names=source_field_names,
                    force_rewrite=is_force_rewrite_sync_mode(sync_mode),
                )
                result.created += one.created
                result.updated += one.updated
                result.skipped += one.skipped
                result.failed += one.failed
                result.errors = (result.errors + source_errors + list(one.errors))[:20]
            await emit_sync_progress(f"字段映射完成，共处理 {fetched_total} 行源数据…")
            attach_sync_fetch_meta(result, fetched=fetched_total, since=since)
            if prerequisite_errors:
                result.errors = (prerequisite_errors + list(result.errors))[:20]
            # 已有接口异常时勿再盖空拉诊断文案（否则掩盖 NoneType 等真错）
            if (
                since is None
                and fetched_total == 0
                and not (result.created or result.updated)
                and not fetch_had_source_errors
            ):
                path_norm = last_source_api_path.replace("\\", "/")
                if "/bd_material/batchquery" in path_norm:
                    zero_msg = (
                        "源端未返回任何物料行（fetched=0）。"
                        "云苍穹常见为集团创建物料再分配子公司，物料 batchQuery 的 data 勿写 createorg_number，"
                        "也勿保留空的 id/number 等勾选未填项；"
                        "请检查「苍穹查询物料」接口 request_body，或连接器换票后重试。"
                    )
                elif "executebillquery" in path_norm or path_norm.endswith(".kdsvc"):
                    zero_msg = (
                        "源端未返回任何物料行（fetched=0）。"
                        "当前同步源是金蝶星空 ExecuteBillQuery（金蝶查询物料），不是苍穹 batchQuery；"
                        "请确认星空连接器可访问且账套确有已审核未禁用物料。"
                        "若应从云苍穹同步，请在同步配置中改选「苍穹查询物料」并重新映射 number/name 等字段。"
                    )
                else:
                    zero_msg = (
                        "源端未返回任何物料行（fetched=0）。"
                        "请检查物料同步绑定的接口、连接器与请求体筛选条件。"
                    )
                result.errors = ([zero_msg] + list(result.errors))[:20]
            if binding:
                if result.failed and not (result.created or result.updated):
                    await mark_binding_failure(
                        binding,
                        "; ".join(result.errors) or "物料同步失败",
                    )
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    async def _upsert_materials(
        self,
        tenant_id: int,
        current_user: Optional[User],
        rows: List[Dict[str, Any]],
        match_key: str,
        *,
        conversion_entries: Optional[List[Dict[str, Any]]] = None,
        source_field_names: Optional[set[str]] = None,
        force_rewrite: bool = False,
    ) -> MasterDataSyncFromSourceOut:
        created = 0
        updated = 0
        skipped = 0
        failed = 0
        errors: List[str] = []
        sync_at = resolve_business_datetime()
        custom_fields_by_code = await load_custom_fields_by_code(
            tenant_id, MATERIAL_CUSTOM_FIELD_TABLE
        )

        PendingRow = Tuple[
            str,
            str,
            Optional[str],
            str,
            Optional[str],
            Optional[str],
            Optional[str],
            Dict[str, Any],
        ]
        pending_rows: List[PendingRow] = []
        for row in rows:
            main_code = cell_str(
                row.get(match_key) or row.get("main_code") or row.get("code") or row.get("number")
            )
            name = cell_str(row.get("name"))
            base_unit = cell_str(
                row.get("base_unit")
                or row.get("baseunit_number")
                or row.get("baseunit.number")
                or row.get("measureunitid_number")
            )
            base_unit_name = (
                cell_str(
                    row.get("base_unit_name")
                    or row.get("baseunit_name")
                    or row.get("baseunit.name")
                    or row.get("measureunitid_name")
                )
                or None
            )
            group_code = (
                cell_str(
                    row.get("group_code")
                    or row.get("group_number")
                    or row.get("group.number")
                    or row.get("materialgroup_number")
                    or row.get("materialgroup.number")
                )
                or None
            )
            group_name = (
                cell_str(
                    row.get("group_name")
                    or row.get("group.name")
                    or row.get("materialgroup_name")
                    or row.get("materialgroup.name")
                )
                or None
            )
            if not main_code:
                skipped += 1
                errors.append("存在缺少物料编码的行，已跳过")
                continue
            if not name:
                skipped += 1
                errors.append(f"物料 {main_code} 缺少名称，已跳过")
                continue
            if not base_unit and not base_unit_name:
                failed += 1
                errors.append(f"物料 {main_code} 缺少基本单位 base_unit / base_unit_name")
                continue
            specification = (
                cell_str(
                    row.get("specification")
                    or row.get("modelnum")
                    or row.get("model")
                    or row.get("modelNum")
                )
                or None
            )
            pending_rows.append(
                (
                    main_code,
                    name,
                    specification,
                    base_unit,
                    base_unit_name,
                    group_code,
                    group_name,
                    row,
                )
            )

        if not pending_rows:
            return MasterDataSyncFromSourceOut(
                created=created,
                updated=updated,
                skipped=skipped,
                failed=failed,
                errors=errors[:20],
            )

        total = len(pending_rows)
        await emit_sync_progress(f"正在预加载单位与分组映射，准备写入 {total} 条物料…")
        unit_by_code, unit_by_name = await load_material_unit_lookup(tenant_id)
        group_by_code = await load_material_group_id_lookup(tenant_id)
        group_pairs = [
            (group_code, group_name or "")
            for *_, group_code, group_name, _row in pending_rows
            if group_code
        ]
        if group_pairs:
            await emit_sync_progress("正在根据物料行补齐本地物料分组…")
            group_by_code = await ensure_material_groups_from_material_rows(
                tenant_id,
                current_user,
                group_by_code=group_by_code,
                group_pairs=group_pairs,
            )

        codes = [item[0] for item in pending_rows]
        existing_by_code: Dict[str, Material] = {}
        lookup_chunk = 2000
        for offset in range(0, len(codes), lookup_chunk):
            chunk_codes = codes[offset : offset + lookup_chunk]
            existing_rows = await Material.filter(
                tenant_id=tenant_id,
                main_code__in=chunk_codes,
                deleted_at__isnull=True,
            ).all()
            for item in existing_rows:
                existing_by_code[item.main_code] = item

        to_update: List[Material] = []
        to_create: List[Material] = []
        custom_payload_by_code: Dict[str, Dict[str, Any]] = {}
        update_fields = [
            "name",
            "specification",
            "base_unit",
            "group_id",
            "external_sync_at",
            "updated_at",
            "updated_by",
            "updated_by_name",
        ]

        for index, (
            main_code,
            name,
            specification,
            base_unit,
            base_unit_name,
            group_code,
            group_name,
            mapped_row,
        ) in enumerate(pending_rows, start=1):
            if index == 1 or index == total or index % 500 == 0:
                await emit_sync_progress(f"正在解析物料 {index}/{total}：{main_code}")
            try:
                resolved_unit = resolve_material_base_unit_from_lookup(
                    unit_by_code,
                    unit_by_name,
                    unit_code=base_unit,
                    unit_name=base_unit_name or "",
                )
                group_id = (
                    resolve_material_group_id_from_lookup(group_by_code, group_code)
                    if group_code
                    else None
                )
                custom_payload_by_code[main_code] = mapped_row
                existing = existing_by_code.get(main_code)
                if existing:
                    proposed: Dict[str, Any] = {
                        "name": name,
                        "specification": specification,
                        "base_unit": resolved_unit,
                    }
                    if group_id is not None:
                        proposed["group_id"] = group_id
                    for field_name in MATERIAL_SYNC_EXTRA_SCALAR_FIELDS:
                        if field_name not in mapped_row:
                            continue
                        coerced = _coerce_material_extra_value(
                            field_name,
                            mapped_row.get(field_name),
                            conversion_entries,
                            source_field_names,
                        )
                        if coerced is None and field_name in MATERIAL_SYNC_BOOL_FIELDS:
                            continue
                        if coerced is None and field_name in {
                            "weight",
                            "volume",
                            "over_report_value",
                        }:
                            continue
                        proposed[field_name] = coerced
                    # 自定义字段有映射时无法在此廉价比对，仍走更新；纯系统字段无变更则跳过
                    has_custom_mapping = any(
                        str(key).startswith("custom:") for key in mapped_row.keys()
                    )
                    if not has_custom_mapping and not sync_record_needs_update(
                        existing, proposed, force=force_rewrite
                    ):
                        skipped += 1
                        continue
                    existing.name = name
                    existing.specification = specification
                    existing.base_unit = resolved_unit
                    if group_id is not None:
                        existing.group_id = group_id
                    _apply_material_extra_scalars(
                        existing,
                        mapped_row,
                        update_fields,
                        conversion_entries=conversion_entries,
                        source_field_names=source_field_names,
                    )
                    existing.external_sync_at = sync_at
                    existing.updated_at = sync_at
                    if current_user is not None:
                        apply_update_audit(existing, current_user)
                    to_update.append(existing)
                else:
                    source_type = (
                        _coerce_material_extra_value(
                            "source_type",
                            mapped_row.get("source_type"),
                            conversion_entries,
                            source_field_names,
                        )
                        if "source_type" in mapped_row
                        else None
                    ) or require_canonical_material_source_type(
                        "Buy",
                        material_code=main_code,
                        material_name=name,
                    )
                    payload: Dict[str, Any] = {
                        "tenant_id": tenant_id,
                        "main_code": main_code,
                        "code": main_code,
                        "name": name,
                        "specification": specification,
                        "base_unit": resolved_unit,
                        "source_type": source_type,
                        "is_active": True,
                        "variant_managed": False,
                        "external_sync_at": sync_at,
                    }
                    if group_id is not None:
                        payload["group_id"] = group_id
                    if current_user is not None:
                        apply_create_audit(payload, current_user)
                    material = Material(**payload)
                    _apply_material_extra_scalars(
                        material,
                        mapped_row,
                        [],
                        conversion_entries=conversion_entries,
                        source_field_names=source_field_names,
                    )
                    to_create.append(material)
            except Exception as exc:
                failed += 1
                errors.append(f"物料 {main_code}：{exc}")

        write_batch = 500

        async def _write_custom_fields_for_materials(materials: List[Material]) -> None:
            if not custom_fields_by_code or not materials:
                return
            for material in materials:
                mapped = custom_payload_by_code.get(material.main_code)
                if not mapped:
                    continue
                try:
                    await apply_mapped_custom_field_values(
                        tenant_id=tenant_id,
                        record_table=MATERIAL_CUSTOM_FIELD_TABLE,
                        record_id=int(material.id),
                        mapped_row=mapped,
                        fields_by_code=custom_fields_by_code,
                    )
                except Exception as cf_exc:
                    errors.append(f"物料 {material.main_code} 自定义字段：{cf_exc}")

        async def _flush_updates(batch: List[Material], start_index: int) -> None:
            nonlocal updated, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量更新物料 {start_index}-{end_index}/{len(to_update)}…"
            )
            try:
                await Material.bulk_update(batch, fields=update_fields, batch_size=write_batch)
                updated += len(batch)
                await _write_custom_fields_for_materials(batch)
            except Exception:
                for material in batch:
                    try:
                        await material.save(update_fields=update_fields)
                        updated += 1
                        await _write_custom_fields_for_materials([material])
                    except Exception as row_exc:
                        failed += 1
                        errors.append(f"物料 {material.main_code}：{row_exc}")

        async def _flush_creates(batch: List[Material], start_index: int) -> None:
            nonlocal created, failed
            if not batch:
                return
            end_index = start_index + len(batch) - 1
            await emit_sync_progress(
                f"正在批量新建物料 {start_index}-{end_index}/{len(to_create)}…"
            )
            try:
                await Material.bulk_create(batch, batch_size=write_batch)
                created += len(batch)
                codes_created = [item.main_code for item in batch]
                persisted = await Material.filter(
                    tenant_id=tenant_id,
                    main_code__in=codes_created,
                    deleted_at__isnull=True,
                ).all()
                await _write_custom_fields_for_materials(persisted)
            except Exception:
                for material in batch:
                    try:
                        await material.save()
                        created += 1
                        await _write_custom_fields_for_materials([material])
                    except Exception as row_exc:
                        failed += 1
                        errors.append(f"物料 {material.main_code}：{row_exc}")

        for offset in range(0, len(to_update), write_batch):
            await _flush_updates(to_update[offset : offset + write_batch], offset + 1)
        for offset in range(0, len(to_create), write_batch):
            await _flush_creates(to_create[offset : offset + write_batch], offset + 1)

        await emit_sync_progress(
            f"物料写入完成：新建 {created}，更新 {updated}，跳过 {skipped}，失败 {failed}"
        )
        return MasterDataSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )
