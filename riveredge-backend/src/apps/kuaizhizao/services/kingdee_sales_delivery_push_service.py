"""业务适配：销售出库单 → 金蝶云苍穹销售出库单批量新增（im_saloutbill/batchAdd）。"""

from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.sales_delivery import SalesDelivery
from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem
from apps.kuaizhizao.services.kingdee_im_batch_update_service import (
    kingdee_im_batch_update_linked_bill,
)
from apps.kuaizhizao.services.kingdee_im_warehouse_revoke_service import (
    SALES_DELIVERY_REVOKE_SPEC,
)
from apps.kuaizhizao.services.kingdee_warehouse_billentry_dual_qty import (
    apply_billentry_dual_qty_fields,
    log_billentry_dual_qty,
    resolve_warehouse_bill_line_unit_qty,
    restate_entry_prices_for_inventory_qty,
)
from core.services.integration.document_push_codes import (
    DEFAULT_UNIT_NUMBER,
    apply_unit_code_map,
    load_save_api_unit_code_map,
    resolve_unit_for_push,
)
from core.services.integration.document_push_mapping import apply_field_map, set_path
from core.services.integration.document_push_pipeline import (
    DocumentPushPipeline,
    DocumentPushPrepared,
    DocumentPushRequest,
)
from core.services.integration.kingdee_cosmic_api_presets import (
    BIZ_IM_SALOUTBILL,
    IM_SALOUTBILL_BATCH_ADD_PATH,
)
from core.utils.timezone_utils import (
    resolve_business_datetime,
    to_api_isoformat,
    to_site_date,
    today_site_str,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = BIZ_IM_SALOUTBILL
DEFAULT_SAVE_PATH = IM_SALOUTBILL_BATCH_ADD_PATH
TARGET_TYPE = "kingdee_im_saloutbill"
TARGET_PROFILE = "kingdee_im_saloutbill"
SOURCE_TYPE = "sales_delivery"
PUSHABLE_STATUSES = frozenset({"已出库", "已完成", "processed", "COMPLETED", "POSTED"})
PUSH_DISABLED_MESSAGE = "金蝶销售出库推送未启用"


def sales_delivery_push_skip_reason(
    delivery: SalesDelivery,
    *,
    already_pushed: bool = False,
    items: Optional[List[SalesDeliveryItem]] = None,
) -> Optional[str]:
    if already_pushed:
        return "已推送过金蝶销售出库单"
    status = str(getattr(delivery, "status", None) or "").strip()
    status_upper = status.upper()
    if status not in PUSHABLE_STATUSES and status_upper not in PUSHABLE_STATUSES:
        return f"销售出库状态 {status or '-'} 不可推送（需已出库）"
    if items is not None and not items:
        return "销售出库单无明细行"
    return None


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _date_string(value: Any) -> str:
    if isinstance(value, datetime):
        try:
            return to_site_date(value).isoformat()
        except Exception:
            return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value:
        text = str(value).strip()
        if text:
            return text[:10]
    return today_site_str("%Y-%m-%d")


def _compact_text(*parts: Any) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


async def _resolve_customer_number(
    tenant_id: int, delivery: SalesDelivery, cfg: Dict[str, Any]
) -> Optional[str]:
    configured = str(cfg.get("customer_number") or "").strip()
    if configured:
        return configured
    try:
        from apps.master_data.models.customer import Customer

        customer = await Customer.get_or_none(
            tenant_id=tenant_id,
            id=int(delivery.customer_id or 0),
            deleted_at__isnull=True,
        )
        if customer and str(customer.code or "").strip():
            return str(customer.code).strip()
    except Exception as exc:
        logger.warning(
            "resolve customer number failed delivery_id={} err={}", delivery.id, exc
        )
    return None


async def _resolve_warehouse_number(
    tenant_id: int,
    *,
    warehouse_id: Optional[int],
    cfg: Dict[str, Any],
) -> Optional[str]:
    configured = str(cfg.get("warehouse_number") or cfg.get("stock_number") or "").strip()
    if configured:
        return configured
    wh_id = int(warehouse_id or 0)
    if wh_id <= 0:
        return None
    try:
        from apps.master_data.models.warehouse import Warehouse

        warehouse = await Warehouse.get_or_none(
            tenant_id=tenant_id,
            id=wh_id,
            deleted_at__isnull=True,
        )
        if warehouse and str(warehouse.code or "").strip():
            return str(warehouse.code).strip()
    except Exception as exc:
        logger.warning("resolve warehouse number failed warehouse_id={} err={}", wh_id, exc)
    return None


def build_kingdee_sales_delivery_model(
    *,
    delivery: SalesDelivery,
    items: List[SalesDeliveryItem],
    cfg: Optional[Dict[str, Any]] = None,
    customer_number: Optional[str] = None,
    warehouse_number: Optional[str] = None,
    line_unit_qty_by_item_id: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    config = cfg or {}
    template = config.get("model_template")
    if isinstance(template, dict) and template:
        model = copy.deepcopy(template)
    else:
        model = {"billentry": []}

    org_number = str(
        config.get("org_number") or config.get("bizorg_number") or config.get("createorg_number") or ""
    ).strip()
    bill_date = _date_string(delivery.delivery_time or delivery.created_at)
    settle_org = str(config.get("entrysettleorg_number") or org_number).strip()
    discounttype = str(config.get("discounttype") or "NULL").strip() or "NULL"

    entries: List[Dict[str, Any]] = []
    unit_map = (
        config.get("api_unit_code_map")
        if isinstance(config.get("api_unit_code_map"), dict)
        else None
    )
    line_plan = line_unit_qty_by_item_id or {}
    for item in items:
        doc_qty = _to_float(item.delivery_quantity)
        planned = line_plan.get(int(getattr(item, "id", 0) or 0)) or {}
        qty = _to_float(planned["qty"]) if "qty" in planned else doc_qty
        if qty <= 0:
            continue
        money_qty = doc_qty if doc_qty > 0 else qty
        unit_raw = str(item.material_unit or "").strip()
        unit_number = (
            str(planned.get("unit_number") or "").strip()
            or apply_unit_code_map(unit_raw, unit_map)
            or str(config.get("unit_number") or DEFAULT_UNIT_NUMBER).strip()
            or DEFAULT_UNIT_NUMBER
        )
        entry: Dict[str, Any] = {
            "material_number": str(item.material_code or "").strip(),
            "qty": qty,
            "unit_number": unit_number,
            "linetype_number": str(config.get("linetype_number") or "").strip(),
            "discounttype": discounttype,
        }
        apply_billentry_dual_qty_fields(entry, planned)
        if warehouse_number:
            entry["warehouse_number"] = warehouse_number
        if settle_org:
            entry["entrysettleorg_number"] = settle_org
        if item.location_code:
            entry["location_number"] = str(item.location_code).strip()
        if item.batch_number:
            entry["lotnumber"] = str(item.batch_number).strip()
        if item.expiry_date:
            entry["expirydate"] = _date_string(item.expiry_date)
        if item.notes:
            entry["entrycomment"] = str(item.notes)
        if bool(getattr(item, "is_gift", False)):
            entry["ispresent"] = True
        out_invstatus = str(config.get("outinvstatus_number") or "").strip()
        out_invtype = str(config.get("outinvtype_number") or "").strip()
        if out_invstatus:
            entry["outinvstatus_number"] = out_invstatus
        if out_invtype:
            entry["outinvtype_number"] = out_invtype
        price = _to_float(item.unit_price)
        line_amount = None
        if price:
            line_amount = _to_float(item.total_amount) or price * money_qty
            entry["price"] = price
            entry["amount"] = line_amount
        restate_entry_prices_for_inventory_qty(
            entry,
            document_qty=money_qty,
            unit_price=price,
            amount=line_amount,
        )
        if not entry.get("linetype_number"):
            entry.pop("linetype_number", None)
        entries.append(entry)

    if entries:
        model["billentry"] = entries

    currency = str(
        config.get("currency_number") or delivery.currency_code or "CNY"
    ).strip() or "CNY"
    exchange_rate = _to_float(config.get("exchangerate"))
    if exchange_rate <= 0:
        exchange_rate = _to_float(delivery.exchange_rate) or 1.0

    default_field_map = {
        "billno": "billno",
        "biztime": "biztime",
        "exratedate": "exratedate",
        "bookdate": "bookdate",
        "exchangerate": "exchangerate",
        "paymode": "paymode",
        "istax": "istax",
        "isredbill": "isredbill",
        "currency_number": "currency_number",
        "org_number": "org_number",
        "bizorg_number": "bizorg_number",
        "bizdept_number": "bizdept_number",
        "billtype_number": "billtype_number",
        "biztype_number": "biztype_number",
        "invscheme_number": "invscheme_number",
        "customer_number": "customer_number",
        "comment": "comment",
    }

    def local_value(key: str) -> Any:
        if key == "billno":
            if config.get("use_local_bill_no", True):
                return delivery.delivery_code
            return None
        if key in {"biztime", "exratedate", "bookdate"}:
            return bill_date
        if key == "exchangerate":
            return exchange_rate
        if key == "paymode":
            return config.get("paymode") or "CREDIT"
        if key == "istax":
            raw = config.get("istax")
            if raw is None:
                return True
            return bool(raw)
        if key == "isredbill":
            return bool(config.get("isredbill", False))
        if key == "currency_number":
            return currency
        if key == "org_number":
            return org_number
        if key == "bizorg_number":
            return str(config.get("bizorg_number") or org_number).strip()
        if key == "bizdept_number":
            return str(
                config.get("bizdept_number") or config.get("bizorg_number") or org_number
            ).strip()
        if key == "billtype_number":
            return config.get("billtype_number") or config.get("bill_type_number")
        if key == "biztype_number":
            return config.get("biztype_number")
        if key == "invscheme_number":
            return (
                config.get("invscheme_number")
                or config.get("inwscheme_number")
                or config.get("inv_scheme_number")
            )
        if key == "customer_number":
            return customer_number or config.get("customer_number")
        if key == "comment":
            return _compact_text("快格云销售出库", delivery.delivery_code, delivery.notes)
        return getattr(delivery, key, None)

    apply_field_map(model, dict(default_field_map), local_value)

    fixed_values = config.get("fixed_values")
    if isinstance(fixed_values, dict):
        for target_path, value in fixed_values.items():
            set_path(model, str(target_path), value)

    return model


class KingdeeSalesDeliveryPushService:
    TARGET_PROFILE = TARGET_PROFILE

    async def push_sales_delivery(
        self,
        *,
        tenant_id: int,
        sales_delivery_id: int,
        acting_user_id: int,
        connection_code: Optional[str] = None,
        save_api_uuid: Optional[str] = None,
        dry_run: bool = False,
    ) -> Optional[Dict[str, Any]]:
        config = await self.get_push_config(tenant_id)
        code = str(connection_code or "").strip()
        api_uuid = str(save_api_uuid or "").strip()
        if code or api_uuid:
            config = {
                **config,
                **({"connection_code": code} if code else {}),
                **({"save_api_uuid": api_uuid} if api_uuid else {}),
                "enabled": True,
            }
        if not bool(config.get("enabled", False)):
            return None

        delivery = await SalesDelivery.get_or_none(
            tenant_id=tenant_id,
            id=sales_delivery_id,
            deleted_at__isnull=True,
        )
        if not delivery:
            return None

        items = await SalesDeliveryItem.filter(
            tenant_id=tenant_id,
            delivery_id=sales_delivery_id,
            deleted_at__isnull=True,
        ).order_by("id")

        already_pushed = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=sales_delivery_id,
            target_type=TARGET_TYPE,
        ).exists()
        skip_reason = sales_delivery_push_skip_reason(
            delivery,
            already_pushed=already_pushed,
            items=list(items),
        )
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        try:
            return await self._push_now(
                tenant_id=tenant_id,
                delivery=delivery,
                items=list(items),
                acting_user_id=acting_user_id,
                config=config,
                dry_run=dry_run,
            )
        except Exception as exc:
            logger.warning(
                "销售出库推送金蝶苍穹失败 tenant_id={} sales_delivery_id={} err={}",
                tenant_id,
                sales_delivery_id,
                exc,
            )
            if bool(config.get("fail_on_error", False)):
                raise BusinessLogicError(f"推送金蝶销售出库失败：{exc}")
            return {"success": False, "message": str(exc)}

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        raw = warehouse.get("kingdee_sales_delivery_push") or {}
        return dict(raw) if isinstance(raw, dict) else {}

    async def batch_update_linked_kingdee_bill(
        self,
        *,
        tenant_id: int,
        delivery: SalesDelivery,
        items: List[SalesDeliveryItem],
        acting_user_id: int,
        relation: DocumentRelation,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        async def _prepare(merged: Dict[str, Any]) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
            return await self._prepare_kingdee_push_model(
                tenant_id=tenant_id,
                delivery=delivery,
                items=items,
                acting_user_id=acting_user_id,
                config=merged,
                dry_run=dry_run,
            )

        return await kingdee_im_batch_update_linked_bill(
            tenant_id=tenant_id,
            spec=SALES_DELIVERY_REVOKE_SPEC,
            source_id=int(delivery.id),
            source_type=SOURCE_TYPE,
            relation=relation,
            base_config=config,
            prepare_model=_prepare,
            dry_run=dry_run,
        )

    async def _prepare_kingdee_push_model(
        self,
        *,
        tenant_id: int,
        delivery: SalesDelivery,
        items: List[SalesDeliveryItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
        form_id = str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID
        save_path = str(config.get("save_path") or DEFAULT_SAVE_PATH).strip() or DEFAULT_SAVE_PATH

        required_cfg = (
            "org_number",
            "billtype_number",
            "biztype_number",
            "invscheme_number",
            "linetype_number",
        )
        missing = []
        for key in required_cfg:
            if key == "billtype_number":
                if not (
                    config.get("billtype_number") or config.get("bill_type_number")
                ):
                    missing.append(key)
            elif key == "invscheme_number":
                if not (
                    config.get("invscheme_number")
                    or config.get("inwscheme_number")
                    or config.get("inv_scheme_number")
                ):
                    missing.append(key)
            elif key == "org_number":
                if not (
                    config.get("org_number")
                    or config.get("bizorg_number")
                    or config.get("createorg_number")
                ):
                    missing.append(key)
            elif not str(config.get(key) or "").strip():
                missing.append(key)
        if missing and not dry_run:
            raise BusinessLogicError(
                "金蝶销售出库推送缺少配置：" + "、".join(missing)
                + "（业务配置 parameters.warehouse.kingdee_sales_delivery_push）"
            )

        customer_number = await _resolve_customer_number(tenant_id, delivery, config)
        if not customer_number and not dry_run:
            raise BusinessLogicError("缺少客户编码，无法推送金蝶销售出库单")

        warehouse_number = await _resolve_warehouse_number(
            tenant_id, warehouse_id=delivery.warehouse_id, cfg=config
        )
        if not warehouse_number and not dry_run:
            raise BusinessLogicError("缺少仓库编码，无法推送金蝶销售出库单")

        first_code = items[0].material_code if items else None
        first_unit = str(getattr(items[0], "material_unit", None) or "").strip() if items else ""
        unit_code_map = await load_save_api_unit_code_map(
            tenant_id, str(config.get("save_api_uuid") or "").strip() or None
        )
        units = await resolve_unit_for_push(
            tenant_id,
            product_code=first_code,
            unit_hint=first_unit or None,
            unit_code_map=unit_code_map,
        )
        config = {
            **config,
            **units,
            "api_unit_code_map": unit_code_map,
            "save_path": save_path,
            "body_wrap": str(config.get("body_wrap") or "data_list").strip() or "data_list",
        }

        line_unit_qty_by_item_id = await resolve_warehouse_bill_line_unit_qty(
            tenant_id,
            items,
            quantity_field="delivery_quantity",
            scene_label="销售出库",
            unit_code_map=unit_code_map,
            config_unit_number=str(config.get("unit_number") or "").strip() or None,
        )
        model = build_kingdee_sales_delivery_model(
            delivery=delivery,
            items=items,
            cfg=config,
            customer_number=customer_number,
            warehouse_number=warehouse_number,
            line_unit_qty_by_item_id=line_unit_qty_by_item_id,
        )
        log_billentry_dual_qty(
            doc_label="销售出库",
            doc_code=delivery.delivery_code,
            entries=model.get("billentry") or [],
        )
        if not (model.get("billentry") or []) and not dry_run:
            raise BusinessLogicError("销售出库单无有效明细数量，无法推送")
        return config, form_id, model

    async def _push_now(
        self,
        *,
        tenant_id: int,
        delivery: SalesDelivery,
        items: List[SalesDeliveryItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        config, form_id, model = await self._prepare_kingdee_push_model(
            tenant_id=tenant_id,
            delivery=delivery,
            items=items,
            acting_user_id=acting_user_id,
            config=config,
            dry_run=dry_run,
        )

        request = DocumentPushRequest(
            source_type=SOURCE_TYPE,
            source_id=int(delivery.id),
            target_profile=TARGET_PROFILE,
            source_code=delivery.delivery_code,
            source_name=delivery.delivery_code,
            connection_code=str(config.get("connection_code") or "").strip() or None,
            save_api_uuid=str(config.get("save_api_uuid") or "").strip() or None,
            dry_run=dry_run,
        )
        prepared = DocumentPushPrepared(
            form_id=form_id,
            model=model,
            target_type=TARGET_TYPE,
            target_name="金蝶苍穹销售出库单",
            relation_desc="销售出库推送金蝶苍穹销售出库单",
            connector_type="kingdee_cosmic",
            config=config,
        )

        async def _persist(result: Dict[str, Any]) -> None:
            await DocumentRelation.create(
                tenant_id=tenant_id,
                source_type=str(result.get("source_type") or SOURCE_TYPE),
                source_id=int(result.get("source_id") or delivery.id),
                source_code=result.get("source_code") or delivery.delivery_code,
                source_name=result.get("source_name") or delivery.delivery_code,
                target_type=str(result.get("target_type") or TARGET_TYPE),
                target_id=int(result.get("bill_id") or 0),
                target_code=(result.get("bill_no") or None),
                target_name=str(result.get("target_name") or "金蝶苍穹销售出库单"),
                relation_type="source",
                relation_mode="push",
                relation_desc=str(
                    result.get("relation_desc") or "销售出库推送金蝶苍穹销售出库单"
                ),
                notes=to_api_isoformat(resolve_business_datetime()),
                created_by=acting_user_id,
            )

        return await DocumentPushPipeline().push(
            tenant_id=tenant_id,
            acting_user_id=acting_user_id,
            request=request,
            prepared=prepared,
            persist_relation=None if dry_run else _persist,
        )
