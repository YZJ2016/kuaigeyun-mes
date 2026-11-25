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
from apps.kuaiconnect.services.document_push.kingdee_push_location import (
    build_kingdee_location_number_by_item_id,
    kingdee_location_number_for_item,
)
from core.services.integration.document_push_codes import (
    DEFAULT_UNIT_NUMBER,
    load_save_api_unit_code_map,
    resolve_unit_for_push,
)
from core.services.integration.document_push_mapping import (
    apply_field_map,
    resolve_kingdee_local_bill_no,
    set_path,
)
from core.services.integration.document_push_pipeline import (
    DocumentPushPipeline,
    DocumentPushPrepared,
    DocumentPushRequest,
)
from core.services.integration.kingdee_cosmic_api_presets import (
    BIZ_IM_SALOUTBILL,
    IM_SALOUTBILL_BATCH_ADD_PATH,
    IM_SALOUTBILL_BATCH_AUDIT_PATH,
    IM_SALOUTBILL_BATCH_SUBMIT_PATH,
)
from core.utils.timezone_utils import (
    resolve_business_datetime,
    to_api_isoformat,
    to_site_date,
    today_site_str,
)
from core.services.integration.kingdee_warehouse_document_push_config import (
    enrich_kingdee_warehouse_push_config,
    finalize_kingdee_warehouse_im_push_config,
    merge_warehouse_kingdee_push_config,
)
from apps.kuaiconnect.services.document_push.kingdee_im_batch_update_service import (
    kingdee_im_batch_update_linked_bill,
    relation_branch_should_batch_update,
)
from apps.kuaiconnect.services.document_push.kingdee_im_warehouse_revoke_service import (
    SALES_DELIVERY_REVOKE_SPEC,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = BIZ_IM_SALOUTBILL
DEFAULT_SAVE_PATH = IM_SALOUTBILL_BATCH_ADD_PATH
DEFAULT_SUBMIT_PATH = IM_SALOUTBILL_BATCH_SUBMIT_PATH
DEFAULT_AUDIT_PATH = IM_SALOUTBILL_BATCH_AUDIT_PATH
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


async def _hydrate_sales_delivery_item_material_codes(
    tenant_id: int, items: List[SalesDeliveryItem]
) -> None:
    """推送前按 material_id 回填空的编码/名称/单位（与仓储详情 hydrate 一致）。"""
    need_ids = {
        int(item.material_id)
        for item in items
        if int(getattr(item, "material_id", 0) or 0) > 0
        and (
            not str(getattr(item, "material_code", "") or "").strip()
            or not str(getattr(item, "material_name", "") or "").strip()
            or not str(getattr(item, "material_unit", "") or "").strip()
        )
    }
    if not need_ids:
        return
    try:
        from apps.master_data.models.material import Material

        materials = await Material.filter(tenant_id=tenant_id, id__in=list(need_ids)).all()
    except Exception as exc:
        logger.warning("hydrate sales delivery material codes failed err={}", exc)
        return
    by_id = {int(m.id): m for m in materials}
    for item in items:
        mid = int(getattr(item, "material_id", 0) or 0)
        material = by_id.get(mid)
        if not material:
            continue
        if not str(getattr(item, "material_code", "") or "").strip():
            code = str(
                getattr(material, "main_code", None) or getattr(material, "code", "") or ""
            ).strip()
            if code:
                item.material_code = code
        if not str(getattr(item, "material_name", "") or "").strip():
            name = str(getattr(material, "name", None) or "").strip()
            if name:
                item.material_name = name
        if not str(getattr(item, "material_unit", "") or "").strip():
            unit = str(getattr(material, "base_unit", None) or "").strip()
            if unit:
                item.material_unit = unit


async def _assert_sales_delivery_batch_for_push(
    tenant_id: int, items: List[SalesDeliveryItem]
) -> None:
    """本地启用批号管理的物料推送前必须有批号（苍穹 lotnumber）。"""
    need_ids = {
        int(item.material_id)
        for item in items
        if _to_float(getattr(item, "delivery_quantity", 0)) > 0
        and int(getattr(item, "material_id", 0) or 0) > 0
        and not str(getattr(item, "batch_number", "") or "").strip()
    }
    if not need_ids:
        return
    from apps.master_data.models.material import Material

    materials = await Material.filter(tenant_id=tenant_id, id__in=list(need_ids)).all()
    by_id = {int(m.id): m for m in materials}
    missing: List[str] = []
    for item in items:
        if _to_float(getattr(item, "delivery_quantity", 0)) <= 0:
            continue
        if str(getattr(item, "batch_number", "") or "").strip():
            continue
        material = by_id.get(int(getattr(item, "material_id", 0) or 0))
        if material is None or not bool(getattr(material, "batch_managed", False)):
            continue
        label = (
            str(getattr(item, "material_code", "") or "").strip()
            or str(getattr(material, "main_code", "") or "").strip()
            or str(getattr(material, "name", "") or "").strip()
            or str(getattr(item, "material_id", ""))
        )
        missing.append(label)
    if missing:
        raise BusinessLogicError(
            "以下物料已启用批号管理，推送金蝶前请在出库明细填写批号："
            + "、".join(missing)
        )

def build_kingdee_sales_delivery_model(
    *,
    delivery: SalesDelivery,
    items: List[SalesDeliveryItem],
    cfg: Optional[Dict[str, Any]] = None,
    customer_number: Optional[str] = None,
    warehouse_number: Optional[str] = None,
    warehouse_number_by_item_id: Optional[Dict[int, str]] = None,
    location_number_by_item_id: Optional[Dict[int, str]] = None,
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
    line_plan = line_unit_qty_by_item_id or {}

    entries: List[Dict[str, Any]] = []
    for item in items:
        planned = line_plan.get(int(item.id or 0)) or {}
        qty = _to_float(planned.get("qty", item.delivery_quantity))
        if qty <= 0:
            continue
        material_number = str(item.material_code or "").strip()
        if not material_number:
            # 空编码推上去苍穹只会报 billentry.material_number 必填，此处跳过由外层汇总报错
            continue
        unit_number = (
            str(planned.get("unit_number") or "").strip()
            or str(config.get("unit_number") or DEFAULT_UNIT_NUMBER).strip()
            or DEFAULT_UNIT_NUMBER
        )
        entry: Dict[str, Any] = {
            "material_number": material_number,
            "qty": qty,
            "unit_number": unit_number,
            "linetype_number": str(config.get("linetype_number") or "").strip(),
            "discounttype": discounttype,
        }
        from apps.kuaiconnect.services.document_push.kingdee_warehouse_billentry_dual_qty import (
            apply_billentry_dual_qty_fields,
    restate_entry_prices_for_inventory_qty,
)

        apply_billentry_dual_qty_fields(entry, planned)
        line_map = warehouse_number_by_item_id or {}
        item_id = int(getattr(item, "id", 0) or 0)
        entry_warehouse = (
            str(line_map.get(item_id) or "").strip()
            or str(warehouse_number or "").strip()
        )
        if entry_warehouse:
            entry["warehouse_number"] = entry_warehouse
        if settle_org:
            entry["entrysettleorg_number"] = settle_org
        location_number = kingdee_location_number_for_item(
            item, config, location_number_by_item_id
        )
        if location_number:
            entry["location_number"] = location_number
        if item.batch_number:
            entry["lotnumber"] = str(item.batch_number).strip()
        if item.expiry_date:
            entry["expirydate"] = _date_string(item.expiry_date)
        if item.notes:
            entry["entrycomment"] = str(item.notes)
        if bool(getattr(item, "is_gift", False)):
            entry["ispresent"] = True
        invstatus = str(
            config.get("invstatus_number") or config.get("outinvstatus_number") or ""
        ).strip()
        invtype = str(
            config.get("invtype_number") or config.get("outinvtype_number") or ""
        ).strip()
        if invstatus:
            entry["invstatus_number"] = invstatus
        if invtype:
            entry["invtype_number"] = invtype
        out_invstatus = str(config.get("outinvstatus_number") or invstatus or "").strip()
        out_invtype = str(config.get("outinvtype_number") or invtype or "").strip()
        if out_invstatus:
            entry["outinvstatus_number"] = out_invstatus
        if out_invtype:
            entry["outinvtype_number"] = out_invtype
        # 价税以出库单行为真源。税率缺失则失败，不用连接器配置里的 13 代替单据。
        from decimal import Decimal

        from apps.kuaizhizao.constants.price_type import normalize_price_type
        from apps.kuaizhizao.utils.sales_price_amount import calc_sales_line_amounts

        raw_tax = getattr(item, "tax_rate", None)
        if raw_tax is None:
            label = str(getattr(item, "material_code", "") or getattr(item, "id", ""))
            raise BusinessLogicError(f"销售出库明细缺少税率，无法推送金蝶：{label}")
        taxrate = _to_float(raw_tax)
        if not float(taxrate).is_integer():
            label = str(getattr(item, "material_code", "") or getattr(item, "id", ""))
            raise BusinessLogicError(
                f"销售出库明细税率 {taxrate} 无法对应金蝶税率编码：{label}"
            )
        price = _to_float(item.unit_price)
        if price <= 0 and not bool(getattr(item, "is_gift", False)):
            price = _to_float(config.get("default_price"))
        if price <= 0 and not bool(getattr(item, "is_gift", False)):
            price = 1.0
        price_type = normalize_price_type(getattr(delivery, "price_type", None))
        excl_amt, _, incl_amt = calc_sales_line_amounts(
            Decimal(str(qty)),
            Decimal(str(price)),
            Decimal(str(taxrate)),
            price_type,
        )
        if price_type == "tax_inclusive":
            entry_price = round(float(excl_amt) / qty, 2) if qty else 0
            entry_amount = round(float(excl_amt), 2)
            entry_price_tax = price
            entry_amount_tax = round(float(incl_amt), 2)
        else:
            entry_price = price
            entry_amount = round(float(excl_amt), 2)
            entry_price_tax = round(float(incl_amt) / qty, 2) if qty else 0
            entry_amount_tax = round(float(incl_amt), 2)
        entry["price"] = entry_price
        entry["amount"] = entry_amount
        entry["taxrate"] = taxrate
        entry["taxrateid_number"] = f"V{int(taxrate)}"
        entry["priceandtax"] = entry_price_tax
        entry["amountandtax"] = entry_amount_tax
        restate_entry_prices_for_inventory_qty(
            entry,
            document_qty=_to_float(item.delivery_quantity) or qty,
            unit_price=price,
            amount=entry_amount,
            amount_and_tax=entry_amount_tax,
        )
        if not entry.get("linetype_number"):
            entry.pop("linetype_number", None)
        entries.append(entry)

    if entries:
        model["billentry"] = entries

    currency = str(
        config.get("settlecurrency_number")
        or config.get("currency_number")
        or delivery.currency_code
        or "CNY"
    ).strip() or "CNY"
    exchange_rate = _to_float(config.get("exchangerate"))
    if exchange_rate <= 0:
        exchange_rate = _to_float(delivery.exchange_rate) or 1.0
    exratetable = str(config.get("exratetable_number") or "").strip()

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
        "settlecurrency_number": "settlecurrency_number",
        "exratetable_number": "exratetable_number",
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
            return resolve_kingdee_local_bill_no(
                config=config,
                local_code=delivery.delivery_code,
                org_number=org_number,
            )
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
        if key == "settlecurrency_number":
            return currency
        if key == "exratetable_number":
            return exratetable or None
        if key == "org_number":
            return org_number
        if key == "bizorg_number":
            return str(config.get("bizorg_number") or org_number).strip()
        if key == "bizdept_number":
            # 开放平台销售部门非必填；勿用组织编码冒充部门（苍穹会报「销售部门数据不存在」）
            dept = str(config.get("bizdept_number") or "").strip()
            return dept or None
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
            return _compact_text("从MES系统销售出库", delivery.delivery_code, delivery.notes)
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

        relation = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=sales_delivery_id,
            target_type=TARGET_TYPE,
        ).first()
        already_pushed = relation is not None
        skip_reason = sales_delivery_push_skip_reason(
            delivery,
            already_pushed=False,
            items=list(items),
        )
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        if already_pushed and relation is not None:
            status = str(getattr(delivery, "status", None) or "").strip()
            try:
                if relation_branch_should_batch_update(status):
                    return await self.batch_update_linked_kingdee_bill(
                        tenant_id=tenant_id,
                        delivery=delivery,
                        items=list(items),
                        acting_user_id=acting_user_id,
                        relation=relation,
                        config=config,
                        dry_run=dry_run,
                    )
                return await self._kingdee_submit_audit_only(
                    tenant_id=tenant_id,
                    config=config,
                    relation=relation,
                    dry_run=dry_run,
                )
            except Exception as exc:
                logger.warning(
                    "销售出库补提交/审核金蝶失败 tenant_id={} sales_delivery_id={} err={}",
                    tenant_id,
                    sales_delivery_id,
                    exc,
                )
                if bool(config.get("fail_on_error", False)):
                    raise BusinessLogicError(f"金蝶销售出库补提交/审核失败：{exc}")
                return {"success": False, "message": str(exc)}

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
        return merge_warehouse_kingdee_push_config(warehouse, "kingdee_sales_delivery_push")

    async def _kingdee_submit_audit_only(
        self,
        *,
        tenant_id: int,
        config: Dict[str, Any],
        relation: DocumentRelation,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """已有关联时只调 batchSubmit / batchAudit（修复金蝶仍暂存/已提交未审核）。"""
        config = {
            **config,
            "form_id": str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID,
        }
        config = await enrich_kingdee_warehouse_push_config(tenant_id, config)
        config = finalize_kingdee_warehouse_im_push_config(
            config,
            default_submit_path=DEFAULT_SUBMIT_PATH,
            default_audit_path=DEFAULT_AUDIT_PATH,
            default_body_wrap="data_list",
        )
        bill_no = str(relation.target_code or "").strip()
        bill_id = int(relation.target_id or 0)
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "message": f"将补金蝶提交/审核 bill_no={bill_no or bill_id}",
                "bill_no": bill_no,
                "bill_id": bill_id,
            }
        return await DocumentPushPipeline().cosmic_im_submit_audit_only(
            tenant_id=tenant_id,
            connector_type="kingdee_cosmic",
            config=config,
            form_id=str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID,
            bill_id=bill_id,
            bill_no=bill_no,
            source_type=SOURCE_TYPE,
            source_id=int(getattr(relation, "source_id", 0) or 0),
            target_profile=TARGET_PROFILE,
        )

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
        config = {
            **config,
            "form_id": str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID,
        }
        config = await enrich_kingdee_warehouse_push_config(tenant_id, config)
        form_id = str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID
        save_path = str(config.get("save_path") or DEFAULT_SAVE_PATH).strip() or DEFAULT_SAVE_PATH

        required_cfg = (
            "org_number",
            "billtype_number",
            "biztype_number",
            "invscheme_number",
            "linetype_number",
            "exratetable_number",
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
                + "（业务配置 parameters.warehouse.kingdee_sales_delivery_push；"
                "其中 exratetable_number 为本环境汇率表编码，也可写在接口库样例头字段）"
            )

        customer_number = await _resolve_customer_number(tenant_id, delivery, config)
        if not customer_number and not dry_run:
            raise BusinessLogicError("缺少客户编码，无法推送金蝶销售出库单")

        warehouse_number = await _resolve_warehouse_number(
            tenant_id, warehouse_id=delivery.warehouse_id, cfg=config
        )
        warehouse_number_by_item_id: Dict[int, str] = {}
        for item in items:
            item_id = int(getattr(item, "id", 0) or 0)
            if item_id <= 0:
                continue
            line_wh_id = getattr(item, "warehouse_id", None)
            resolved = None
            if line_wh_id and int(line_wh_id) > 0:
                resolved = await _resolve_warehouse_number(
                    tenant_id, warehouse_id=int(line_wh_id), cfg=config
                )
            if not resolved:
                resolved = warehouse_number
            if resolved:
                warehouse_number_by_item_id[item_id] = resolved
        if not warehouse_number and not warehouse_number_by_item_id and not dry_run:
            raise BusinessLogicError("缺少仓库编码，无法推送金蝶销售出库单")
        missing_line_wh = [
            str(getattr(item, "material_code", "") or getattr(item, "id", ""))
            for item in items
            if _to_float(item.delivery_quantity) > 0
            and not warehouse_number_by_item_id.get(int(getattr(item, "id", 0) or 0))
        ]
        if missing_line_wh and not dry_run:
            raise BusinessLogicError(
                "以下出库明细缺少仓库编码，无法推送金蝶：" + "、".join(missing_line_wh)
            )

        await _hydrate_sales_delivery_item_material_codes(tenant_id, items)
        missing_material = [
            str(getattr(item, "id", "") or "")
            for item in items
            if _to_float(item.delivery_quantity) > 0
            and not str(getattr(item, "material_code", "") or "").strip()
        ]
        if missing_material and not dry_run:
            raise BusinessLogicError(
                "销售出库明细缺少物料编码，无法推送金蝶（请检查明细物料主数据编码）"
            )
        if not dry_run:
            await _assert_sales_delivery_batch_for_push(tenant_id, items)

        first_code = next(
            (str(i.material_code).strip() for i in items if str(i.material_code or "").strip()),
            None,
        )
        first_unit = str(getattr(items[0], "material_unit", None) or "").strip() if items else ""
        unit_code_map = await load_save_api_unit_code_map(
            tenant_id, str(config.get("save_api_uuid") or "").strip() or None
        )
        units = await resolve_unit_for_push(
            tenant_id,
            product_code=first_code,
            unit_hint=first_unit or None,
            unit_code_map=unit_code_map,
            allow_builtin_aliases=False,
        )
        from apps.kuaiconnect.services.document_push.kingdee_warehouse_billentry_dual_qty import (
            log_billentry_dual_qty,
            resolve_warehouse_bill_line_unit_qty,
        )

        line_unit_qty_by_item_id = await resolve_warehouse_bill_line_unit_qty(
            tenant_id,
            items,
            quantity_field="delivery_quantity",
            scene_label="销售出库",
            unit_code_map=unit_code_map,
            config_unit_number=str(config.get("unit_number") or "").strip() or None,
        )
        # 结算币别：配置 / 单据币种 / CNY（开放平台字段名 settlecurrency_number）
        settle_currency = str(
            config.get("settlecurrency_number")
            or config.get("currency_number")
            or getattr(delivery, "currency_code", None)
            or "CNY"
        ).strip() or "CNY"
        config = finalize_kingdee_warehouse_im_push_config(
            {
                **config,
                **units,
                "api_unit_code_map": unit_code_map,
                "save_path": save_path,
                "settlecurrency_number": settle_currency,
                "currency_number": str(config.get("currency_number") or settle_currency).strip()
                or settle_currency,
            },
            default_submit_path=DEFAULT_SUBMIT_PATH,
            default_audit_path=DEFAULT_AUDIT_PATH,
            default_body_wrap="data_list",
        )

        location_number_by_item_id = await build_kingdee_location_number_by_item_id(
            tenant_id,
            items,
            config,
            warehouse_number_by_item_id=warehouse_number_by_item_id,
            default_warehouse_number=warehouse_number,
        )
        model = build_kingdee_sales_delivery_model(
            delivery=delivery,
            items=items,
            cfg=config,
            customer_number=customer_number,
            warehouse_number=warehouse_number,
            warehouse_number_by_item_id=warehouse_number_by_item_id,
            location_number_by_item_id=location_number_by_item_id,
            line_unit_qty_by_item_id=line_unit_qty_by_item_id,
        )
        log_billentry_dual_qty(
            doc_label="销售出库",
            doc_code=delivery.delivery_code,
            entries=model.get("billentry") or [],
        )
        if not (model.get("billentry") or []) and not dry_run:
            raise BusinessLogicError("销售出库单无有效明细数量或物料编码，无法推送")
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
