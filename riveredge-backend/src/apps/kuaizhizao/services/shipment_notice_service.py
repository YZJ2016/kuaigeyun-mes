"""
发货通知单服务模块

销售通知仓库发货，不直接动库存。来源为销售订单。

Author: RiverEdge Team
Date: 2026-02-22
"""

import logging
from collections import defaultdict
from typing import List, Optional, Dict, Any, Union
from datetime import date, datetime, time
from decimal import Decimal
from tortoise.transactions import in_transaction
from tortoise.expressions import Q

from apps.common.base_service import AppBaseService

logger = logging.getLogger(__name__)
from apps.kuaizhizao.models.shipment_notice import ShipmentNotice
from apps.kuaizhizao.models.shipment_notice_item import ShipmentNoticeItem
from apps.kuaizhizao.models.sales_order_item import SalesOrderItem
from apps.kuaizhizao.models.sales_order import SalesOrder
from apps.kuaizhizao.schemas.shipment_notice import (
    ShipmentNoticeCreate,
    ShipmentNoticeUpdate,
    ShipmentNoticeNotify,
    ShipmentNoticeResponse,
    ShipmentNoticeListResponse,
    ShipmentNoticeWithItemsResponse,
    ShipmentNoticeItemCreate,
    ShipmentNoticeItemResponse,
)
from infra.exceptions.exceptions import NotFoundError, BusinessLogicError, ValidationError
from apps.kuaizhizao.services.document_action_policy.print_unaudited_gate import (
    push_allow_print_unaudited,
)
from apps.kuaizhizao.services.document_action_policy.shipment_notice import (
    assert_shipment_notice_capability,
    derive_shipment_notice_capabilities,
    shipment_notice_review_approved,
)
from apps.kuaizhizao.services.document_action_policy.enricher import (
    enrich_shipment_notice_capabilities_on_response,
    enrich_shipment_notice_list_capabilities,
)
from infra.services.business_config_service import BusinessConfigService
from apps.kuaizhizao.utils.inventory_helper import get_material_available_quantity
from apps.kuaizhizao.services.kuaizhizao_data_scope import (
    apply_sales_order_child_list_scope,
    assert_sales_order_child_row_visible,
)
from core.services.approval.audit_record_enricher import enrich_items
from core.utils.timezone_utils import resolve_business_datetime, today_site_str
from infra.models.user import User

SHIPMENT_NOTICE_SORTABLE_FIELDS = frozenset({
    "notice_code",
    "sales_order_code",
    "customer_name",
    "warehouse_name",
    "planned_ship_date",
    "notified_at",
    "total_quantity",
    "total_amount",
    "status",
    "created_at",
    "updated_at",
})


async def _resolve_warehouse_name_by_id(
    tenant_id: int,
    warehouse_id: int,
    preferred_name: Optional[str] = None,
) -> str:
    preferred = str(preferred_name or "").strip()
    if preferred:
        return preferred
    if warehouse_id is None:
        raise ValidationError("缺少仓库ID，无法解析仓库名称")
    from apps.master_data.models.warehouse import Warehouse

    wh = await Warehouse.get_or_none(
        tenant_id=tenant_id,
        id=int(warehouse_id),
        is_active=True,
        deleted_at__isnull=True,
    )
    if not wh:
        raise ValidationError(f"仓库不存在或未启用: {warehouse_id}")
    name = str(getattr(wh, "name", "") or "").strip()
    if not name:
        raise ValidationError(f"仓库名称未配置: {warehouse_id}")
    return name


def _coerce_int_id_map(raw: Optional[Dict[Any, Any]]) -> Dict[int, int]:
    """JSON 对象键为 str：规范化为 {item_id: int_id}。"""
    if not raw:
        return {}
    out: Dict[int, int] = {}
    for key, value in raw.items():
        try:
            item_id = int(key)
            target_id = int(value)
        except (TypeError, ValueError):
            continue
        if item_id > 0 and target_id > 0:
            out[item_id] = target_id
    return out


def _coerce_str_id_map(raw: Optional[Dict[Any, Any]]) -> Dict[int, str]:
    if not raw:
        return {}
    out: Dict[int, str] = {}
    for key, value in raw.items():
        try:
            item_id = int(key)
        except (TypeError, ValueError):
            continue
        text = str(value or "").strip()
        if item_id > 0 and text:
            out[item_id] = text
    return out


def _is_whole_warehouse_placeholder(location: Any) -> bool:
    """系统占位「整仓」：名称是整仓，且未挂库区（直挂本仓）。"""
    from apps.master_data.services.warehouse_service import WHOLE_WAREHOUSE_LOCATION_NAME

    name = str(getattr(location, "name", None) or "").strip()
    return (
        name == WHOLE_WAREHOUSE_LOCATION_NAME
        and getattr(location, "storage_area_id", None) is None
    )


async def _warehouse_has_real_storage_location(tenant_id: int, warehouse_id: int) -> bool:
    """未传库位时，仓库是否已有真实货位。仅「整仓」占位不算，需再查本仓其他库位。"""
    from apps.master_data.models.warehouse import StorageLocation
    from apps.master_data.services.warehouse_service import WarehouseService

    found_id, _found_code = await WarehouseService.find_first_storage_location_for_warehouse(
        tenant_id, warehouse_id
    )
    if found_id is None:
        return False
    found = await StorageLocation.get_or_none(
        tenant_id=tenant_id,
        id=int(found_id),
        deleted_at__isnull=True,
    )
    if found is None:
        return False
    if not _is_whole_warehouse_placeholder(found):
        return True
    rows = await StorageLocation.filter(
        tenant_id=tenant_id,
        warehouse_id=int(warehouse_id),
        deleted_at__isnull=True,
        is_active=True,
    )
    for loc in rows:
        if int(getattr(loc, "id", 0) or 0) == int(found_id):
            continue
        if not _is_whole_warehouse_placeholder(loc):
            return True
    return False


class ShipmentNoticeService(AppBaseService[ShipmentNotice]):
    """发货通知单服务"""

    def __init__(self):
        super().__init__(ShipmentNotice)
        self.business_config_service = BusinessConfigService()

    @staticmethod
    def _collect_notice_delivery_ids(notice: ShipmentNotice) -> List[int]:
        ids: List[int] = []
        primary = getattr(notice, "sales_delivery_id", None)
        if primary:
            ids.append(int(primary))
        related = getattr(notice, "related_sales_delivery_ids", None) or []
        if isinstance(related, list):
            for entry in related:
                if isinstance(entry, dict) and entry.get("id") is not None:
                    ids.append(int(entry["id"]))
                elif isinstance(entry, int):
                    ids.append(int(entry))
        return list(dict.fromkeys(ids))

    @staticmethod
    def _pushable_items_have_warehouses(notice_items: List[ShipmentNoticeItem]) -> bool:
        has_positive = False
        for item in notice_items:
            qty = Decimal(str(getattr(item, "notice_quantity", 0) or 0))
            if qty <= Decimal("0"):
                continue
            has_positive = True
            if not getattr(item, "warehouse_id", None):
                return False
        return has_positive

    async def _notice_delivery_withdrawable(self, tenant_id: int, notice: ShipmentNotice) -> bool:
        delivery_ids = self._collect_notice_delivery_ids(notice)
        if not delivery_ids:
            return True
        from apps.kuaizhizao.models.sales_delivery import SalesDelivery

        deliveries = await SalesDelivery.filter(
            tenant_id=tenant_id, id__in=delivery_ids, deleted_at__isnull=True
        ).all()
        status_by_id = {int(d.id): str(d.status or "").strip() for d in deliveries}
        for did in delivery_ids:
            st = status_by_id.get(did, "")
            if st and st not in ("草稿", "draft", "待出库"):
                return False
        return True

    async def _delivery_withdrawable_by_notice_id(
        self, tenant_id: int, notices: List[ShipmentNotice]
    ) -> dict[int, bool]:
        result: dict[int, bool] = {}
        delivery_ids_by_notice: dict[int, List[int]] = {}
        all_delivery_ids: set[int] = set()
        for n in notices:
            if str(n.status or "").strip() != "已通知":
                continue
            ids = self._collect_notice_delivery_ids(n)
            if not ids:
                result[int(n.id)] = True
            else:
                delivery_ids_by_notice[int(n.id)] = ids
                all_delivery_ids.update(ids)

        if not all_delivery_ids:
            return result

        from apps.kuaizhizao.models.sales_delivery import SalesDelivery

        status_by_id: dict[int, str] = {}
        deliveries = await SalesDelivery.filter(
            tenant_id=tenant_id, id__in=list(all_delivery_ids), deleted_at__isnull=True
        ).all()
        for d in deliveries:
            status_by_id[int(d.id)] = str(d.status or "").strip()

        for nid, dids in delivery_ids_by_notice.items():
            withdrawable = True
            for did in dids:
                st = status_by_id.get(did, "")
                if st and st not in ("草稿", "draft", "待出库"):
                    withdrawable = False
                    break
            result[nid] = withdrawable
        return result

    async def _notice_has_items_map(self, tenant_id: int, notice_ids: List[int]) -> dict[int, bool]:
        if not notice_ids:
            return {}
        from tortoise.functions import Count

        rows = await ShipmentNoticeItem.filter(
            tenant_id=tenant_id,
            notice_id__in=notice_ids,
        ).annotate(cnt=Count("id")).group_by("notice_id").values("notice_id", "cnt")
        return {int(r["notice_id"]): int(r["cnt"] or 0) > 0 for r in rows}

    async def _enrich_notice_response(
        self,
        tenant_id: int,
        notice: ShipmentNotice,
        response: ShipmentNoticeResponse | ShipmentNoticeWithItemsResponse,
    ) -> ShipmentNoticeResponse | ShipmentNoticeWithItemsResponse:
        item_count = await ShipmentNoticeItem.filter(tenant_id=tenant_id, notice_id=notice.id).count()
        delivery_withdrawable = await self._notice_delivery_withdrawable(tenant_id, notice)
        allow_print = await self.business_config_service.get_allow_print_unaudited(tenant_id)
        with push_allow_print_unaudited(allow_print):
            enriched = enrich_shipment_notice_capabilities_on_response(
                notice,
                response,
                has_items=item_count > 0,
                has_warehouse=getattr(notice, "warehouse_id", None) is not None,
                delivery_withdrawable=delivery_withdrawable,
            )
        from core.services.approval.audit_record_enricher import enrich_record

        return await enrich_record(tenant_id, "shipment_notice", enriched)

    async def _validate_not_overdelivery_on_notify(
        self,
        *,
        tenant_id: int,
        notice: ShipmentNotice,
    ) -> None:
        """
        通知仓库前超发校验：与下推/取单同一口径（欠发 − 其他通知占用 − 待出库占用）。
        """
        notice_items = await ShipmentNoticeItem.filter(
            tenant_id=tenant_id,
            notice_id=notice.id,
        ).all()
        if not notice_items:
            raise BusinessLogicError("发货通知单无明细，无法通知仓库")

        order_items = await SalesOrderItem.filter(
            tenant_id=tenant_id,
            sales_order_id=notice.sales_order_id,
        ).all()
        if not order_items:
            raise BusinessLogicError("销售订单明细不存在，无法校验发货通知数量")

        from apps.kuaizhizao.utils.sales_order_push_qty import get_pushable_qty_for_order_items

        pushable_by_item = await get_pushable_qty_for_order_items(
            tenant_id,
            int(notice.sales_order_id),
            order_items,
            exclude_notice_id=int(notice.id),
        )
        from apps.kuaizhizao.utils.over_qty_tolerance import (
            OverQtyToleranceResolver,
            max_pushable_with_issue_tolerance,
        )

        tolerance_resolver = OverQtyToleranceResolver(tenant_id)
        order_item_by_id = {int(it.id): it for it in order_items}

        for n_item in notice_items:
            qty = Decimal(str(n_item.notice_quantity or 0))
            if qty <= Decimal("0"):
                raise BusinessLogicError("发货通知数量必须大于0")

            so_item_id = getattr(n_item, "sales_order_item_id", None)
            if so_item_id is None:
                continue
            so_item_id = int(so_item_id)
            so_item = order_item_by_id.get(so_item_id)
            if not so_item:
                raise BusinessLogicError(f"发货通知明细缺少有效的订单行关联: {so_item_id}")

            base_qty = pushable_by_item.get(so_item_id, Decimal("0"))
            available_qty, _ = await max_pushable_with_issue_tolerance(
                tenant_id,
                material_id=int(so_item.material_id),
                base_pushable=base_qty,
                resolver=tolerance_resolver,
            )
            if qty > available_qty:
                material_label = (
                    getattr(so_item, "material_code", None)
                    or getattr(so_item, "material_name", None)
                    or str(so_item_id)
                )
                raise BusinessLogicError(
                    f"物料 {material_label} 通知数量 {qty} 超过可通知欠发量 {available_qty}"
                )

    @staticmethod
    def _format_notify_inventory_qty(value: Union[Decimal, float, int, str, None]) -> str:
        """提示用数量：去掉多余尾零，避免 246.000000。"""
        try:
            d = Decimal(str(value if value is not None else 0))
        except Exception:
            return "0"
        text = format(d.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    async def _build_notify_inventory_shortfall_messages(
        self,
        *,
        tenant_id: int,
        exclude_notice_id: int,
        required_by_wh_material: dict[tuple[int, int], Decimal],
        labels_by_wh_material: dict[tuple[int, int], str],
        warehouse_names_by_id: Optional[Dict[int, str]] = None,
    ) -> List[str]:
        """
        通知仓库库存校验文案：在库 / 其它已通知预占（单号明细）/ 可用 / 本次通知。
        无不足时返回空列表。
        """
        if not required_by_wh_material:
            return []

        reserved_notice_ids = await ShipmentNotice.filter(
            tenant_id=tenant_id,
            status="已通知",
            deleted_at__isnull=True,
        ).exclude(id=exclude_notice_id).values_list("id", flat=True)

        reserved_qty_by_key: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
        reserved_by_key_notice: dict[tuple[int, int], dict[str, Decimal]] = defaultdict(
            lambda: defaultdict(lambda: Decimal("0"))
        )
        if reserved_notice_ids:
            # 明细表无 deleted_at；未删除头单已由 reserved_notice_ids 约束
            reserved_items = await ShipmentNoticeItem.filter(
                tenant_id=tenant_id,
                notice_id__in=list(reserved_notice_ids),
            ).all()
            reserved_notices = await ShipmentNotice.filter(
                tenant_id=tenant_id,
                id__in=list(reserved_notice_ids),
            ).all()
            header_wh_by_notice = {int(n.id): getattr(n, "warehouse_id", None) for n in reserved_notices}
            notice_code_by_id = {
                int(n.id): str(getattr(n, "notice_code", None) or "").strip() or f"#{int(n.id)}"
                for n in reserved_notices
            }
            for rit in reserved_items:
                material_id = getattr(rit, "material_id", None)
                if not material_id:
                    continue
                qty = Decimal(str(getattr(rit, "notice_quantity", 0) or 0))
                if qty <= Decimal("0"):
                    continue
                wh_id = getattr(rit, "warehouse_id", None) or header_wh_by_notice.get(int(rit.notice_id))
                if wh_id is None:
                    continue
                key = (int(wh_id), int(material_id))
                code = notice_code_by_id.get(int(rit.notice_id), f"#{int(rit.notice_id)}")
                reserved_qty_by_key[key] += qty
                reserved_by_key_notice[key][code] += qty

        messages: List[str] = []
        wh_names = warehouse_names_by_id or {}
        for key, required_qty in required_by_wh_material.items():
            wh_id, material_id = key
            on_hand = Decimal(
                str(
                    await get_material_available_quantity(
                        tenant_id=tenant_id,
                        material_id=material_id,
                        warehouse_id=wh_id,
                    )
                    or 0
                )
            )
            reserved_qty = reserved_qty_by_key.get(key, Decimal("0"))
            effective_qty = max(Decimal("0"), on_hand - reserved_qty)
            if required_qty <= effective_qty:
                continue

            label = labels_by_wh_material.get(key, str(material_id))
            wh_label = str(wh_names.get(int(wh_id), "") or "").strip()
            material_part = f"物料 {label}" + (f"（{wh_label}）" if wh_label else "")
            fmt = self._format_notify_inventory_qty
            if reserved_qty > 0:
                occ_parts = [
                    f"{code} 预占 {fmt(qty)}"
                    for code, qty in sorted(
                        reserved_by_key_notice.get(key, {}).items(),
                        key=lambda x: x[0],
                    )
                ]
                occ_detail = "；".join(occ_parts)
                messages.append(
                    f"{material_part}：通知 {fmt(required_qty)}，在库 {fmt(on_hand)}，"
                    f"其它已通知预占 {fmt(reserved_qty)}（{occ_detail}），"
                    f"可用 {fmt(effective_qty)}，库存不足"
                )
            else:
                messages.append(
                    f"{material_part}：通知 {fmt(required_qty)}，在库 {fmt(on_hand)}，"
                    f"无其它已通知预占，可用 {fmt(effective_qty)}，库存不足"
                )
        return messages

    async def _validate_inventory_reservation_on_notify(
        self,
        *,
        tenant_id: int,
        notice: ShipmentNotice,
    ) -> None:
        """
        P1-S-011: 通知仓库前校验库存预占量。
        按行出库仓库 + 物料汇总需求，扣除其他「已通知」单据同仓预占后再判断。
        """
        # 明细表无 deleted_at 字段，勿传 deleted_at__isnull（会 Unknown filter param）
        notice_items = await ShipmentNoticeItem.filter(
            tenant_id=tenant_id,
            notice_id=notice.id,
        ).all()
        if not notice_items:
            return

        required_by_wh_material: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
        labels_by_wh_material: dict[tuple[int, int], str] = {}
        warehouse_names_by_id: Dict[int, str] = {}
        for item in notice_items:
            material_id = getattr(item, "material_id", None)
            if not material_id:
                continue
            qty = Decimal(str(getattr(item, "notice_quantity", 0) or 0))
            if qty <= Decimal("0"):
                continue
            warehouse_id = getattr(item, "warehouse_id", None) or getattr(notice, "warehouse_id", None)
            if warehouse_id is None:
                label = (
                    getattr(item, "material_code", None)
                    or getattr(item, "material_name", None)
                    or str(material_id)
                )
                raise ValidationError(f"请为物料 {label} 指定出库仓库")
            key = (int(warehouse_id), int(material_id))
            required_by_wh_material[key] += qty
            labels_by_wh_material[key] = (
                getattr(item, "material_code", None)
                or getattr(item, "material_name", None)
                or str(material_id)
            )
            wh_name = (
                str(getattr(item, "warehouse_name", None) or "").strip()
                or str(getattr(notice, "warehouse_name", None) or "").strip()
            )
            if wh_name and int(warehouse_id) not in warehouse_names_by_id:
                warehouse_names_by_id[int(warehouse_id)] = wh_name

        messages = await self._build_notify_inventory_shortfall_messages(
            tenant_id=tenant_id,
            exclude_notice_id=int(notice.id),
            required_by_wh_material=required_by_wh_material,
            labels_by_wh_material=labels_by_wh_material,
            warehouse_names_by_id=warehouse_names_by_id,
        )
        if messages:
            raise BusinessLogicError("；".join(messages))

    @staticmethod
    def _shipment_notice_line_amount(
        qty: Decimal,
        unit_price: Any,
        *,
        explicit_total: Any = None,
        sales_order_item: Any = None,
        price_type: Optional[str] = None,
    ) -> Decimal:
        if explicit_total is not None:
            from apps.kuaizhizao.utils.document_amount_write import resolve_simple_line_total

            return resolve_simple_line_total(qty, unit_price, explicit_total)
        if sales_order_item is not None and price_type is not None:
            from apps.kuaizhizao.constants.price_type import normalize_price_type
            from apps.kuaizhizao.utils.sales_price_amount import stored_sales_line_amount

            return stored_sales_line_amount(
                qty,
                unit_price,
                getattr(sales_order_item, "tax_rate", 0) or 0,
                normalize_price_type(price_type),
                is_gift=bool(getattr(sales_order_item, "is_gift", False)),
            )
        from apps.kuaizhizao.utils.document_amount_write import line_total_qty_unit_price

        return line_total_qty_unit_price(qty, unit_price)

    async def create_shipment_notice(
        self,
        tenant_id: int,
        notice_data: ShipmentNoticeCreate,
        created_by: int
    ) -> ShipmentNoticeResponse:
        """创建发货通知单"""
        is_enabled = await self.business_config_service.check_node_enabled(tenant_id, "shipment_notice")
        if not is_enabled:
            raise BusinessLogicError("发货通知单节点未启用，无法创建发货通知单")
        source_order = await SalesOrder.get_or_none(
            tenant_id=tenant_id,
            id=notice_data.sales_order_id,
            deleted_at__isnull=True,
        )
        if not source_order:
            raise BusinessLogicError("销售订单不存在或已删除，无法创建发货通知单")
        existed = await ShipmentNotice.get_or_none(
            tenant_id=tenant_id,
            sales_order_id=notice_data.sales_order_id,
            deleted_at__isnull=True,
        )
        if existed:
            raise BusinessLogicError(
                f"该销售订单已创建发货通知单（{existed.notice_code}），请勿重复创建"
            )
        from apps.kuaizhizao.utils.sales_order_currency_carry import currency_fields_for_sales_doc

        fields_set = getattr(notice_data, "model_fields_set", set()) or set()
        so_currency = currency_fields_for_sales_doc(
            source_order,
            override_code=(
                getattr(notice_data, "currency_code", None)
                if "currency_code" in fields_set
                else None
            ),
            override_rate=(
                getattr(notice_data, "exchange_rate", None)
                if "exchange_rate" in fields_set
                else None
            ),
        )
        async with in_transaction():
            code = notice_data.notice_code
            if not code:
                code = await self.generate_code(tenant_id, "SHIPMENT_NOTICE_CODE", prefix="SN")

            dump = notice_data.model_dump(exclude_unset=True, exclude={"items", "notice_code"})
            dump.update(so_currency)
            audit_required = await self.business_config_service.check_audit_required(
                tenant_id, "shipment_notice"
            )
            if audit_required:
                dump["status"] = "待审核"
                dump["review_status"] = "待审核"
            else:
                dump["status"] = "待发货"
                dump["review_status"] = "已通过"

            user_info = await self.get_user_info(created_by)
            notice = await ShipmentNotice.create(
                tenant_id=tenant_id,
                notice_code=code,
                **dump,
                created_by=created_by,
                created_by_name=user_info["name"],
                updated_by=created_by,
                updated_by_name=user_info["name"],
            )

            items = getattr(notice_data, "items", None) or []
            total_quantity = Decimal(0)
            total_amount = Decimal(0)
            from apps.kuaizhizao.utils.document_line_material_snapshot import (
                enrich_line_dicts_with_partner_snapshots,
                snapshot_kwargs_for_orm,
            )

            item_rows = [it.model_dump(exclude_unset=True) for it in items]
            item_rows = await enrich_line_dicts_with_partner_snapshots(
                tenant_id,
                partner_type="customer",
                partner_id=int(getattr(notice, "customer_id", 0) or 0) or None,
                lines=item_rows,
            )
            price_type = None
            so_item_by_id: Dict[int, SalesOrderItem] = {}
            so_id = int(getattr(notice_data, "sales_order_id", 0) or getattr(notice, "sales_order_id", 0) or 0)
            if so_id > 0:
                sales_order = await SalesOrder.get_or_none(tenant_id=tenant_id, id=so_id)
                if sales_order is not None:
                    from apps.kuaizhizao.constants.price_type import normalize_price_type

                    price_type = normalize_price_type(getattr(sales_order, "price_type", None))
                so_ids = {
                    int(getattr(it, "sales_order_item_id", 0) or 0)
                    for it in items
                    if int(getattr(it, "sales_order_item_id", 0) or 0) > 0
                }
                if so_ids:
                    for soi in await SalesOrderItem.filter(tenant_id=tenant_id, id__in=list(so_ids)):
                        so_item_by_id[int(soi.id)] = soi
            for item_data, row in zip(items, item_rows):
                qty = Decimal(str(item_data.notice_quantity))
                so_line_id = int(getattr(item_data, "sales_order_item_id", 0) or 0)
                so_item = so_item_by_id.get(so_line_id) if so_line_id > 0 else None
                amt = self._shipment_notice_line_amount(
                    qty,
                    item_data.unit_price,
                    explicit_total=item_data.total_amount,
                    sales_order_item=so_item,
                    price_type=price_type,
                )
                dump = item_data.model_dump(
                    exclude_unset=True,
                    exclude={"notice_quantity", "unit_price", "total_amount"},
                )
                spec = row.get("material_spec") or dump.get("material_spec")
                await ShipmentNoticeItem.create(
                    tenant_id=tenant_id,
                    notice_id=notice.id,
                    notice_quantity=qty,
                    unit_price=Decimal(str(item_data.unit_price or 0)),
                    total_amount=amt,
                    **dump,
                    material_spec=spec,
                    **snapshot_kwargs_for_orm(row),
                )
                total_quantity += qty
                total_amount += amt

            await ShipmentNotice.filter(tenant_id=tenant_id, id=notice.id).update(
                total_quantity=total_quantity,
                total_amount=total_amount
            )
            notice = await ShipmentNotice.get(tenant_id=tenant_id, id=notice.id)
            if audit_required and (notice.status or "").strip() == "待审核":
                from core.services.approval.approval_instance_service import ApprovalInstanceService

                instance = await ApprovalInstanceService.start_approval_for_node(
                    tenant_id=tenant_id,
                    user_id=created_by,
                    node_key="shipment_notice",
                    entity_type="shipment_notice",
                    entity_id=notice.id,
                    entity_uuid=str(notice.uuid),
                    title=f"发货通知单审批: {notice.notice_code}",
                    content=f"客户: {notice.customer_name}, 金额: {notice.total_amount}",
                )
                if not instance:
                    raise BusinessLogicError(
                        "发货通知单审核已开启但未找到可用的审批流程，请在配置中心检查 shipment_notice 审批流程是否已激活"
                    )
                from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit

                if approval_instance_finished_on_submit(instance):
                    return await self.approve_shipment_notice(
                        tenant_id, notice.id, created_by
                    )
            resp = ShipmentNoticeResponse.model_validate(notice)
            return await self._enrich_notice_response(tenant_id, notice, resp)

    async def get_shipment_notice_by_id(
        self,
        tenant_id: int,
        notice_id: int,
        current_user: Optional[User] = None,
    ) -> ShipmentNoticeWithItemsResponse:
        """根据ID获取发货通知单（含明细）"""
        notice = await ShipmentNotice.get_or_none(tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True)
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")
        if current_user:
            await assert_sales_order_child_row_visible(
                notice,
                tenant_id=tenant_id,
                user=current_user,
                order_id_field="sales_order_id",
            )

        items = await ShipmentNoticeItem.filter(tenant_id=tenant_id, notice_id=notice_id).all()
        response = ShipmentNoticeWithItemsResponse.model_validate(notice)
        response.items = [ShipmentNoticeItemResponse.model_validate(i) for i in items]
        from apps.kuaizhizao.services.document_lifecycle_service import get_shipment_notice_lifecycle, get_document_milestones
        milestones = await get_document_milestones(tenant_id, "shipment_notice", notice_id)
        response.lifecycle = get_shipment_notice_lifecycle(notice, milestones=milestones)
        return await self._enrich_notice_response(tenant_id, notice, response)

    async def list_shipment_notices(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        current_user: Optional[User] = None,
        **filters
    ) -> Dict[str, Any]:
        """获取发货通知单列表（含 capabilities 与分页 total）。"""
        query = ShipmentNotice.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        query = await apply_sales_order_child_list_scope(
            query,
            tenant_id=tenant_id,
            current_user=current_user,
            order_id_field="sales_order_id",
        )
        if filters.get("status"):
            query = query.filter(status=filters["status"])
        if filters.get("sales_order_id"):
            query = query.filter(sales_order_id=filters["sales_order_id"])
        if filters.get("customer_id"):
            query = query.filter(customer_id=int(filters["customer_id"]))
        if filters.get("warehouse_id"):
            query = query.filter(warehouse_id=int(filters["warehouse_id"]))
        if filters.get("planned_start_date"):
            query = query.filter(planned_ship_date__gte=filters["planned_start_date"])
        if filters.get("planned_end_date"):
            query = query.filter(planned_ship_date__lte=filters["planned_end_date"])
        if filters.get("created_start_date"):
            query = query.filter(
                created_at__gte=datetime.combine(filters["created_start_date"], time.min)
            )
        if filters.get("created_end_date"):
            query = query.filter(
                created_at__lte=datetime.combine(filters["created_end_date"], time(23, 59, 59))
            )
        keyword = str(filters.get("keyword") or "").strip()
        if keyword:
            from apps.kuaizhizao.utils.list_item_material_keyword import (
                header_ids_matching_item_material,
            )

            material_notice_ids = await header_ids_matching_item_material(
                tenant_id,
                ShipmentNoticeItem,
                "notice_id",
                keyword,
            )
            query = query.filter(
                Q(notice_code__icontains=keyword)
                | Q(sales_order_code__icontains=keyword)
                | Q(customer_name__icontains=keyword)
                | Q(warehouse_name__icontains=keyword)
                | Q(sales_delivery_code__icontains=keyword)
                | Q(id__in=material_notice_ids)
            )
        if filters.get("notice_code"):
            code = str(filters["notice_code"]).strip()
            if code:
                query = query.filter(notice_code__icontains=code)
        if filters.get("sales_order_code"):
            order_code = str(filters["sales_order_code"]).strip()
            if order_code:
                query = query.filter(sales_order_code__icontains=order_code)

        total = await query.count()
        order_clause = filters.get("order_by") or "-created_at"
        notices = await query.offset(skip).limit(limit).order_by(order_clause, "-id")
        notice_list = list(notices)
        notice_ids = [int(n.id) for n in notice_list]
        include_items = bool(filters.get("include_items"))
        items_by_notice: dict[int, list] = {}
        if include_items and notice_ids:
            from apps.kuaizhizao.schemas.shipment_notice import ShipmentNoticeItemResponse

            all_items = (
                await ShipmentNoticeItem.filter(tenant_id=tenant_id, notice_id__in=notice_ids)
                .order_by("notice_id", "id")
                .all()
            )
            for it in all_items:
                nid = int(it.notice_id)
                items_by_notice.setdefault(nid, []).append(
                    ShipmentNoticeItemResponse.model_validate(it)
                )
        has_items_by_id = await self._notice_has_items_map(tenant_id, notice_ids)
        withdrawable_by_id = await self._delivery_withdrawable_by_notice_id(tenant_id, notice_list)
        from apps.kuaizhizao.services.document_lifecycle_service import get_shipment_notice_lifecycle
        list_responses: List[ShipmentNoticeListResponse] = []
        for r in notice_list:
            resp = ShipmentNoticeListResponse.model_validate(r)
            resp.lifecycle = get_shipment_notice_lifecycle(r)
            if include_items:
                resp.items = items_by_notice.get(int(r.id), [])
            list_responses.append(resp)
        allow_print = await self.business_config_service.get_allow_print_unaudited(tenant_id)
        with push_allow_print_unaudited(allow_print):
            capped = enrich_shipment_notice_list_capabilities(
                notice_list,
                list_responses,
                has_items_by_id=has_items_by_id,
                delivery_withdrawable_by_id=withdrawable_by_id,
            )
        enriched = await enrich_items(tenant_id, "shipment_notice", capped)
        return {
            "data": [item.model_dump() for item in enriched],
            "total": total,
            "success": True,
        }

    async def update_shipment_notice(
        self,
        tenant_id: int,
        notice_id: int,
        notice_data: ShipmentNoticeUpdate,
        updated_by: int
    ) -> ShipmentNoticeResponse:
        """更新发货通知单"""
        notice_row = await ShipmentNotice.get_or_none(
            tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True
        )
        if not notice_row:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")
        assert_shipment_notice_capability(notice_row, "update")

        async with in_transaction():
            dump = notice_data.model_dump(exclude_unset=True, exclude={"notice_code"})
            user_info = await self.get_user_info(updated_by)
            dump["updated_by"] = updated_by
            dump["updated_by_name"] = user_info["name"]
            await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(**dump)
            updated = await ShipmentNotice.get(tenant_id=tenant_id, id=notice_id)
            resp = ShipmentNoticeResponse.model_validate(updated)
            return await self._enrich_notice_response(tenant_id, updated, resp)

    async def delete_shipment_notice(self, tenant_id: int, notice_id: int) -> bool:
        """删除发货通知单"""
        notice = await ShipmentNotice.get_or_none(tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True)
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")
        assert_shipment_notice_capability(notice, "delete")

        await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(deleted_at=resolve_business_datetime())
        return True

    async def submit_shipment_notice(
        self,
        tenant_id: int,
        notice_id: int,
        submitted_by: int,
    ) -> ShipmentNoticeResponse:
        notice = await ShipmentNotice.get_or_none(
            tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True
        )
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")
        review = str(notice.review_status or "").strip()
        status = str(notice.status or "").strip()
        user_name = (await self.get_user_info(submitted_by))["name"]
        if review == "待审核":
            return await self.get_shipment_notice_by_id(tenant_id, notice_id)
        if status == "待审核":
            await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(
                review_status="待审核",
                updated_by=submitted_by,
                updated_by_name=user_name,
            )
            return await self.get_shipment_notice_by_id(tenant_id, notice_id)

        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "shipment_notice"
        )
        assert_shipment_notice_capability(notice, "submit")
        if not audit_required:
            await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(
                status="待发货",
                review_status="已通过",
                updated_by=submitted_by,
                updated_by_name=user_name,
            )
            return await self.get_shipment_notice_by_id(tenant_id, notice_id)

        from core.services.approval.approval_instance_service import ApprovalInstanceService

        instance = await ApprovalInstanceService.start_approval_for_node(
            tenant_id=tenant_id,
            user_id=submitted_by,
            node_key="shipment_notice",
            entity_type="shipment_notice",
            entity_id=notice.id,
            entity_uuid=str(notice.uuid),
            title=f"发货通知单审批: {notice.notice_code}",
            content=f"客户: {notice.customer_name}, 金额: {notice.total_amount}",
        )
        if not instance:
            raise BusinessLogicError(
                "发货通知单审核已开启但未找到可用的审批流程，请在配置中心检查 shipment_notice 审批流程是否已激活"
            )
        await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(
            status="待审核",
            review_status="待审核",
            updated_by=submitted_by,
            updated_by_name=user_name,
        )
        from core.services.approval.audit_flow_guard import approval_instance_finished_on_submit

        if approval_instance_finished_on_submit(instance):
            return await self.approve_shipment_notice(tenant_id, notice_id, submitted_by)
        return await self.get_shipment_notice_by_id(tenant_id, notice_id)

    async def approve_shipment_notice(
        self,
        tenant_id: int,
        notice_id: int,
        approver_id: int,
    ) -> ShipmentNoticeResponse:
        notice = await ShipmentNotice.get_or_none(
            tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True
        )
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")
        assert_shipment_notice_capability(notice, "approve")
        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "shipment_notice"
        )
        if audit_required:
            from core.services.approval.audit_flow_guard import (
                assert_manual_approval_action_allowed,
                get_approval_gate_status,
            )

            gate = await get_approval_gate_status(
                tenant_id=tenant_id,
                entity_type="shipment_notice",
                entity_id=notice_id,
            )
            assert_manual_approval_action_allowed(
                gate,
                doc_label="发货通知单",
                verb="审核",
            )
        await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(
            status="待发货",
            review_status="已通过",
            updated_by=approver_id,
            updated_by_name=(await self.get_user_info(approver_id))["name"],
        )
        return await self.get_shipment_notice_by_id(tenant_id, notice_id)

    async def reject_shipment_notice(
        self,
        tenant_id: int,
        notice_id: int,
        approver_id: int,
        *,
        rejection_reason: Optional[str] = None,
    ) -> ShipmentNoticeResponse:
        notice = await ShipmentNotice.get_or_none(
            tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True
        )
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")
        assert_shipment_notice_capability(notice, "reject")
        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "shipment_notice"
        )
        if audit_required:
            from core.services.approval.audit_flow_guard import (
                assert_manual_approval_action_allowed,
                get_approval_gate_status,
            )

            gate = await get_approval_gate_status(
                tenant_id=tenant_id,
                entity_type="shipment_notice",
                entity_id=notice_id,
            )
            assert_manual_approval_action_allowed(
                gate,
                doc_label="发货通知单",
                verb="驳回",
            )
        await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(
            status="草稿",
            review_status="已驳回",
            updated_by=approver_id,
            updated_by_name=(await self.get_user_info(approver_id))["name"],
        )
        return await self.get_shipment_notice_by_id(tenant_id, notice_id)

    async def withdraw_shipment_notice_submit(
        self,
        tenant_id: int,
        notice_id: int,
        operator_id: int,
    ) -> ShipmentNoticeResponse:
        notice = await ShipmentNotice.get_or_none(
            tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True
        )
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")
        assert_shipment_notice_capability(notice, "withdraw_submit")
        from core.services.approval.approval_instance_service import ApprovalInstanceService

        await ApprovalInstanceService.cancel_approval(
            tenant_id=tenant_id,
            entity_type="shipment_notice",
            entity_id=notice_id,
            operator_id=operator_id,
        )
        await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(
            status="草稿",
            review_status="草稿",
            updated_by=operator_id,
            updated_by_name=(await self.get_user_info(operator_id))["name"],
        )
        return await self.get_shipment_notice_by_id(tenant_id, notice_id)

    async def revoke_shipment_notice_approval(
        self,
        tenant_id: int,
        notice_id: int,
        operator_id: int,
    ) -> ShipmentNoticeResponse:
        from core.services.approval.audit_transition import (
            resolve_revoke_to_draft_landing_phase,
        )
        from core.services.approval.uni_audit_service import UniAuditService

        notice = await ShipmentNotice.get_or_none(
            tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True
        )
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")
        assert_shipment_notice_capability(notice, "revoke_approval")
        audit_required = await self.business_config_service.check_audit_required(
            tenant_id, "shipment_notice"
        )

        async def _do_revoke(*, reopened: bool = False) -> ShipmentNoticeResponse:
            landing = resolve_revoke_to_draft_landing_phase(
                manual_audit_enabled=audit_required,
                flow_reopened=reopened,
            )
            if landing == "pending":
                next_status, next_review = "待审核", "待审核"
            else:
                next_status, next_review = "草稿", "草稿"
            await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(
                status=next_status,
                review_status=next_review,
                updated_by=operator_id,
                updated_by_name=(await self.get_user_info(operator_id))["name"],
            )
            return await self.get_shipment_notice_by_id(tenant_id, notice_id)

        return await UniAuditService.revoke_with_flow_fallback(
            tenant_id=tenant_id,
            entity_type="shipment_notice",
            entity_id=notice_id,
            operator_id=operator_id,
            flow_revoke=_do_revoke,
        )

    async def _apply_notify_line_warehouses(
        self,
        *,
        tenant_id: int,
        notice: ShipmentNotice,
        notified_by: int,
        notify_data: Optional[ShipmentNoticeNotify],
    ) -> tuple[ShipmentNotice, List[ShipmentNoticeItem], Dict[int, tuple[Optional[int], Optional[str]]]]:
        """将通知请求中的行仓/库位落到通知明细，并解析出库库位（无库位仓 ensure 整仓）。

        未传库位时，仅真实货位要求调用方指定；只有系统占位「整仓」则交给原库位解析复用。
        返回：(刷新后的通知头, 明细列表, {item_id: (location_id, location_code)})。
        """
        from apps.kuaizhizao.services.warehouse_service import _resolve_line_location_pair

        notice_items = await ShipmentNoticeItem.filter(
            tenant_id=tenant_id,
            notice_id=notice.id,
        ).order_by("id")
        if not notice_items:
            raise BusinessLogicError("发货通知单无明细，无法通知仓库")

        line_wh = _coerce_int_id_map(
            getattr(notify_data, "line_warehouses", None) if notify_data else None
        )
        line_wh_names = _coerce_str_id_map(
            getattr(notify_data, "line_warehouse_names", None) if notify_data else None
        )
        line_loc = _coerce_int_id_map(
            getattr(notify_data, "line_location_ids", None) if notify_data else None
        )
        line_loc_codes = _coerce_str_id_map(
            getattr(notify_data, "line_location_codes", None) if notify_data else None
        )
        header_wh = getattr(notify_data, "warehouse_id", None) if notify_data else None
        if header_wh is not None:
            try:
                header_wh = int(header_wh)
            except (TypeError, ValueError):
                header_wh = None
        if header_wh is not None and header_wh <= 0:
            header_wh = None
        header_wh_name = (
            str(getattr(notify_data, "warehouse_name", None) or "").strip()
            if notify_data
            else ""
        ) or None
        fallback_wh = header_wh or getattr(notice, "warehouse_id", None)
        fallback_wh_name = header_wh_name or getattr(notice, "warehouse_name", None)

        location_by_item: Dict[int, tuple[Optional[int], Optional[str]]] = {}
        applied_warehouses: List[tuple[int, str]] = []

        for item in notice_items:
            qty = Decimal(str(getattr(item, "notice_quantity", 0) or 0))
            if qty <= Decimal("0"):
                continue
            item_id = int(item.id)
            label = (
                getattr(item, "material_code", None)
                or getattr(item, "material_name", None)
                or str(item_id)
            )
            wh_id = line_wh.get(item_id) or getattr(item, "warehouse_id", None) or fallback_wh
            if wh_id is None or int(wh_id) <= 0:
                raise ValidationError(f"请为物料 {label} 指定出库仓库")
            wh_id = int(wh_id)
            wh_name = await _resolve_warehouse_name_by_id(
                tenant_id=tenant_id,
                warehouse_id=wh_id,
                preferred_name=(
                    line_wh_names.get(item_id)
                    or getattr(item, "warehouse_name", None)
                    or fallback_wh_name
                ),
            )
            if int(getattr(item, "warehouse_id", 0) or 0) != wh_id or (
                str(getattr(item, "warehouse_name", None) or "").strip() != wh_name
            ):
                await ShipmentNoticeItem.filter(tenant_id=tenant_id, id=item_id).update(
                    warehouse_id=wh_id,
                    warehouse_name=wh_name,
                )
                item.warehouse_id = wh_id
                item.warehouse_name = wh_name

            requested_loc_id = line_loc.get(item_id)
            requested_loc_code = line_loc_codes.get(item_id)
            has_requested_location = (
                requested_loc_id is not None and int(requested_loc_id) > 0
            ) or bool(str(requested_loc_code or "").strip())
            if not has_requested_location:
                if await _warehouse_has_real_storage_location(tenant_id, wh_id):
                    raise ValidationError(f"物料 {label} 的出库仓库已有库位，请指定库位")
            loc_id, loc_code = await _resolve_line_location_pair(
                tenant_id,
                warehouse_id=wh_id,
                location_id=requested_loc_id,
                location_code=requested_loc_code,
                material_label=str(label),
                direction_label="出库",
            )
            location_by_item[item_id] = (loc_id, loc_code)
            applied_warehouses.append((wh_id, wh_name))

        if not applied_warehouses:
            raise BusinessLogicError("发货通知单无有效明细，无法通知仓库")

        unique_wh = {wh_id for wh_id, _ in applied_warehouses}
        if len(unique_wh) == 1:
            only_wh_id, only_wh_name = applied_warehouses[0]
            await ShipmentNotice.filter(tenant_id=tenant_id, id=notice.id).update(
                warehouse_id=only_wh_id,
                warehouse_name=only_wh_name,
                updated_by=notified_by,
                updated_by_name=(await self.get_user_info(notified_by))["name"],
            )
        elif fallback_wh is not None and int(fallback_wh) > 0:
            fb_name = await _resolve_warehouse_name_by_id(
                tenant_id=tenant_id,
                warehouse_id=int(fallback_wh),
                preferred_name=fallback_wh_name,
            )
            await ShipmentNotice.filter(tenant_id=tenant_id, id=notice.id).update(
                warehouse_id=int(fallback_wh),
                warehouse_name=fb_name,
                updated_by=notified_by,
                updated_by_name=(await self.get_user_info(notified_by))["name"],
            )

        notice = await ShipmentNotice.get(tenant_id=tenant_id, id=notice.id)
        notice_items = await ShipmentNoticeItem.filter(
            tenant_id=tenant_id,
            notice_id=notice.id,
        ).order_by("id")
        return notice, list(notice_items), location_by_item


    async def preview_notify_warehouse(
        self,
        tenant_id: int,
        notice_id: int,
        *,
        warehouse_id: Optional[int] = None,
        line_warehouses: Optional[Dict[Any, Any]] = None,
    ) -> Dict[str, Any]:
        """通知仓库预览：返回通知明细数量、已占用、可通知量，不实际创建出库单。"""
        notice = await ShipmentNotice.get_or_none(
            tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True
        )
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")

        notice_items = await ShipmentNoticeItem.filter(
            tenant_id=tenant_id, notice_id=notice_id
        ).order_by("id")
        if not notice_items:
            raise BusinessLogicError("发货通知单无明细，无法通知仓库")

        line_wh_override = _coerce_int_id_map(line_warehouses)
        effective_header_wh = warehouse_id or getattr(notice, "warehouse_id", None)

        def _effective_line_warehouse(item: ShipmentNoticeItem) -> Optional[int]:
            item_id = int(item.id)
            wh = (
                line_wh_override.get(item_id)
                or getattr(item, "warehouse_id", None)
                or effective_header_wh
            )
            if wh is None:
                return None
            try:
                wh_int = int(wh)
            except (TypeError, ValueError):
                return None
            return wh_int if wh_int > 0 else None

        line_warehouses_ok = all(
            _effective_line_warehouse(item) is not None
            for item in notice_items
            if Decimal(str(getattr(item, "notice_quantity", 0) or 0)) > Decimal("0")
        ) and any(
            Decimal(str(getattr(item, "notice_quantity", 0) or 0)) > Decimal("0")
            for item in notice_items
        )
        # 能力门禁：缺仓可在弹窗补选，不因缺仓关闭 notify 能力；库存校验按已选行仓执行
        caps = derive_shipment_notice_capabilities(
            notice,
            has_items=True,
            has_warehouse=True,
        )
        push_allowed = caps.notify.allowed
        blocking_reason = caps.notify.reason if not push_allowed else None

        order_items = await SalesOrderItem.filter(
            tenant_id=tenant_id,
            sales_order_id=notice.sales_order_id,
        ).all()
        order_item_by_id = {int(it.id): it for it in order_items}

        reserved_notice_ids = await ShipmentNotice.filter(
            tenant_id=tenant_id,
            sales_order_id=notice.sales_order_id,
            status="已通知",
            deleted_at__isnull=True,
        ).exclude(id=notice.id).values_list("id", flat=True)

        reserved_by_item_id: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        if reserved_notice_ids:
            reserved_items = await ShipmentNoticeItem.filter(
                tenant_id=tenant_id,
                notice_id__in=list(reserved_notice_ids),
            ).all()
            for rit in reserved_items:
                so_item_id = getattr(rit, "sales_order_item_id", None)
                if so_item_id is None:
                    continue
                reserved_by_item_id[int(so_item_id)] += Decimal(str(rit.notice_quantity or 0))

        from apps.kuaizhizao.utils.over_qty_tolerance import (
            OverQtyToleranceResolver,
            max_pushable_with_issue_tolerance,
        )
        from apps.kuaizhizao.utils.sales_order_push_qty import get_pushable_qty_for_order_items

        pushable_by_item = await get_pushable_qty_for_order_items(
            tenant_id,
            int(notice.sales_order_id),
            order_items,
            exclude_notice_id=int(notice.id),
        )
        tolerance_resolver = OverQtyToleranceResolver(tenant_id)

        preview_items: List[Dict[str, Any]] = []
        line_blocking_issues: List[str] = []
        for n_item in notice_items:
            notice_qty = Decimal(str(n_item.notice_quantity or 0))
            so_item_id = getattr(n_item, "sales_order_item_id", None)
            reserved_qty = Decimal("0")
            available_qty = notice_qty
            order_qty = notice_qty
            issue_pct = Decimal("0")

            if so_item_id is not None:
                so_item_id = int(so_item_id)
                so_item = order_item_by_id.get(so_item_id)
                if so_item:
                    order_qty = Decimal(str(so_item.order_quantity or 0))
                    base_push = pushable_by_item.get(so_item_id, Decimal("0"))
                    available_qty, issue_pct = await max_pushable_with_issue_tolerance(
                        tenant_id,
                        material_id=int(so_item.material_id),
                        base_pushable=base_push,
                        resolver=tolerance_resolver,
                    )
                    reserved_qty = reserved_by_item_id.get(so_item_id, Decimal("0"))
                    if notice_qty > available_qty:
                        material_label = (
                            getattr(so_item, "material_code", None)
                            or getattr(so_item, "material_name", None)
                            or str(so_item_id)
                        )
                        line_blocking_issues.append(
                            f"物料 {material_label} 通知数量 {notice_qty} 超过可通知欠发量 {available_qty}"
                        )

            effective_wh = _effective_line_warehouse(n_item)
            preview_items.append({
                "item_id": int(n_item.id),
                "sales_order_item_id": int(so_item_id) if so_item_id is not None else None,
                "material_id": int(n_item.material_id) if getattr(n_item, "material_id", None) else None,
                "material_code": str(getattr(n_item, "material_code", "") or "").strip(),
                "material_name": str(getattr(n_item, "material_name", "") or "").strip(),
                "quantity": float(order_qty),
                "pushed_quantity": float(reserved_qty),
                "max_push_quantity": float(available_qty),
                "notice_quantity": float(notice_qty),
                "over_issue_tolerance_pct": float(issue_pct),
                "warehouse_id": int(effective_wh) if effective_wh is not None else None,
                "warehouse_name": getattr(n_item, "warehouse_name", None),
            })

        required_by_wh_material: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
        labels_by_wh_material: dict[tuple[int, int], str] = {}
        warehouse_names_by_id: Dict[int, str] = {}
        for item in notice_items:
            material_id = getattr(item, "material_id", None)
            if not material_id:
                continue
            qty = Decimal(str(getattr(item, "notice_quantity", 0) or 0))
            if qty <= Decimal("0"):
                continue
            wh_id = _effective_line_warehouse(item)
            if wh_id is None:
                continue
            key = (int(wh_id), int(material_id))
            required_by_wh_material[key] += qty
            labels_by_wh_material[key] = (
                getattr(item, "material_code", None)
                or getattr(item, "material_name", None)
                or str(material_id)
            )
            wh_name = (
                str(getattr(item, "warehouse_name", None) or "").strip()
                or str(getattr(notice, "warehouse_name", None) or "").strip()
            )
            if wh_name and int(wh_id) not in warehouse_names_by_id:
                warehouse_names_by_id[int(wh_id)] = wh_name

        inventory_blocking = await self._build_notify_inventory_shortfall_messages(
            tenant_id=tenant_id,
            exclude_notice_id=int(notice.id),
            required_by_wh_material=required_by_wh_material,
            labels_by_wh_material=labels_by_wh_material,
            warehouse_names_by_id=warehouse_names_by_id,
        )

        if line_blocking_issues or inventory_blocking:
            push_allowed = False
            blocking_reason = blocking_reason or "shipment_notice.notify.overdelivery_or_inventory"

        pushable_count = sum(
            1 for row in preview_items if float(row.get("max_push_quantity") or 0) > 0
        )
        header_wh_out = effective_header_wh
        try:
            header_wh_out = int(header_wh_out) if header_wh_out is not None else None
        except (TypeError, ValueError):
            header_wh_out = None
        return {
            "target_type": "sales_delivery",
            "summary": (
                f"请确认将通知仓库的发货明细（{pushable_count}/{len(preview_items)} 行可通知）"
                if push_allowed
                else "当前发货通知单不可通知仓库"
            ),
            "notice_code": notice.notice_code,
            "warehouse_required": not line_warehouses_ok,
            "line_warehouse_required": not line_warehouses_ok,
            "warehouse_id": header_wh_out if header_wh_out and header_wh_out > 0 else None,
            "items": preview_items,
            "has_blocking_issues": not push_allowed,
            "blocking_reason": blocking_reason if not push_allowed else None,
            "line_blocking_issues": line_blocking_issues + inventory_blocking,
            "tip": "确认后将生成销售出库单（待出库），并标记本通知单为已通知。请按明细选择出库仓库与库位。",
        }


    async def notify_warehouse(
        self,
        tenant_id: int,
        notice_id: int,
        notified_by: int,
        *,
        notify_data: Optional[ShipmentNoticeNotify] = None,
    ) -> ShipmentNoticeResponse:
        """通知仓库（标记为已通知）"""
        notice = await ShipmentNotice.get_or_none(tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True)
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")
        if not shipment_notice_review_approved(notice.review_status):
            audit_required = await self.business_config_service.check_audit_required(
                tenant_id, "shipment_notice"
            )
            if audit_required:
                assert_shipment_notice_capability(notice, "notify")
            await self.submit_shipment_notice(tenant_id, notice_id, notified_by)
            notice = await ShipmentNotice.get_or_none(
                tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True
            )
            if not notice:
                raise NotFoundError(f"发货通知单不存在: {notice_id}")
        item_count = await ShipmentNoticeItem.filter(tenant_id=tenant_id, notice_id=notice_id).count()
        assert_shipment_notice_capability(
            notice,
            "notify",
            has_items=item_count > 0,
        )

        notice, notice_items, location_by_item = await self._apply_notify_line_warehouses(
            tenant_id=tenant_id,
            notice=notice,
            notified_by=notified_by,
            notify_data=notify_data,
        )

        await self._validate_not_overdelivery_on_notify(
            tenant_id=tenant_id,
            notice=notice,
        )
        await self._validate_inventory_reservation_on_notify(
            tenant_id=tenant_id,
            notice=notice,
        )

        # 按行出库仓库分组生成销售出库单
        from apps.kuaizhizao.services.warehouse_service import SalesDeliveryService
        from apps.kuaizhizao.schemas.warehouse import SalesDeliveryCreate, SalesDeliveryItemCreate

        from apps.kuaizhizao.services.warehouse_service import (
            occupied_sales_delivery_qty_by_notice_item_ids,
        )

        price_type = None
        so_item_by_id: Dict[int, SalesOrderItem] = {}
        if notice.sales_order_id:
            sales_order = await SalesOrder.get_or_none(tenant_id=tenant_id, id=int(notice.sales_order_id))
            if sales_order is not None:
                from apps.kuaizhizao.constants.price_type import normalize_price_type

                price_type = normalize_price_type(getattr(sales_order, "price_type", None))
            so_ids = {
                int(getattr(item, "sales_order_item_id", 0) or 0)
                for item in notice_items
                if int(getattr(item, "sales_order_item_id", 0) or 0) > 0
            }
            if so_ids:
                for soi in await SalesOrderItem.filter(tenant_id=tenant_id, id__in=list(so_ids)):
                    so_item_by_id[int(soi.id)] = soi

        occupied_by_notice_item = await occupied_sales_delivery_qty_by_notice_item_ids(
            tenant_id, [int(item.id) for item in notice_items]
        )
        groups: dict[int, list] = defaultdict(list)
        for item in notice_items:
            qty = Decimal(str(getattr(item, "notice_quantity", 0) or 0)) - occupied_by_notice_item.get(
                int(item.id), Decimal("0")
            )
            if qty <= Decimal("0"):
                continue
            wh_id = getattr(item, "warehouse_id", None) or getattr(notice, "warehouse_id", None)
            if wh_id is None:
                label = getattr(item, "material_code", None) or getattr(item, "material_name", None) or str(item.id)
                raise ValidationError(f"请为物料 {label} 指定出库仓库")
            groups[int(wh_id)].append((item, qty))

        if not groups:
            raise BusinessLogicError("发货通知单无有效明细，无法通知仓库")

        delivery_service = SalesDeliveryService()
        created_deliveries = []
        for wh_id, group_items in groups.items():
            wh_name = await _resolve_warehouse_name_by_id(
                tenant_id=tenant_id,
                warehouse_id=wh_id,
                preferred_name=next(
                    (getattr(item, "warehouse_name", None) for item, _qty in group_items if getattr(item, "warehouse_name", None)),
                    getattr(notice, "warehouse_name", None),
                ),
            )
            delivery_items = []
            from apps.master_data.models.material import Material
            from apps.kuaizhizao.utils.material_dual_quantity_utils import is_floating_line_unit

            material_ids = {
                int(getattr(item, "material_id", 0) or 0)
                for item, _qty in group_items
                if int(getattr(item, "material_id", 0) or 0) > 0
            }
            material_by_id: Dict[int, Any] = {}
            if material_ids:
                for mat in await Material.filter(tenant_id=tenant_id, id__in=list(material_ids)):
                    material_by_id[int(mat.id)] = mat

            for item, qty in group_items:
                unit_price = getattr(item, "unit_price", None)
                so_item_id = getattr(item, "sales_order_item_id", None)
                so_line_id = int(so_item_id) if so_item_id else 0
                so_item = so_item_by_id.get(so_line_id) if so_line_id > 0 else None
                line_tax = getattr(so_item, "tax_rate", 0) or 0 if so_item else 0
                total_amount = self._shipment_notice_line_amount(
                    qty,
                    unit_price,
                    sales_order_item=so_item,
                    price_type=price_type,
                )
                material_unit = str(getattr(item, "material_unit", None) or "").strip() or None
                aux_quantity = getattr(item, "aux_quantity", None)
                aux_unit = getattr(item, "aux_unit", None)
                unit_conversion_rate = getattr(item, "unit_conversion_rate", None)
                mid = int(getattr(item, "material_id", 0) or 0)
                mat = material_by_id.get(mid)
                # 通知下推出库：行单位若是无固定换算副单位且未带副数量/换算率，回落主单位，避免确认出库被卡
                if (
                    mat is not None
                    and material_unit
                    and is_floating_line_unit(mat, material_unit)
                    and aux_quantity is None
                    and unit_conversion_rate is None
                ):
                    base_unit = str(getattr(mat, "base_unit", None) or "").strip()
                    if base_unit:
                        material_unit = base_unit
                loc_id, loc_code = location_by_item.get(int(item.id), (None, None))
                delivery_items.append(
                    SalesDeliveryItemCreate(
                        sales_order_item_id=int(so_item_id) if so_item_id else None,
                        shipment_notice_item_id=int(item.id),
                        material_id=item.material_id,
                        material_code=item.material_code,
                        material_name=item.material_name,
                        material_spec=getattr(item, "material_spec", None),
                        material_unit=material_unit or item.material_unit,
                        delivery_quantity=float(qty),
                        unit_price=float(unit_price) if unit_price is not None else 0.0,
                        tax_rate=float(line_tax or 0),
                        total_amount=float(total_amount) if total_amount is not None else 0.0,
                        is_gift=bool(getattr(item, "is_gift", False)),
                        gift_ref_unit_price=(
                            float(item.gift_ref_unit_price)
                            if getattr(item, "gift_ref_unit_price", None) is not None
                            else None
                        ),
                        warehouse_id=int(wh_id),
                        warehouse_name=wh_name,
                        location_id=int(loc_id) if loc_id is not None and int(loc_id) > 0 else None,
                        location_code=loc_code,
                        aux_quantity=float(aux_quantity) if aux_quantity is not None else None,
                        aux_unit=aux_unit,
                        unit_conversion_rate=(
                            float(unit_conversion_rate) if unit_conversion_rate is not None else None
                        ),
                        notes=getattr(item, "notes", None),
                    )
                )

            delivery_data = SalesDeliveryCreate(
                sales_order_id=notice.sales_order_id,
                sales_order_code=notice.sales_order_code,
                demand_id=notice.sales_order_id,
                demand_code=notice.sales_order_code,
                demand_type="sales_order",
                customer_id=notice.customer_id,
                customer_name=notice.customer_name,
                customer_contact=getattr(notice, "customer_contact", None),
                customer_phone=getattr(notice, "customer_phone", None),
                warehouse_id=wh_id,
                warehouse_name=wh_name,
                delivery_time=notice.planned_ship_date,
                shipping_address=getattr(notice, "shipping_address", None),
                notes=getattr(notice, "notes", None),
                currency_code=getattr(notice, "currency_code", None) or "CNY",
                exchange_rate=getattr(notice, "exchange_rate", None) or Decimal("1"),
                price_type=price_type,
                items=delivery_items,
                status="待出库",
            )
            delivery = await delivery_service.create_sales_delivery(
                tenant_id=tenant_id,
                delivery_data=delivery_data,
                created_by=notified_by,
                require_batch_serial_on_create=False,
                skip_manual_create_auto_submit=True,
            )
            push_mode = None
            if notify_data is not None:
                push_mode = getattr(notify_data, "push_mode", None)
            delivery = await delivery_service._finalize_sales_delivery_after_document_push(
                tenant_id,
                int(delivery.id),
                notified_by,
                push_mode=push_mode,
            )
            created_deliveries.append(delivery)

        primary_delivery = created_deliveries[0]
        related_deliveries = [
            {"id": int(d.id), "code": str(d.delivery_code)}
            for d in created_deliveries
        ]

        await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(
            status="已通知",
            notified_at=resolve_business_datetime(),
            sales_delivery_id=primary_delivery.id,
            sales_delivery_code=primary_delivery.delivery_code,
            related_sales_delivery_ids=related_deliveries,
            updated_by=notified_by,
            updated_by_name=(await self.get_user_info(notified_by))["name"],
        )
        # 回写关联后再自动建 OQC，避免与「销售出库创建时自动建 OQC」在未关联窗口双建。
        # 门禁在确认出库时校验，此处只建待检验单。
        from apps.kuaizhizao.services.quality_automation_service import QualityAutomationService

        await QualityAutomationService().maybe_auto_create_oqc_from_shipment_notice(
            tenant_id=tenant_id,
            notice_id=notice_id,
            user_id=notified_by,
        )
        updated = await ShipmentNotice.get(tenant_id=tenant_id, id=notice_id)
        from apps.kuaizhizao.models.sales_order import SalesOrder
        from apps.kuaizhizao.services.kuaizhizao_business_notification import (
            ACTION_CONFIRMED,
            DOC_SHIPMENT_NOTICE,
            dispatch_kuaizhizao_notification,
        )

        sales_order = await SalesOrder.get_or_none(
            tenant_id=tenant_id,
            id=updated.sales_order_id,
            deleted_at__isnull=True,
        )
        try:
            await dispatch_kuaizhizao_notification(
                tenant_id,
                trigger_document=DOC_SHIPMENT_NOTICE,
                trigger_action=ACTION_CONFIRMED,
                variables={
                    "notice_code": updated.notice_code or str(notice_id),
                    "sales_order_code": updated.sales_order_code or "—",
                    "customer_name": updated.customer_name or "—",
                    "planned_ship_date": str(updated.planned_ship_date or ""),
                    "detail_path": (
                        f"/apps/kuaizhizao/sales-management/shipment-notices?highlight={notice_id}"
                    ),
                    "shipment_notice_id": str(notice_id),
                },
                context={
                    "creator_user_id": getattr(updated, "created_by", None),
                    "salesman_user_id": sales_order.salesman_id if sales_order else None,
                },
            )
        except Exception as exc:
            logger.warning("发货确认消息提醒失败 tenant={} notice={}: {}", tenant_id, notice_id, exc)
        resp = ShipmentNoticeResponse.model_validate(updated)
        return await self._enrich_notice_response(tenant_id, updated, resp)

    async def withdraw_notice(
        self,
        tenant_id: int,
        notice_id: int,
        withdrawn_by: int,
    ) -> ShipmentNoticeResponse:
        """撤回通知（已通知 -> 待发货）。已出库/已关联出库单不允许撤回。"""
        notice = await ShipmentNotice.get_or_none(tenant_id=tenant_id, id=notice_id, deleted_at__isnull=True)
        if not notice:
            raise NotFoundError(f"发货通知单不存在: {notice_id}")

        delivery_withdrawable = await self._notice_delivery_withdrawable(tenant_id, notice)
        assert_shipment_notice_capability(
            notice,
            "withdraw",
            delivery_withdrawable=delivery_withdrawable,
        )
        if getattr(notice, "sales_delivery_id", None) or getattr(notice, "related_sales_delivery_ids", None):
            from apps.kuaizhizao.models.sales_delivery import SalesDelivery
            from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem

            delivery_ids = self._collect_notice_delivery_ids(notice)
            for delivery_id in delivery_ids:
                delivery = await SalesDelivery.get_or_none(
                    tenant_id=tenant_id, id=delivery_id, deleted_at__isnull=True
                )
                if delivery:
                    await SalesDelivery.filter(tenant_id=tenant_id, id=delivery.id).update(
                        deleted_at=resolve_business_datetime()
                    )
                    await SalesDeliveryItem.filter(tenant_id=tenant_id, delivery_id=delivery.id).delete()

        await ShipmentNotice.filter(tenant_id=tenant_id, id=notice_id).update(
            status="待发货",
            notified_at=None,
            updated_by=withdrawn_by,
            updated_by_name=(await self.get_user_info(withdrawn_by))["name"],
            sales_delivery_id=None,
            sales_delivery_code=None,
            related_sales_delivery_ids=None,
        )
        updated = await ShipmentNotice.get(tenant_id=tenant_id, id=notice_id)
        resp = ShipmentNoticeResponse.model_validate(updated)
        return await self._enrich_notice_response(tenant_id, updated, resp)
