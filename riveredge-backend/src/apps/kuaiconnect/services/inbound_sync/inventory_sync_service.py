"""即时库存从数据接口/数据集同步服务。"""
from __future__ import annotations

import copy
from fractions import Fraction
import uuid
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from infra.exceptions.exceptions import ValidationError
from infra.models.user import User
from tortoise import connections

from apps.kuaizhizao.models.inventory_sync_binding import InventorySyncBinding
from apps.kuaizhizao.schemas.inventory_sync import (
    InventorySyncBindingOut,
    InventorySyncBindingUpsert,
    InventorySyncFromSourceOut,
    InventorySyncFromSourceRequest,
)
from apps.master_data.constants.batch_quality_status import QUALIFIED
from apps.master_data.models.material import Material
from apps.master_data.models.material_batch import MaterialBatch
from apps.master_data.models.warehouse import StorageLocation, Warehouse
from apps.kuaiconnect.services.inbound_sync.master_data_sync_common import (
    attach_sync_fetch_meta,
    serialize_binding_row,
    cell_optional_decimal,
    cell_str,
    fetch_sync_rows,
    lookup_mapped_source_value,
    map_sync_rows,
    mark_binding_failure,
    mark_binding_partial_success,
    mark_binding_success,
    normalize_schedule_interval,
    normalize_sync_direction,
    normalize_sync_mode,
    record_sync_run_log,
    resolve_business_datetime,
    resolve_incremental_since,
    resolve_sync_sources,
    sources_from_upsert_body,
    upsert_sync_binding,
    resolve_schedule_window_for_sync_request,
    resolve_upsert_schedule_from_body,
)
from apps.kuaiconnect.services.inbound_sync.sync_binding_sources import fetch_mapped_rows_from_sources
from apps.master_data.utils.kingdee_location_number import (
    index_storage_locations_for_inbound_sync,
    resolve_storage_location_for_inbound_sync,
)
from core.services.data.sync_progress import emit_sync_progress


INVENTORY_WRITE_CHUNK = 500
# 金蝶即时库存：数量优先 avbqty，其次 qty；批号 lotnum。映射到空列（如 baseqty）时回退。
INVENTORY_MAP_EMPTY_FALLBACKS = {
    "quantity": ["avbqty", "qty", "baseqty"],
    "base_quantity": ["baseqty", "base_qty", "baseQty", "base_quantity"],
    "aux_quantity": [
        "avbqty2nd",
        "qty2nd",
        "auxqty",
        "aux_qty",
        "auxQty",
        "secqty",
        "sec_qty",
        "auxiliaryqty",
        "auxiliary_qty",
    ],
    "aux_unit": [
        "unit2nd.number",
        "unit2nd_number",
        "unit2nd.name",
        "unit2nd_name",
        "secunit_number",
        "secunit.number",
        "secunit_name",
        "secunit.name",
        "auxunit_number",
        "auxunit.number",
        "auxunit_name",
        "auxunit.name",
        "aux_unit",
        "auxUnit",
    ],
    "batch_no": ["lotnum", "lot_number", "lot.number", "batch_no", "batch_number"],
    "location_code": [
        "location.number",
        "location_number",
        "locationNumber",
        "location_code",
        "locationCode",
        "location",
    ],
    "location_name": ["location.name", "location_name", "locationName"],
}


def normalize_inventory_sync_batch_no(row: Dict[str, Any]) -> str:
    """即时库存源常无批号；空值落空串（与库存增减口径一致），并兼容金蝶 lotnum。"""
    return _inventory_cell(
        row,
        "batch_no",
        "batch_number",
        "batchNo",
        "lotnum",
        "lot_number",
        "lot.number",
    )[:100]


def _compact_sync_errors(errors: List[str], *, limit: int = 12) -> List[str]:
    counts: Dict[str, int] = {}
    order: List[str] = []
    for item in errors:
        text = str(item or "").strip()
        if not text:
            continue
        if text not in counts:
            order.append(text)
            counts[text] = 0
        counts[text] += 1
    out: List[str] = []
    for text in order[:limit]:
        n = counts[text]
        out.append(f"{text}（共 {n} 条）" if n > 1 else text)
    return out


def _empty_inventory_write_message(result: Any, fetched: int) -> str:
    skipped = int(getattr(result, "skipped", 0) or 0)
    failed = int(getattr(result, "failed", 0) or 0)
    msg = (
        f"未写入任何库存（拉取 {int(fetched or 0)} 条，"
        f"新建 0，更新 0，跳过 {skipped}，失败 {failed}）"
    )
    details = _compact_sync_errors(list(getattr(result, "errors", None) or []))
    if details:
        msg = f"{msg}。{ '；'.join(details) }"
    elif int(fetched or 0) == 0:
        msg = f"{msg}。请检查接口调用参数、物料编码分批条件是否返回了余额行"
    else:
        msg = f"{msg}。请确认物料主数据已同步，且映射了物料编码、数量、仓库编码或名称"
    return msg[:2000]


def _inventory_cell(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = cell_str(row.get(key))
        if text:
            return text
    return ""


def _inventory_quantity(row: Dict[str, Any]) -> Optional[float]:
    for key in ("quantity", "avbqty", "qty", "baseqty"):
        raw = row.get(key)
        if raw in (None, ""):
            continue
        text = str(raw).strip()
        if not text or text in {"-", "--"}:
            continue
        qty = cell_optional_decimal(raw)
        if qty is not None:
            return float(qty)
    return None


def _inventory_lookup_cell(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        found, value = lookup_mapped_source_value(row, key)
        if found:
            text = cell_str(value)
            if text:
                return text
        text = cell_str(row.get(key))
        if text:
            return text
    return ""


def _inventory_auxiliary_unit(row: Dict[str, Any]) -> str:
    """提取即时库存行辅助单位（兼容苍穹 unit2nd.* 与 secunit_* / aux_unit）。"""
    return _inventory_lookup_cell(
        row,
        "aux_unit",
        "auxUnit",
        "secunit_number",
        "secunit.number",
        "secunit_name",
        "secunit.name",
        "unit2nd.number",
        "unit2nd_number",
        "unit2nd.name",
        "unit2nd_name",
        "auxunit_number",
        "auxunit.number",
        "auxunit_name",
        "auxunit.name",
    )


def _inventory_auxiliary_quantity(row: Dict[str, Any]) -> Optional[float]:
    """提取即时库存行辅助数量（兼容苍穹 avbqty2nd / qty2nd 与 auxqty / secqty）。"""
    for key in (
        "aux_quantity",
        "avbqty2nd",
        "qty2nd",
        "auxqty",
        "aux_qty",
        "auxQty",
        "secqty",
        "sec_qty",
        "auxiliaryqty",
        "auxiliary_qty",
    ):
        found, raw = lookup_mapped_source_value(row, key)
        if not found:
            raw = row.get(key)
        if raw in (None, ""):
            continue
        text = str(raw).strip()
        if not text or text in {"-", "--"}:
            continue
        qty = cell_optional_decimal(raw)
        if qty is not None:
            return float(qty)
    return None


def _aux_base_ratio_n_d(
    base_quantity: Decimal,
    aux_quantity: Decimal,
) -> Tuple[int, int]:
    """由基本量 / 辅助量反推 1 辅助单位 = (numerator / denominator) 基本单位。"""
    base_q = Decimal(str(base_quantity))
    aux_q = Decimal(str(aux_quantity))
    if base_q <= 0:
        raise ValidationError("推算固定辅助单位换算比时，基本数量必须大于 0")
    if aux_q <= 0:
        raise ValidationError("推算固定辅助单位换算比时，辅助数量必须大于 0")
    ratio = (Fraction(base_q) / Fraction(aux_q)).limit_denominator(1_000_000)
    if ratio.numerator <= 0 or ratio.denominator <= 0:
        raise ValidationError("推算固定辅助单位换算比失败：换算比须大于 0")
    return int(ratio.numerator), int(ratio.denominator)


async def ensure_material_fixed_aux_from_inventory_row(
    material: Any,
    *,
    aux_unit: Optional[str],
    base_quantity: Optional[Decimal],
    aux_quantity: Optional[Decimal],
    current_user: Optional[User] = None,
) -> bool:
    """
    依据苍穹/金蝶即时库存行的双计量数值补齐或升级物料固定辅助单位。

    - 已有同名固定辅助单位：跳过（返回 False）
    - 已有同名浮动辅助单位：升级为固定换算并落库（返回 True）
    - 缺失辅助单位：新增固定换算辅助单位并落库（返回 True）
    """
    if material is None:
        return False
    unit_name = str(aux_unit or "").strip()
    if not unit_name:
        return False
    base_unit = str(getattr(material, "base_unit", None) or "").strip()
    if base_unit and unit_name.casefold() == base_unit.casefold():
        return False
    if base_quantity is None or aux_quantity is None:
        return False
    base_q = Decimal(str(base_quantity))
    aux_q = Decimal(str(aux_quantity))
    if base_q <= 0 or aux_q <= 0:
        return False

    numerator, denominator = _aux_base_ratio_n_d(base_q, aux_q)

    from apps.kuaizhizao.utils.material_unit_utils import _parse_material_units_cfg
    from apps.master_data.constants.material_conversion_type import (
        CONVERSION_TYPE_FIXED,
        is_floating_aux_unit_row,
    )

    parsed = _parse_material_units_cfg(getattr(material, "units", None))
    units_cfg: Dict[str, Any] = copy.deepcopy(parsed) if isinstance(parsed, dict) else {}
    raw_rows = units_cfg.get("units")
    unit_rows: List[Dict[str, Any]] = (
        [row for row in raw_rows if isinstance(row, dict)]
        if isinstance(raw_rows, list)
        else []
    )
    scenarios = units_cfg.get("scenarios")
    if not isinstance(scenarios, dict):
        scenarios = {}
    units_cfg["units"] = unit_rows
    units_cfg["scenarios"] = scenarios

    target_key = unit_name.casefold()
    matched_row: Optional[Dict[str, Any]] = None
    for row in unit_rows:
        existing_name = str(row.get("unit") or "").strip()
        if existing_name and existing_name.casefold() == target_key:
            matched_row = row
            break

    if matched_row is not None:
        if not is_floating_aux_unit_row(matched_row):
            return False
        matched_row["unit"] = unit_name
        matched_row["numerator"] = numerator
        matched_row["denominator"] = denominator
        matched_row["conversionType"] = CONVERSION_TYPE_FIXED
        matched_row.pop("conversion_type", None)
    else:
        unit_rows.append(
            {
                "unit": unit_name,
                "numerator": numerator,
                "denominator": denominator,
                "conversionType": CONVERSION_TYPE_FIXED,
            }
        )

    material.units = units_cfg
    update_fields = ["units", "updated_at"]
    if current_user is not None:
        from apps.common.audit_actor import operator_name_from_user

        material.updated_by = int(current_user.id)
        material.updated_by_name = operator_name_from_user(current_user)
        update_fields.extend(["updated_by", "updated_by_name"])
    await material.save(update_fields=update_fields)
    return True


def _chunks(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


class InventorySyncService:
    MATCH_KEY = "material_code"

    def serialize_binding(self, row: Optional[InventorySyncBinding]) -> InventorySyncBindingOut:
        data = serialize_binding_row(row, default_match_key=self.MATCH_KEY)
        return InventorySyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: InventorySyncBindingUpsert,
    ) -> InventorySyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await InventorySyncBinding.filter(tenant_id=tenant_id).delete()
            return InventorySyncBindingOut(match_key_field=self.MATCH_KEY)

        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or self.MATCH_KEY).strip() or self.MATCH_KEY
        sync_mode = normalize_sync_mode(body.sync_mode)
        sync_direction = normalize_sync_direction(body.sync_direction)
        interval, w_start, w_end = await resolve_upsert_schedule_from_body(
            InventorySyncBinding, tenant_id, body
        )
        row = await upsert_sync_binding(
            InventorySyncBinding,
            tenant_id,
            sources=sources,
            match_key_field=match_key,
            sync_mode=sync_mode,
            sync_direction=sync_direction,
            schedule_interval_minutes=interval,
            schedule_window_start=w_start,
            schedule_window_end=w_end,
        )
        return self.serialize_binding(row)

    async def get_binding(self, tenant_id: int) -> InventorySyncBindingOut:
        row = await InventorySyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    async def sync_from_source(
        self,
        tenant_id: int,
        current_user: Optional[User],
        request: Optional[InventorySyncFromSourceRequest] = None,
        *,
        skip_prerequisite_syncs: bool = False,
    ) -> InventorySyncFromSourceOut:
        req = request or InventorySyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            InventorySyncBinding,
            tenant_id,
            req,
            default_match_key=self.MATCH_KEY,
        )

        binding = binding or await InventorySyncBinding.filter(tenant_id=tenant_id).first()
        sync_mode = normalize_sync_mode(
            req.sync_mode or (binding.sync_mode if binding else None)
        )
        sync_direction = normalize_sync_direction(
            req.sync_direction or (binding.sync_direction if binding else None)
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
                InventorySyncBindingUpsert(
                    sources=req.sources,
                    match_key_field=match_key,
                    sync_mode=sync_mode,
                    sync_direction=sync_direction,
                    schedule_interval_minutes=interval,
                    schedule_window_start=w_start,
                    schedule_window_end=w_end,
                ),
            )
            binding = await InventorySyncBinding.filter(tenant_id=tenant_id).first()

        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )

        started_at = resolve_business_datetime()
        try:
            from apps.kuaiconnect.services.document_push.warehouse_kingdee_alignment import (
                list_inventory_pull_blockers,
            )
            from infra.exceptions.exceptions import BusinessLogicError

            blockers = await list_inventory_pull_blockers(tenant_id)
            if blockers:
                preview = "；".join(blockers[:8])
                raise BusinessLogicError(
                    f"仓储单据与金蝶未对齐，禁止用即时库存覆盖本地批次：{preview}"
                )
            await emit_sync_progress("开始同步即时库存…")
            rows, source_errors, fetched = await fetch_mapped_rows_from_sources(
                tenant_id,
                sources,
                since=since,
                active_only=req.active_only,
                empty_fallbacks=INVENTORY_MAP_EMPTY_FALLBACKS,
            )
            await emit_sync_progress(f"字段映射完成，准备写入 {len(rows)} 条库存记录…")
            result = await self._upsert_batches(tenant_id, current_user, rows, match_key)
            if source_errors:
                result.errors = (source_errors + list(result.errors))[:20]
            attach_sync_fetch_meta(result, fetched=fetched, since=since, truncated=False)
            result.errors = _compact_sync_errors(list(result.errors or []))
            wrote = bool(result.created or result.updated)
            if binding:
                if not wrote:
                    incremental_noop = (
                        since is not None
                        and fetched == 0
                        and not result.failed
                        and not result.skipped
                    )
                    if incremental_noop:
                        await mark_binding_success(binding)
                    else:
                        await mark_binding_failure(
                            binding,
                            _empty_inventory_write_message(result, fetched),
                        )
                elif result.failed:
                    await mark_binding_partial_success(
                        binding,
                        "；".join(result.errors) or "即时库存部分行同步失败",
                    )
                else:
                    await mark_binding_success(binding)
            await record_sync_run_log(
                tenant_id=tenant_id,
                binding=binding,
                entity_type="inventory",
                result=result,
                started_at=started_at,
                truncated=False,
            )
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            await record_sync_run_log(
                tenant_id=tenant_id,
                binding=binding,
                entity_type="inventory",
                result=None,
                started_at=started_at,
                error=str(exc),
            )
            raise

    async def _upsert_batches(
        self,
        tenant_id: int,
        current_user: Optional[User],
        rows: List[Dict[str, Any]],
        match_key: str,
    ) -> InventorySyncFromSourceOut:
        """金蝶仍一次拉全量；本地认仓认料后批量 UPSERT，避免逐行写库拖垮进度流。"""
        created = 0
        updated = 0
        skipped = 0
        failed = 0
        errors: List[str] = []

        await emit_sync_progress("正在预加载本地仓库与物料…")
        warehouses = await Warehouse.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).all()
        warehouse_by_code = {str(w.code).strip(): w for w in warehouses if str(w.code or "").strip()}
        warehouse_by_name = {str(w.name).strip(): w for w in warehouses if str(w.name or "").strip()}

        storage_locations = await StorageLocation.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).all()
        location_by_code, location_by_wh_source, location_by_name = (
            index_storage_locations_for_inbound_sync(storage_locations)
        )

        materials = await Material.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).all()
        material_by_code: Dict[str, Material] = {}
        for material in materials:
            main_code = str(getattr(material, "main_code", None) or "").strip()
            code = str(getattr(material, "code", None) or "").strip()
            if main_code:
                material_by_code[main_code] = material
            if code and code not in material_by_code:
                material_by_code[code] = material

        payloads: Dict[Tuple[int, str, int, str], Dict[str, Any]] = {}
        default_loc_by_wh: Dict[int, Tuple[Optional[int], str]] = {}
        await emit_sync_progress(f"正在匹配 {len(rows)} 条来源行…")
        for row in rows:
            warehouse_code = _inventory_cell(
                row, "warehouse_code", "warehouseCode", "warehouse.number"
            )
            warehouse_name = _inventory_cell(
                row, "warehouse_name", "warehouseName", "warehouse.name"
            )
            if not warehouse_code and not warehouse_name:
                failed += 1
                errors.append("存在缺少仓库编码或仓库名称的行")
                continue
            warehouse = warehouse_by_code.get(warehouse_code) if warehouse_code else None
            if warehouse is None and warehouse_name:
                warehouse = warehouse_by_name.get(warehouse_name)
            if warehouse is None:
                failed += 1
                errors.append(f"仓库不存在：{warehouse_code or warehouse_name}")
                continue

            material_code = _inventory_cell(
                row,
                match_key,
                "material_code",
                "material.number",
                "material",
                "number",
                "code",
            )
            if not material_code:
                failed += 1
                errors.append("存在缺少物料编码的行")
                continue
            material = material_by_code.get(material_code)
            if material is None:
                failed += 1
                errors.append(f"物料 {material_code} 不存在，请先同步物料主数据")
                continue

            quantity = _inventory_quantity(row)
            if quantity is None:
                failed += 1
                errors.append(f"物料 {material_code} 缺少库存数量")
                continue

            from apps.kuaizhizao.utils.ledger_dual_quantity_utils import (
                resolve_sync_ledger_quantities,
            )

            base_raw = _inventory_cell(row, "baseqty", "base_qty", "baseQty", "base_quantity")
            aux_qty_val = _inventory_auxiliary_quantity(row)
            aux_unit_val = _inventory_auxiliary_unit(row)
            base_dec_opt = Decimal(str(base_raw)) if base_raw not in (None, "") else None
            aux_dec_opt = Decimal(str(aux_qty_val)) if aux_qty_val is not None else None
            try:
                if aux_unit_val and aux_dec_opt is not None and aux_dec_opt > 0:
                    infer_base_dec = (
                        base_dec_opt
                        if base_dec_opt is not None and base_dec_opt > 0
                        else Decimal(str(quantity))
                    )
                    if infer_base_dec > 0:
                        await ensure_material_fixed_aux_from_inventory_row(
                            material,
                            aux_unit=aux_unit_val,
                            base_quantity=infer_base_dec,
                            aux_quantity=aux_dec_opt,
                            current_user=current_user,
                        )
                synced = resolve_sync_ledger_quantities(
                    material,
                    primary_quantity=Decimal(str(quantity)),
                    base_quantity_raw=base_dec_opt,
                    aux_quantity_raw=aux_dec_opt,
                )
            except Exception as exc:
                failed += 1
                errors.append(f"物料 {material_code} 库存数量解析失败：{exc}")
                continue

            location_code = _inventory_cell(
                row,
                "location_code",
                "locationCode",
                "location.number",
                "location_number",
                "locationNumber",
                "location",
            )[:50]
            location_name = _inventory_cell(
                row, "location_name", "locationName", "location.name"
            )
            location_id: Optional[int] = None
            loc = resolve_storage_location_for_inbound_sync(
                warehouse_id=int(warehouse.id),
                source_location_key=location_code,
                location_by_code=location_by_code,
                location_by_wh_source=location_by_wh_source,
                location_by_name=location_by_name,
                location_name=location_name,
            )
            if loc is not None:
                location_id = int(loc.id)
                location_code = str(loc.code or "").strip()[:50]
            elif not location_code and location_name:
                # 苍穹仓位可能只有名称（如「无货架」）；无主数据时用名称作编码落账
                location_code = location_name[:50]

            if not str(location_code or "").strip():
                from apps.master_data.services.warehouse_service import WarehouseService

                wh_int = int(warehouse.id)
                if wh_int not in default_loc_by_wh:
                    default_loc_by_wh[wh_int] = (
                        await WarehouseService.resolve_kingdee_default_storage_location(
                            tenant_id, wh_int
                        )
                    )
                def_id, def_code = default_loc_by_wh[wh_int]
                if def_code:
                    location_code = def_code
                    if def_id:
                        location_id = def_id

            from apps.kuaizhizao.services.inventory_service import InventoryService

            batch_no = InventoryService._normalize_batch_no_for_ledger(
                normalize_inventory_sync_batch_no(row)
            )
            # 本地台账键不含金蝶库存类型；同仓同位普通/赠品等多行须累加，禁止后写覆盖（否则 0 会冲掉赠品量）。
            key = (int(material.id), batch_no, int(warehouse.id), location_code)
            existing_payload = payloads.get(key)
            if existing_payload is None:
                payloads[key] = {
                    "material_id": int(material.id),
                    "batch_no": batch_no,
                    "warehouse_id": int(warehouse.id),
                    "warehouse_name": (warehouse.name or warehouse_name or None),
                    "location_id": location_id,
                    "location_code": location_code,
                    "quantity": synced.quantity,
                    "base_quantity": synced.base_quantity,
                    "aux_quantity": synced.aux_quantity,
                }
            else:
                payloads[key] = {
                    **existing_payload,
                    "location_id": location_id or existing_payload.get("location_id"),
                    "warehouse_name": (
                        warehouse.name
                        or warehouse_name
                        or existing_payload.get("warehouse_name")
                    ),
                    "quantity": existing_payload["quantity"] + synced.quantity,
                    "base_quantity": existing_payload["base_quantity"]
                    + synced.base_quantity,
                    "aux_quantity": existing_payload["aux_quantity"] + synced.aux_quantity,
                }

        if not payloads:
            await emit_sync_progress(
                f"库存写入完成：新建 0，更新 0，跳过 {skipped}，失败 {failed}"
            )
            return InventorySyncFromSourceOut(
                created=0,
                updated=0,
                skipped=skipped,
                failed=failed,
                errors=_compact_sync_errors(errors),
            )

        material_ids = list({item["material_id"] for item in payloads.values()})
        existing_rows = await MaterialBatch.filter(
            tenant_id=tenant_id,
            material_id__in=material_ids,
            ownership_type="company_owned",
            customer_id=0,
            quality_status=QUALIFIED,
            deleted_at__isnull=True,
        ).only("id", "material_id", "batch_no", "warehouse_id", "location_code")
        from apps.kuaizhizao.services.inventory_service import InventoryService

        existing_keys = {
            (
                int(row.material_id),
                InventoryService._normalize_batch_no_for_ledger(str(row.batch_no or "")),
                int(row.warehouse_id or 0),
                str(row.location_code or ""),
            )
            for row in existing_rows
        }

        to_insert: List[Dict[str, Any]] = []
        to_update: List[Dict[str, Any]] = []
        for key, item in payloads.items():
            if key in existing_keys:
                to_update.append(item)
            else:
                to_insert.append(item)

        now = resolve_business_datetime()
        actor_id = None
        actor_name = None
        if current_user is not None:
            from apps.common.audit_actor import operator_name_from_user

            actor_id = int(current_user.id)
            actor_name = operator_name_from_user(current_user)

        await emit_sync_progress(
            f"正在批量写入库存：新建 {len(to_insert)}，更新 {len(to_update)}…"
        )
        if to_update:
            updated += await self._bulk_update_on_hand(
                tenant_id, to_update, now, actor_id, actor_name
            )
        if to_insert:
            created += await self._bulk_insert_on_hand(
                tenant_id, to_insert, now, actor_id, actor_name
            )

        await emit_sync_progress(
            f"库存写入完成：新建 {created}，更新 {updated}，跳过 {skipped}，失败 {failed}"
        )
        return InventorySyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=_compact_sync_errors(errors),
        )

    async def _bulk_update_on_hand(
        self,
        tenant_id: int,
        items: List[Dict[str, Any]],
        now: Any,
        actor_id: Optional[int],
        actor_name: Optional[str],
    ) -> int:
        conn = connections.get("default")
        sql = """
            UPDATE apps_master_data_material_batches AS b
            SET quantity = v.quantity,
                base_quantity = v.base_quantity,
                aux_quantity = v.aux_quantity,
                status = CASE WHEN v.quantity > 0 THEN 'in_stock' ELSE 'out_stock' END,
                warehouse_name = COALESCE(v.warehouse_name, b.warehouse_name),
                location_id = COALESCE(v.location_id, b.location_id),
                batch_no = v.batch_no,
                updated_at = $10::timestamptz,
                updated_by = $11::int,
                updated_by_name = $12::varchar
            FROM (
                SELECT *
                FROM unnest(
                    $1::int[], $2::varchar[], $3::int[], $4::varchar[],
                    $5::numeric[], $6::numeric[], $7::numeric[],
                    $8::varchar[], $9::int[]
                ) AS t(
                    material_id, batch_no, warehouse_id, location_code,
                    quantity, base_quantity, aux_quantity,
                    warehouse_name, location_id
                )
            ) AS v
            WHERE b.tenant_id = $13::int
              AND b.material_id = v.material_id
              AND (
                b.batch_no = v.batch_no
                OR (
                  v.batch_no = 'DEFAULT'
                  AND (b.batch_no = '' OR b.batch_no IS NULL)
                )
              )
              AND b.warehouse_id = v.warehouse_id
              AND b.location_code = v.location_code
              AND b.ownership_type = 'company_owned'
              AND b.customer_id = 0
              AND b.quality_status = $14::varchar
              AND b.deleted_at IS NULL
        """
        written = 0
        for chunk in _chunks(items, INVENTORY_WRITE_CHUNK):
            await conn.execute_query(
                sql,
                [
                    [item["material_id"] for item in chunk],
                    [item["batch_no"] for item in chunk],
                    [item["warehouse_id"] for item in chunk],
                    [item["location_code"] for item in chunk],
                    [item["quantity"] for item in chunk],
                    [item["base_quantity"] for item in chunk],
                    [item["aux_quantity"] for item in chunk],
                    [item["warehouse_name"] for item in chunk],
                    [item.get("location_id") for item in chunk],
                    now,
                    actor_id,
                    actor_name,
                    tenant_id,
                    QUALIFIED,
                ],
            )
            written += len(chunk)
        return written

    async def _bulk_insert_on_hand(
        self,
        tenant_id: int,
        items: List[Dict[str, Any]],
        now: Any,
        actor_id: Optional[int],
        actor_name: Optional[str],
    ) -> int:
        conn = connections.get("default")
        sql = """
            INSERT INTO apps_master_data_material_batches (
                uuid, tenant_id, material_id, batch_no, warehouse_id, warehouse_name,
                location_id, location_code,
                quantity, base_quantity, aux_quantity,
                status, ownership_type, customer_id, quality_status,
                created_at, updated_at, created_by, created_by_name, updated_by, updated_by_name
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'company_owned',0,$13,$14,$14,$15,$16,$15,$16
            )
            ON CONFLICT (
                tenant_id, material_id, batch_no, ownership_type, customer_id,
                warehouse_id, quality_status, location_code
            )
            WHERE (deleted_at IS NULL)
            DO UPDATE SET
                quantity = EXCLUDED.quantity,
                base_quantity = EXCLUDED.base_quantity,
                aux_quantity = EXCLUDED.aux_quantity,
                status = EXCLUDED.status,
                warehouse_name = COALESCE(
                    EXCLUDED.warehouse_name, apps_master_data_material_batches.warehouse_name
                ),
                location_id = COALESCE(
                    EXCLUDED.location_id, apps_master_data_material_batches.location_id
                ),
                updated_at = EXCLUDED.updated_at,
                updated_by = EXCLUDED.updated_by,
                updated_by_name = EXCLUDED.updated_by_name
        """
        written = 0
        for chunk in _chunks(items, INVENTORY_WRITE_CHUNK):
            values = [
                [
                    str(uuid.uuid4()),
                    tenant_id,
                    item["material_id"],
                    item["batch_no"],
                    item["warehouse_id"],
                    item["warehouse_name"],
                    item.get("location_id"),
                    item["location_code"],
                    item["quantity"],
                    item["base_quantity"],
                    item["aux_quantity"],
                    "in_stock" if item["quantity"] > 0 else "out_stock",
                    QUALIFIED,
                    now,
                    actor_id,
                    actor_name,
                ]
                for item in chunk
            ]
            await conn.execute_many(sql, values)
            written += len(chunk)
        return written

    async def _upsert_sync_binding(
        self,
        tenant_id: int,
        *,
        source_type: str,
        api_uuid: Optional[str],
        dataset_uuid: Optional[str],
        field_mapping: Dict[str, str],
        match_key_field: str,
        sync_mode: str,
        sync_direction: str,
        schedule_interval_minutes: Optional[int],
    ) -> InventorySyncBinding:
        if source_type not in ("api", "dataset"):
            raise ValidationError("来源类型须为 api 或 dataset")
        if source_type == "api" and not api_uuid:
            raise ValidationError("已选择数据接口时须指定接口")
        if source_type == "dataset" and not dataset_uuid:
            raise ValidationError("已选择数据集时须指定数据集")
        if not field_mapping:
            raise ValidationError("请配置字段映射")
        if match_key_field not in field_mapping.values():
            raise ValidationError(f"字段映射须包含匹配键 {match_key_field}")

        mode = normalize_sync_mode(sync_mode)
        direction = normalize_sync_direction(sync_direction)
        interval = normalize_schedule_interval(schedule_interval_minutes)
        existing = await InventorySyncBinding.filter(tenant_id=tenant_id).first()
        preserve = {
            "last_success_at": existing.last_success_at if existing else None,
            "last_attempt_at": existing.last_attempt_at if existing else None,
            "last_error": existing.last_error if existing else None,
            "schedule_window_start": getattr(existing, "schedule_window_start", None) if existing else None,
            "schedule_window_end": getattr(existing, "schedule_window_end", None) if existing else None,
        }
        await InventorySyncBinding.filter(tenant_id=tenant_id).delete()
        return await InventorySyncBinding.create(
            tenant_id=tenant_id,
            source_type=source_type,
            api_uuid=api_uuid if source_type == "api" else None,
            dataset_uuid=dataset_uuid if source_type == "dataset" else None,
            field_mapping=field_mapping,
            match_key_field=match_key_field,
            sync_mode=mode,
            sync_direction=direction,
            schedule_interval_minutes=interval,
            **preserve,
        )
