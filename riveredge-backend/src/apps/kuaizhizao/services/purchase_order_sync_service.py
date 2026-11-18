"""采购订单从数据接口/数据集同步服务。

写路径对齐销售订单同步：预加载供应商/物料/已有订单 → 内存组 payload →
轻量 create/update + bulk_create 明细，避免逐行 N+1 导致超时。
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from infra.exceptions.exceptions import BusinessLogicError, ValidationError
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from apps.kuaizhizao.constants import DocumentStatus, ReviewStatus
from apps.kuaizhizao.constants.price_type import DEFAULT_PURCHASE_PRICE_TYPE, normalize_price_type
from apps.kuaizhizao.constants.purchase_order_type import normalize_purchase_order_type
from apps.kuaicaiwu.services.purchase_settlement import (
    PURCHASE_ORDER_COMPUTED_HEADER_FIELDS,
    normalize_po_tax_rate_to_percent,
    sync_purchase_order_header_amounts,
)
from apps.kuaizhizao.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from apps.kuaizhizao.models.purchase_order_sync_binding import PurchaseOrderSyncBinding
from apps.kuaizhizao.schemas.purchase import (
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
    PurchaseOrderUpdate,
)
from apps.kuaizhizao.schemas.purchase_order_sync import (
    PurchaseOrderPushBindingOut,
    PurchaseOrderPushBindingUpsert,
    PurchaseOrderSyncBindingOut,
    PurchaseOrderSyncBindingUpsert,
    PurchaseOrderSyncFromSourceOut,
    PurchaseOrderSyncFromSourceRequest,
)
from apps.kuaizhizao.services.document_recognition import ensure_payable_recognition_on_create
from apps.kuaizhizao.utils.price_settlement_helpers import (
    derive_price_settlement_status,
    derive_provisional_unit_price,
)
from apps.master_data.services.master_data_sync_common import (
    apply_mapped_custom_field_values,
    attach_sync_fetch_meta,
    fetch_sync_rows,
    load_custom_fields_by_code,
    mark_binding_failure,
    mark_binding_success,
    normalize_schedule_interval,
    normalize_sync_mode,
    resolve_incremental_since,
    resolve_sync_sources,
    serialize_binding_row,
    sources_from_upsert_body,
    upsert_sync_binding,
)
from apps.master_data.config.partner_settlement_codes import partner_settlement_terms_for_pricing
from apps.master_data.models.material import Material
from apps.master_data.models.supplier import Supplier
from apps.master_data.services.sync_association_service import (
    run_purchase_order_prerequisite_syncs,
)
from core.services.data.sync_from_source_fetch import (
    fetch_rows_from_api,
    fetch_rows_from_dataset,
)
from core.services.data.sync_progress import emit_sync_progress
from core.utils.timezone_utils import resolve_business_datetime

PURCHASE_ORDER_CUSTOM_FIELD_TABLE = "apps_kuaizhizao_purchase_orders"

_SYNC_WRITE_PROGRESS_EVERY = 25
_LOOKUP_IN_CHUNK = 800

# 明细摊平后，源列名会被加上明细键前缀（见 sync_nested_expand）
_DETAIL_FLAT_PREFIXES = (
    "billentry",
    "BillEntry",
    "FEntity",
    "fentity",
    "entry",
    "TreeEntity",
    "treeEntity",
)
_MISSING = object()

_PURCHASE_ORDER_SYNC_HEADER_EXCLUDE = frozenset(
    {
        "items",
        "payment_milestones",
        "audit",
        "prepayment_unsettled_balance",
        "estimated_payable_after_prepayment",
        "document_flow_source_type",
        "document_flow_requisition_item_ids",
        "document_flow_item_quantities",
        "document_flow_item_unit_prices",
        "document_flow_item_suppliers",
        "document_flow_persist_default_supplier",
        "document_flow_inquiry_item_ids",
        "document_flow_demand_computation_item_ids",
        "document_flow_demand_computation_ids",
        "document_flow_replenishment_suggestion_ids",
        "document_flow_sales_order_id",
        *PURCHASE_ORDER_COMPUTED_HEADER_FIELDS,
    }
)


class PurchaseOrderSyncService:
    ITEM_PREFIX = "item."

    def serialize_binding(self, row: Optional[PurchaseOrderSyncBinding]) -> PurchaseOrderSyncBindingOut:
        if not row:
            return PurchaseOrderSyncBindingOut()
        data = serialize_binding_row(row, default_match_key="order_code")
        return PurchaseOrderSyncBindingOut(**data)

    async def upsert_binding(
        self,
        tenant_id: int,
        body: PurchaseOrderSyncBindingUpsert,
    ) -> PurchaseOrderSyncBindingOut:
        if body.sources is not None and len(body.sources) == 0:
            await PurchaseOrderSyncBinding.filter(tenant_id=tenant_id).delete()
            return PurchaseOrderSyncBindingOut()
        sources = sources_from_upsert_body(body)
        match_key = (body.match_key_field or "order_code").strip() or "order_code"
        sync_mode = normalize_sync_mode(body.sync_mode)
        interval = normalize_schedule_interval(body.schedule_interval_minutes)
        row = await upsert_sync_binding(
            PurchaseOrderSyncBinding,
            tenant_id,
            sources=sources,
            match_key_field=match_key,
            sync_mode=sync_mode,
            schedule_interval_minutes=interval,
        )
        return self.serialize_binding(row)

    async def get_binding(self, tenant_id: int) -> PurchaseOrderSyncBindingOut:
        row = await PurchaseOrderSyncBinding.filter(tenant_id=tenant_id).first()
        return self.serialize_binding(row)

    def serialize_push_binding(self, row: Optional[PurchaseOrderSyncBinding]) -> PurchaseOrderPushBindingOut:
        from core.schemas.sync_binding_contract import DocumentPushTargetItem
        from core.services.data.sync_binding_sources import (
            push_targets_from_row,
            trigger_actions_from_row,
        )

        if not row or not isinstance(getattr(row, "push_targets", None), list):
            return PurchaseOrderPushBindingOut()
        stored = [DocumentPushTargetItem.model_validate(item) for item in push_targets_from_row(row)]
        targets = [item for item in stored if item.user_saved]
        first = targets[0] if targets else None
        return PurchaseOrderPushBindingOut(
            targets=targets,
            trigger_actions=trigger_actions_from_row(row) if targets else [],
            connection_code=first.connection_code if first else None,
            save_api_uuid=first.save_api_uuid if first else None,
            sync_mode=str(getattr(row, "sync_mode", None) or "manual_full"),
            schedule_interval_minutes=int(getattr(row, "schedule_interval_minutes", None) or 15),
            targets_configured=True,
        )

    async def get_push_binding(self, tenant_id: int) -> PurchaseOrderPushBindingOut:
        row = await PurchaseOrderSyncBinding.filter(tenant_id=tenant_id).first()
        out = self.serialize_push_binding(row)
        if (
            row
            and isinstance(getattr(row, "push_targets", None), list)
            and out.targets_configured
            and not out.targets
            and getattr(row, "push_targets", None)
        ):
            await PurchaseOrderSyncBinding.filter(id=row.id).update(push_targets=[], trigger_actions=[])
        return out

    async def upsert_push_binding(
        self,
        tenant_id: int,
        body: PurchaseOrderPushBindingUpsert,
    ) -> PurchaseOrderPushBindingOut:
        from core.services.data.sync_binding_sources import normalize_push_targets_json

        row = await PurchaseOrderSyncBinding.filter(tenant_id=tenant_id).first()
        if not row:
            row = await PurchaseOrderSyncBinding.create(tenant_id=tenant_id)
        targets = normalize_push_targets_json([item.model_dump(mode="json") for item in body.targets])
        triggers = [str(action).strip().lower() for action in body.trigger_actions if str(action).strip()]
        await PurchaseOrderSyncBinding.filter(id=row.id).update(
            push_targets=targets,
            trigger_actions=triggers,
        )
        fresh = await PurchaseOrderSyncBinding.get(id=row.id)
        return self.serialize_push_binding(fresh)

    async def sync_from_source(
        self,
        tenant_id: int,
        user_id: int,
        request: Optional[PurchaseOrderSyncFromSourceRequest] = None,
    ) -> PurchaseOrderSyncFromSourceOut:
        req = request or PurchaseOrderSyncFromSourceRequest()
        sources, match_key, binding = await resolve_sync_sources(
            PurchaseOrderSyncBinding,
            tenant_id,
            req,
            default_match_key="order_code",
        )
        binding = binding or await PurchaseOrderSyncBinding.filter(tenant_id=tenant_id).first()
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
                PurchaseOrderSyncBindingUpsert(
                    sources=req.sources,
                    match_key_field=match_key,
                    sync_mode=sync_mode,
                    schedule_interval_minutes=interval,
                ),
            )
            binding = await PurchaseOrderSyncBinding.filter(tenant_id=tenant_id).first()
        since = resolve_incremental_since(
            binding,
            sync_mode=sync_mode,
            request_incremental=req.incremental,
        )
        try:
            await emit_sync_progress("开始同步采购订单…")
            order_map: Dict[str, Dict[str, Any]] = {}
            source_errors: List[str] = []
            fetched_total = 0
            for src in sources:
                kind = str(src.get("kind") or "").strip()
                field_mapping = src.get("field_mapping") or {}
                try:
                    raw_rows = await fetch_sync_rows(
                        tenant_id,
                        source_type=kind,
                        api_uuid=str(src.get("api_uuid") or "").strip() or None,
                        dataset_uuid=str(src.get("dataset_uuid") or "").strip() or None,
                        since=since,
                        active_only=req.active_only,
                        request_body=src.get("request_body") if isinstance(src.get("request_body"), dict) else None,
                        request_params=src.get("request_params") if isinstance(src.get("request_params"), dict) else None,
                        batch_fill_path=str(src.get("batch_fill_path") or "").strip() or None,
                        batch_fill_values=(
                            [str(v).strip() for v in src.get("batch_fill_values") if str(v).strip()]
                            if isinstance(src.get("batch_fill_values"), list)
                            else None
                        ),
                    )
                    fetched_total += len(raw_rows)
                    for order in self._build_orders_from_rows(raw_rows, field_mapping, match_key):
                        key_val = self._stringify(order.get(match_key))
                        if key_val:
                            order_map[key_val] = order
                except Exception as exc:
                    source_errors.append(str(exc))
            orders = list(order_map.values())
            await emit_sync_progress(
                f"源端拉取完成 {fetched_total} 行，已组装 {len(orders)} 张采购订单，开始写入…"
            )

            from infra.models.user import User

            current_user = await User.get_or_none(id=user_id)
            if not current_user:
                raise ValidationError("同步用户不存在")
            prerequisite_errors: List[str] = []
            if not req.skip_prerequisite_syncs:
                await emit_sync_progress("正在同步前置主数据（供应商/物料）…")
                prerequisite_errors = await run_purchase_order_prerequisite_syncs(
                    tenant_id, current_user
                )
            result = await self._upsert_orders(
                tenant_id, user_id, orders, match_key, current_user
            )
            attach_sync_fetch_meta(result, fetched=fetched_total, since=since)
            if prerequisite_errors or source_errors:
                result.errors = (prerequisite_errors + source_errors + list(result.errors))[:20]
            if binding:
                if result.failed and not (result.created or result.updated):
                    await mark_binding_failure(
                        binding, "; ".join(result.errors) or "采购订单同步失败"
                    )
                else:
                    await mark_binding_success(binding)
            return result
        except Exception as exc:
            if binding:
                await mark_binding_failure(binding, str(exc))
            raise

    async def _fetch_rows_from_api(self, tenant_id: int, api_uuid: str) -> List[Dict[str, Any]]:
        return await fetch_rows_from_api(tenant_id, api_uuid)

    async def _fetch_rows_from_dataset(self, tenant_id: int, dataset_uuid: str) -> List[Dict[str, Any]]:
        return await fetch_rows_from_dataset(tenant_id, dataset_uuid)

    def _build_orders_from_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        field_mapping: Dict[str, str],
        match_key: str,
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        order_list: List[Dict[str, Any]] = []
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            mapped = self._map_row(raw, field_mapping)
            nested_items = mapped.pop("items", None)
            if isinstance(nested_items, list) and nested_items:
                key_val = self._stringify(mapped.get(match_key))
                if not key_val:
                    continue
                bucket = grouped.setdefault(
                    key_val,
                    {**{k: v for k, v in mapped.items() if not str(k).startswith(self.ITEM_PREFIX)}, "items": []},
                )
                for nested in nested_items:
                    if isinstance(nested, dict):
                        bucket["items"].append(nested)
                for field, value in mapped.items():
                    if str(field).startswith(self.ITEM_PREFIX):
                        continue
                    if bucket.get(field) in (None, "") and value not in (None, ""):
                        bucket[field] = value
                continue
            item_fields = {
                field[len(self.ITEM_PREFIX) :]: value
                for field, value in mapped.items()
                if str(field).startswith(self.ITEM_PREFIX)
            }
            header = {
                field: value
                for field, value in mapped.items()
                if not str(field).startswith(self.ITEM_PREFIX)
            }
            key_val = self._stringify(header.get(match_key))
            if not key_val:
                continue
            if item_fields:
                bucket = grouped.setdefault(key_val, {**header, "items": []})
                for field, value in header.items():
                    if bucket.get(field) in (None, "") and value not in (None, ""):
                        bucket[field] = value
                bucket["items"].append(item_fields)
            else:
                order_list.append({**header, "items": header.get("items") or []})
                grouped[key_val] = order_list[-1]
        for key_val, bucket in grouped.items():
            if key_val not in {self._stringify(o.get(match_key)) for o in order_list}:
                order_list.append(bucket)
        return order_list

    @classmethod
    def _lookup_raw_value(cls, raw: Dict[str, Any], src_key: str) -> Any:
        """精确匹配；再试摊平前缀（FPrice → FEntityFPrice / billentryFPrice）。"""
        if src_key in raw:
            return raw[src_key]
        dotted = src_key.replace(".", "_")
        if dotted != src_key and dotted in raw:
            return raw[dotted]
        for prefix in _DETAIL_FLAT_PREFIXES:
            glued = f"{prefix}{src_key}"
            if glued in raw:
                return raw[glued]
            underscored = f"{prefix}_{src_key}"
            if underscored in raw:
                return raw[underscored]
        return _MISSING

    def _map_row(self, raw: Dict[str, Any], field_mapping: Dict[str, str]) -> Dict[str, Any]:
        mapped: Dict[str, Any] = {}
        for src_key, target_key in field_mapping.items():
            if not str(src_key).strip() or not str(target_key).strip():
                continue
            value = self._lookup_raw_value(raw, str(src_key).strip())
            if value is _MISSING:
                continue
            target = str(target_key).strip()
            if target == "items" and isinstance(value, list):
                mapped["items"] = value
            else:
                mapped[target] = value
        return mapped

    async def _upsert_orders(
        self,
        tenant_id: int,
        user_id: int,
        orders: List[Dict[str, Any]],
        match_key: str,
        current_user: Any,
    ) -> PurchaseOrderSyncFromSourceOut:
        from apps.common.base_service import AppBaseService
        from infra.models.user import User

        if current_user is None:
            current_user = await User.get_or_none(id=user_id)
        if not current_user:
            raise ValidationError("同步用户不存在")

        from apps.kuaizhizao.services.purchase_service import PurchaseService

        purchase_service = PurchaseService()
        is_enabled = await purchase_service.business_config_service.check_node_enabled(
            tenant_id, "purchase_order"
        )
        if not is_enabled:
            raise BusinessLogicError("采购管理模块未启用，无法同步采购订单")

        operator_name = await AppBaseService().get_user_name(user_id)
        caches = await self._prefetch_sync_caches(tenant_id, orders, match_key)
        custom_fields_by_code = await load_custom_fields_by_code(
            tenant_id, PURCHASE_ORDER_CUSTOM_FIELD_TABLE
        )

        created = 0
        updated = 0
        skipped = 0
        failed = 0
        errors: List[str] = []
        total = len(orders)
        sync_at = resolve_business_datetime()

        for index, header in enumerate(orders, start=1):
            order_key = self._stringify(header.get(match_key))
            if not order_key:
                skipped += 1
                errors.append("存在缺少订单号的行，已跳过")
                continue
            if (
                index == 1
                or index == total
                or index % _SYNC_WRITE_PROGRESS_EVERY == 0
            ):
                await emit_sync_progress(f"正在写入采购订单 {index}/{total}：{order_key}")
            try:
                payload = self._build_purchase_order_payload_cached(header, caches)
                existing = caches["orders_by_code"].get(order_key)
                if existing:
                    if existing.status not in (
                        DocumentStatus.DRAFT.value,
                        DocumentStatus.REJECTED.value,
                    ):
                        skipped += 1
                        errors.append(f"订单 {order_key} 已审核或非草稿，已跳过")
                        continue
                    await self._sync_update_order(
                        tenant_id=tenant_id,
                        existing=existing,
                        payload=payload,
                        user_id=user_id,
                        operator_name=operator_name,
                        material_by_id=caches["material_by_id"],
                        supplier_by_id=caches["supplier_by_id"],
                        sync_at=sync_at,
                    )
                    if custom_fields_by_code:
                        await apply_mapped_custom_field_values(
                            tenant_id=tenant_id,
                            record_table=PURCHASE_ORDER_CUSTOM_FIELD_TABLE,
                            record_id=int(existing.id),
                            mapped_row=header,
                            fields_by_code=custom_fields_by_code,
                        )
                    updated += 1
                else:
                    order = await self._sync_create_order(
                        tenant_id=tenant_id,
                        payload=payload,
                        user_id=user_id,
                        operator_name=operator_name,
                        material_by_id=caches["material_by_id"],
                        supplier_by_id=caches["supplier_by_id"],
                        sync_at=sync_at,
                    )
                    caches["orders_by_code"][order_key] = order
                    if custom_fields_by_code:
                        await apply_mapped_custom_field_values(
                            tenant_id=tenant_id,
                            record_table=PURCHASE_ORDER_CUSTOM_FIELD_TABLE,
                            record_id=int(order.id),
                            mapped_row=header,
                            fields_by_code=custom_fields_by_code,
                        )
                    created += 1
            except Exception as exc:
                failed += 1
                errors.append(f"订单 {order_key or '-'}：{exc}")

        return PurchaseOrderSyncFromSourceOut(
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            errors=errors[:20],
        )

    async def _prefetch_sync_caches(
        self,
        tenant_id: int,
        orders: List[Dict[str, Any]],
        match_key: str,
    ) -> Dict[str, Any]:
        await emit_sync_progress("预加载供应商、物料与已有采购订单…")
        supplier_codes: set[str] = set()
        supplier_names: set[str] = set()
        supplier_ids: set[int] = set()
        material_codes: set[str] = set()
        order_codes: List[str] = []

        for header in orders:
            order_key = self._stringify(header.get(match_key))
            if order_key:
                order_codes.append(order_key)
            sid = header.get("supplier_id")
            if sid is not None and str(sid).strip() != "":
                try:
                    supplier_ids.add(int(sid))
                except (TypeError, ValueError):
                    pass
            code = self._stringify(header.get("supplier_code"))
            if code:
                supplier_codes.add(code)
                supplier_codes.add(code.upper())
            name = self._stringify(header.get("supplier_name"))
            if name:
                supplier_names.add(name)
            for raw_item in header.get("items") or []:
                if not isinstance(raw_item, dict):
                    continue
                mcode = self._stringify(raw_item.get("material_code"))
                if mcode:
                    material_codes.add(mcode)

        supplier_by_code: Dict[str, Supplier] = {}
        supplier_by_name: Dict[str, Supplier] = {}
        supplier_by_id: Dict[int, Supplier] = {}

        for chunk in self._chunked(sorted(supplier_codes), _LOOKUP_IN_CHUNK):
            rows = await Supplier.filter(
                tenant_id=tenant_id,
                code__in=chunk,
                deleted_at__isnull=True,
            ).all()
            for row in rows:
                supplier_by_code[row.code] = row
                supplier_by_code[row.code.upper()] = row
                supplier_by_id[int(row.id)] = row

        for chunk in self._chunked(sorted(supplier_names), _LOOKUP_IN_CHUNK):
            rows = await Supplier.filter(
                tenant_id=tenant_id,
                name__in=chunk,
                deleted_at__isnull=True,
            ).all()
            for row in rows:
                supplier_by_name[row.name] = row
                supplier_by_id[int(row.id)] = row

        for chunk in self._chunked(sorted(supplier_ids), _LOOKUP_IN_CHUNK):
            rows = await Supplier.filter(
                tenant_id=tenant_id,
                id__in=chunk,
                deleted_at__isnull=True,
            ).all()
            for row in rows:
                supplier_by_id[int(row.id)] = row
                supplier_by_code[row.code] = row
                supplier_by_code[row.code.upper()] = row

        material_by_code: Dict[str, Material] = {}
        material_by_id: Dict[int, Material] = {}
        for chunk in self._chunked(sorted(material_codes), _LOOKUP_IN_CHUNK):
            rows = await Material.filter(
                tenant_id=tenant_id,
                deleted_at__isnull=True,
            ).filter(Q(main_code__in=chunk) | Q(code__in=chunk)).all()
            for row in rows:
                material_by_id[int(row.id)] = row
                if row.main_code:
                    material_by_code[row.main_code] = row
                if row.code:
                    material_by_code[row.code] = row

        orders_by_code: Dict[str, PurchaseOrder] = {}
        for chunk in self._chunked(sorted(set(order_codes)), _LOOKUP_IN_CHUNK):
            rows = await PurchaseOrder.filter(
                tenant_id=tenant_id,
                order_code__in=chunk,
                deleted_at__isnull=True,
            ).all()
            for row in rows:
                orders_by_code[row.order_code] = row

        await emit_sync_progress(
            f"预加载完成：供应商 {len(supplier_by_id)}，物料 {len(material_by_id)}，"
            f"已有订单 {len(orders_by_code)}"
        )
        return {
            "supplier_by_code": supplier_by_code,
            "supplier_by_name": supplier_by_name,
            "supplier_by_id": supplier_by_id,
            "material_by_code": material_by_code,
            "material_by_id": material_by_id,
            "orders_by_code": orders_by_code,
        }

    @staticmethod
    def _chunked(values: List[Any], size: int) -> List[List[Any]]:
        if not values:
            return []
        return [values[i : i + size] for i in range(0, len(values), size)]

    def _build_purchase_order_payload_cached(
        self,
        header: Dict[str, Any],
        caches: Dict[str, Any],
    ) -> Dict[str, Any]:
        supplier_id, supplier_name = self._resolve_supplier_cached(header, caches)
        order_date = self._parse_date(header.get("order_date"), "order_date")
        delivery_date = self._parse_date(
            header.get("delivery_date") or order_date,
            "delivery_date",
        )
        raw_items = header.get("items") or []
        if not raw_items:
            raise ValidationError("订单须至少包含一条明细")
        item_payloads: List[PurchaseOrderItemCreate] = []
        for idx, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise ValidationError(f"订单明细第 {idx + 1} 行格式无效（须为对象）")
            item_payloads.append(
                self._build_item_payload_cached(raw_item, delivery_date, caches)
            )
        if not item_payloads:
            raise ValidationError("订单须至少包含一条有效明细")
        header_total_qty = self._optional_decimal(header.get("total_quantity"))
        if header_total_qty is None:
            header_total_qty = sum(
                (item.ordered_quantity for item in item_payloads),
                Decimal("0"),
            )
        header_total_amount = self._optional_decimal(header.get("total_amount"))
        price_type_raw = self._coerce_price_type(header.get("price_type"))
        price_type = normalize_price_type(
            price_type_raw,
            fallback=DEFAULT_PURCHASE_PRICE_TYPE,
        )
        # 未映价类且明细仅有未税单价：强制未税价类，禁止默认含税价类下把未税写入 display
        if price_type_raw is None:
            has_display = any(
                getattr(it, "display_unit_price", None) is not None for it in item_payloads
            )
            has_excl_only = any(
                getattr(it, "display_unit_price", None) is None
                and Decimal(str(it.unit_price or 0)) != 0
                for it in item_payloads
            )
            if has_excl_only and not has_display:
                price_type = "tax_exclusive"
        # 头表 tax_rate schema 为小数比率（0.13，le=1）；金蝶常见 13 或 0.13
        header_tax_rate = self._header_tax_rate_as_fraction(header.get("tax_rate"))
        header_data = {
            "order_code": self._stringify(header.get("order_code")) or None,
            "order_date": order_date,
            "delivery_date": delivery_date,
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "supplier_contact": self._optional_str(header.get("supplier_contact")),
            "supplier_phone": self._optional_str(header.get("supplier_phone")),
            "total_amount": header_total_amount,
            "total_quantity": header_total_qty,
            "price_type": price_type,
            "tax_rate": header_tax_rate,
            "buyer_name": self._optional_str(header.get("buyer_name")),
            "payment_method_code": self._optional_str(header.get("payment_method_code")),
            "settlement_terms_code": self._optional_str(header.get("settlement_terms_code")),
            "payment_terms_days": self._optional_int(header.get("payment_terms_days")),
            "notes": self._optional_str(header.get("notes")),
            "status": DocumentStatus.DRAFT.value,
        }
        create_payload = {**header_data, "items": item_payloads}
        update_payload = {
            key: value
            for key, value in header_data.items()
            if key not in ("order_code", "status")
        }
        update_payload["items"] = item_payloads
        return {"create": create_payload, "update": update_payload}

    def _build_item_payload_cached(
        self,
        raw_item: Dict[str, Any],
        default_delivery_date: date,
        caches: Dict[str, Any],
    ) -> PurchaseOrderItemCreate:
        material_code = self._stringify(raw_item.get("material_code"))
        if not material_code:
            raise ValidationError("明细缺少 material_code")
        material_name = self._stringify(raw_item.get("material_name"))
        material_id = raw_item.get("material_id")
        material_spec = self._optional_str(raw_item.get("material_spec"))
        material_unit = self._optional_str(raw_item.get("material_unit"))
        if not material_name or material_id is None:
            material = caches["material_by_code"].get(material_code)
            if not material:
                raise ValidationError(
                    f"物料编码 {material_code} 不存在，请先在物料管理配置并完成物料同步"
                )
            material_id = material.id
            material_name = material.name
            material_spec = material_spec or material.specification
            material_unit = material_unit or material.base_unit
            caches["material_by_id"][int(material.id)] = material
        qty = self._optional_decimal(raw_item.get("ordered_quantity"))
        if qty is None or qty <= 0:
            raise ValidationError(f"明细 {material_code} 数量无效")
        # 未税 item.unit_price（FPrice）与含税 item.display_unit_price（FTaxPrice）分列映射
        tax_excl = self._optional_decimal(raw_item.get("unit_price"))
        tax_incl = self._optional_decimal(raw_item.get("display_unit_price"))
        # 行税率 schema 为百分比（13）；金蝶 FEntryTaxRate 常见 13 或 0.13
        line_tax_pct = normalize_po_tax_rate_to_percent(
            self._optional_decimal(raw_item.get("tax_rate"))
        )
        if tax_incl is not None and tax_excl is not None:
            unit_for_schema = tax_excl
            display_for_schema = tax_incl
        elif tax_incl is not None:
            # 仅含税：录入含税价，写库时按含税价类拆未税
            unit_for_schema = tax_incl
            display_for_schema = tax_incl
        elif tax_excl is not None:
            # 仅未税：display 置空，写库时按未税价类落库
            unit_for_schema = tax_excl
            display_for_schema = None
        else:
            unit_for_schema = Decimal("0")
            display_for_schema = None
        # total_price 为 Create schema 必填；真实未税合计在 _build_item_rows 按价类重算覆盖
        provisional_total = (qty * unit_for_schema).quantize(Decimal("0.01"))
        item_delivery = self._parse_date(
            raw_item.get("required_date") or raw_item.get("delivery_date") or default_delivery_date,
            "delivery_date",
        )
        return PurchaseOrderItemCreate(
            material_id=int(material_id) if material_id is not None else None,
            material_code=material_code,
            material_name=material_name or material_code,
            material_spec=material_spec,
            ordered_quantity=qty,
            unit=material_unit or "",
            unit_price=unit_for_schema,
            display_unit_price=display_for_schema,
            total_price=provisional_total,
            tax_rate=line_tax_pct,
            required_date=item_delivery,
            notes=self._optional_str(raw_item.get("notes")),
        )

    def _resolve_supplier_cached(
        self,
        header: Dict[str, Any],
        caches: Dict[str, Any],
    ) -> Tuple[int, str]:
        supplier_id = header.get("supplier_id")
        if supplier_id is not None and str(supplier_id).strip() != "":
            try:
                supplier_id_int = int(supplier_id)
            except (TypeError, ValueError) as exc:
                raise ValidationError("supplier_id 无效") from exc
            supplier = caches["supplier_by_id"].get(supplier_id_int)
            if not supplier:
                raise ValidationError(f"供应商 ID {supplier_id_int} 不存在")
            return supplier.id, supplier.name

        code = self._stringify(header.get("supplier_code"))
        name = self._stringify(header.get("supplier_name"))
        if code:
            supplier = caches["supplier_by_code"].get(code) or caches["supplier_by_code"].get(
                code.upper()
            )
            if not supplier:
                raise ValidationError(
                    f"供应商编码 {code} 不存在，请先在供应商管理配置并完成供应商同步"
                )
            return supplier.id, supplier.name

        if name:
            supplier = caches["supplier_by_name"].get(name)
            if not supplier:
                raise ValidationError(
                    f"供应商名称 {name} 不存在，请先在供应商管理配置并完成供应商同步"
                )
            return supplier.id, supplier.name

        raise ValidationError("须映射 supplier_id、supplier_code 或 supplier_name 之一")

    def _build_item_rows(
        self,
        items: List[PurchaseOrderItemCreate],
        *,
        material_by_id: Dict[int, Material],
        partner_settlement_method: Optional[str],
        header_tax_rate: Any = None,
        price_type: str = DEFAULT_PURCHASE_PRICE_TYPE,
    ) -> Tuple[List[Dict[str, Any]], Decimal, Decimal]:
        from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts
        from core.utils.price_precision import quantize_business_price

        rows: List[Dict[str, Any]] = []
        total_qty = Decimal("0")
        total_amt = Decimal("0")
        pt = normalize_price_type(price_type, fallback=DEFAULT_PURCHASE_PRICE_TYPE)
        for item in items:
            material = material_by_id.get(int(item.material_id))
            if not material:
                raise ValidationError(f"物料不存在: {item.material_id}")
            qty = Decimal(str(item.ordered_quantity))
            line_tax_pct = normalize_po_tax_rate_to_percent(getattr(item, "tax_rate", None))
            if line_tax_pct <= 0:
                line_tax_pct = normalize_po_tax_rate_to_percent(header_tax_rate)
            raw_display = getattr(item, "display_unit_price", None)
            has_display = raw_display is not None and str(raw_display).strip() != ""
            unit_mapped = Decimal(str(item.unit_price or 0))
            if has_display:
                display_unit = Decimal(str(raw_display))
                # 未税+含税都映且数值不同：直接落两侧，合计用未税
                if unit_mapped > 0 and unit_mapped != display_unit:
                    unit_excl = quantize_business_price(unit_mapped, 4)
                    excl = (qty * unit_excl).quantize(Decimal("0.01"))
                else:
                    # 仅含税（或两侧同值）：按表头价类拆；默认可为含税
                    line_pt = pt
                    excl, _tax, _incl = calc_document_line_amounts(
                        qty, display_unit, line_tax_pct, line_pt, 2
                    )
                    if qty > 0:
                        unit_excl = quantize_business_price(excl / qty, 4)
                    else:
                        unit_excl = (
                            quantize_business_price(
                                display_unit
                                / (Decimal("1") + line_tax_pct / Decimal("100")),
                                4,
                            )
                            if line_pt == "tax_inclusive"
                            and line_tax_pct > 0
                            and display_unit > 0
                            else quantize_business_price(display_unit, 4)
                        )
            else:
                # 仅未税：display 保持空，由详情按税率推含税；禁止把未税冒充 display_unit_price
                excl, _tax, _incl = calc_document_line_amounts(
                    qty, unit_mapped, line_tax_pct, "tax_exclusive", 2
                )
                unit_excl = (
                    quantize_business_price(excl / qty, 4)
                    if qty > 0
                    else quantize_business_price(unit_mapped, 4)
                )
                display_unit = None
            settlement_status = derive_price_settlement_status(
                unit_price=unit_excl,
                partner_settlement_method=partner_settlement_method,
                explicit_status=getattr(item, "price_settlement_status", None),
            )
            provisional_price = derive_provisional_unit_price(
                unit_price=unit_excl,
                reference_price=getattr(item, "provisional_unit_price", None),
                settlement_status=settlement_status,
            )
            rows.append(
                {
                    "material_id": int(item.material_id),
                    "material_code": (item.material_code or material.main_code or material.code or "")[
                        :50
                    ],
                    "material_name": (item.material_name or material.name or "")[:200],
                    "material_spec": item.material_spec or material.specification,
                    "ordered_quantity": qty,
                    "unit": item.unit or material.base_unit or "",
                    "unit_price": unit_excl,
                    "display_unit_price": display_unit,
                    "total_price": excl,
                    "tax_rate": line_tax_pct,
                    "received_quantity": Decimal("0"),
                    "outstanding_quantity": qty,
                    "required_date": item.required_date,
                    "notes": item.notes,
                    "price_settlement_status": settlement_status,
                    "provisional_unit_price": provisional_price,
                    "inspection_required": bool(
                        getattr(item, "inspection_required", True)
                    ),
                }
            )
            total_qty += qty
            total_amt += excl
        return rows, total_qty, total_amt

    async def _sync_create_order(
        self,
        *,
        tenant_id: int,
        payload: Dict[str, Any],
        user_id: int,
        operator_name: str,
        material_by_id: Dict[int, Material],
        supplier_by_id: Dict[int, Supplier],
        sync_at: datetime,
    ) -> PurchaseOrder:
        create_data = PurchaseOrderCreate(**payload["create"])
        if not create_data.order_code:
            raise ValidationError("同步创建须带订单号")

        order_dict = create_data.model_dump(exclude=_PURCHASE_ORDER_SYNC_HEADER_EXCLUDE)
        order_dict["status"] = DocumentStatus.DRAFT.value
        order_dict["review_status"] = ReviewStatus.PENDING.value
        order_dict["created_by"] = user_id
        order_dict["created_by_name"] = operator_name
        order_dict["updated_by"] = user_id
        order_dict["updated_by_name"] = operator_name
        order_dict["external_sync_at"] = sync_at
        order_dict["order_type"] = normalize_purchase_order_type(order_dict.get("order_type"))
        order_dict["price_type"] = normalize_price_type(
            order_dict.get("price_type"),
            fallback=DEFAULT_PURCHASE_PRICE_TYPE,
        )

        supplier = supplier_by_id.get(int(order_dict["supplier_id"]))
        partner_settlement_method = (
            partner_settlement_terms_for_pricing(supplier) if supplier else None
        )
        if not order_dict.get("buyer_id") and supplier and getattr(supplier, "buyer_id", None):
            order_dict["buyer_id"] = supplier.buyer_id
            order_dict["buyer_name"] = supplier.buyer_name
        if not order_dict.get("buyer_id"):
            order_dict["buyer_id"] = user_id
            if not order_dict.get("buyer_name"):
                order_dict["buyer_name"] = operator_name

        item_rows, total_qty, total_amt = self._build_item_rows(
            create_data.items,
            material_by_id=material_by_id,
            partner_settlement_method=partner_settlement_method,
            header_tax_rate=create_data.tax_rate,
            price_type=str(order_dict.get("price_type") or DEFAULT_PURCHASE_PRICE_TYPE),
        )
        order_dict["total_quantity"] = total_qty
        order_dict["total_amount"] = total_amt

        order_dict["payable_recognition"] = await ensure_payable_recognition_on_create(
            tenant_id,
            order_dict.get("supplier_id"),
            order_dict.get("payable_recognition"),
        )

        async with in_transaction():
            order = await PurchaseOrder.create(tenant_id=tenant_id, **order_dict)
            await PurchaseOrderItem.bulk_create(
                [
                    PurchaseOrderItem(
                        tenant_id=tenant_id,
                        order_id=order.id,
                        material_id=row["material_id"],
                        material_code=row["material_code"],
                        material_name=row["material_name"],
                        material_spec=row["material_spec"],
                        ordered_quantity=row["ordered_quantity"],
                        unit=row["unit"],
                        unit_price=row["unit_price"],
                        display_unit_price=row["display_unit_price"],
                        total_price=row["total_price"],
                        tax_rate=row["tax_rate"],
                        received_quantity=row["received_quantity"],
                        outstanding_quantity=row["outstanding_quantity"],
                        required_date=row["required_date"],
                        notes=row["notes"],
                        price_settlement_status=row["price_settlement_status"],
                        provisional_unit_price=row["provisional_unit_price"],
                        inspection_required=row["inspection_required"],
                        created_by=user_id,
                        updated_by=user_id,
                    )
                    for row in item_rows
                ]
            )
            await sync_purchase_order_header_amounts(
                tenant_id, int(order.id), order=order, persist=True
            )
        return order

    async def _sync_update_order(
        self,
        *,
        tenant_id: int,
        existing: PurchaseOrder,
        payload: Dict[str, Any],
        user_id: int,
        operator_name: str,
        material_by_id: Dict[int, Material],
        supplier_by_id: Dict[int, Supplier],
        sync_at: datetime,
    ) -> None:
        update_data = PurchaseOrderUpdate(**payload["update"])
        upd = update_data.model_dump(
            exclude_unset=True, exclude=_PURCHASE_ORDER_SYNC_HEADER_EXCLUDE
        )
        upd.pop("status", None)
        upd.pop("review_status", None)
        upd["updated_by"] = user_id
        upd["updated_by_name"] = operator_name
        upd["external_sync_at"] = sync_at
        if "order_type" in upd:
            upd["order_type"] = normalize_purchase_order_type(upd.get("order_type"))
        if "price_type" in upd:
            upd["price_type"] = normalize_price_type(
                upd.get("price_type"),
                fallback=DEFAULT_PURCHASE_PRICE_TYPE,
            )

        items = update_data.items or []
        if not items:
            raise ValidationError("订单须至少包含一条明细")

        supplier_id = upd.get("supplier_id", existing.supplier_id)
        supplier = supplier_by_id.get(int(supplier_id)) if supplier_id else None
        partner_settlement_method = (
            partner_settlement_terms_for_pricing(supplier) if supplier else None
        )
        if not upd.get("buyer_id") and not existing.buyer_id and supplier and getattr(
            supplier, "buyer_id", None
        ):
            upd["buyer_id"] = supplier.buyer_id
            upd["buyer_name"] = supplier.buyer_name

        effective_price_type = str(
            upd.get("price_type")
            or getattr(existing, "price_type", None)
            or DEFAULT_PURCHASE_PRICE_TYPE
        )
        item_rows, total_qty, total_amt = self._build_item_rows(
            items,
            material_by_id=material_by_id,
            partner_settlement_method=partner_settlement_method,
            header_tax_rate=upd.get("tax_rate", existing.tax_rate),
            price_type=effective_price_type,
        )
        upd["total_quantity"] = total_qty
        upd["total_amount"] = total_amt

        async with in_transaction():
            if upd:
                await PurchaseOrder.filter(id=existing.id).update(**upd)
            await PurchaseOrderItem.filter(
                tenant_id=tenant_id, order_id=existing.id
            ).delete()
            await PurchaseOrderItem.bulk_create(
                [
                    PurchaseOrderItem(
                        tenant_id=tenant_id,
                        order_id=existing.id,
                        material_id=row["material_id"],
                        material_code=row["material_code"],
                        material_name=row["material_name"],
                        material_spec=row["material_spec"],
                        ordered_quantity=row["ordered_quantity"],
                        unit=row["unit"],
                        unit_price=row["unit_price"],
                        display_unit_price=row["display_unit_price"],
                        total_price=row["total_price"],
                        tax_rate=row["tax_rate"],
                        received_quantity=row["received_quantity"],
                        outstanding_quantity=row["outstanding_quantity"],
                        required_date=row["required_date"],
                        notes=row["notes"],
                        price_settlement_status=row["price_settlement_status"],
                        provisional_unit_price=row["provisional_unit_price"],
                        inspection_required=row["inspection_required"],
                        created_by=user_id,
                        updated_by=user_id,
                    )
                    for row in item_rows
                ]
            )
            refreshed = await PurchaseOrder.get(id=existing.id)
            await sync_purchase_order_header_amounts(
                tenant_id, int(existing.id), order=refreshed, persist=True
            )
            existing.external_sync_at = sync_at

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _optional_str(value: Any) -> Optional[str]:
        text = PurchaseOrderSyncService._stringify(value)
        return text or None

    @staticmethod
    def _optional_decimal(value: Any, *, field_label: str = "数值") -> Optional[Decimal]:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError(f"{field_label}无效：{value}") from exc

    @staticmethod
    def _optional_int(value: Any, *, field_label: str = "整数") -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(Decimal(str(value)))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValidationError(f"{field_label}无效：{value}") from exc

    @staticmethod
    def _coerce_price_type(value: Any) -> Optional[str]:
        """金蝶含税标记 / 本系统价类码 → tax_inclusive | tax_exclusive。"""
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return "tax_inclusive" if value else "tax_exclusive"
        text = str(value).strip().lower()
        if text in ("tax_inclusive", "tax_exclusive"):
            return text
        if text in ("1", "true", "yes", "y", "含税", "include", "included"):
            return "tax_inclusive"
        if text in ("0", "false", "no", "n", "未税", "不含税", "exclude", "excluded"):
            return "tax_exclusive"
        return text

    @staticmethod
    def _header_tax_rate_as_fraction(value: Any) -> Decimal:
        """采购订单头 tax_rate 存小数比率（0.13）；源端 13 / 0.13 均可。"""
        raw = PurchaseOrderSyncService._optional_decimal(value)
        if raw is None:
            return Decimal("0")
        pct = normalize_po_tax_rate_to_percent(raw)
        if pct <= 0:
            return Decimal("0")
        return (pct / Decimal("100")).quantize(Decimal("0.000001"))

    @staticmethod
    def _parse_date(value: Any, field_name: str) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        text = PurchaseOrderSyncService._stringify(value)
        if not text:
            raise ValidationError(f"{field_name} 不能为空")
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(text[:10], fmt).date()
            except ValueError:
                continue
        if "T" in text:
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
            except ValueError:
                pass
        raise ValidationError(f"{field_name} 格式无效：{text}")
