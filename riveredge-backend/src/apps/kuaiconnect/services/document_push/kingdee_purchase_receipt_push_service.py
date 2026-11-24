"""业务适配：采购入库单 → 金蝶云苍穹采购入库单新增（默认标品 add；自定义 add2 含验收人）。"""

from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
from apps.kuaiconnect.services.document_push.kingdee_push_location import (
    build_kingdee_location_number_by_item_id,
    kingdee_location_number_for_item,
    warehouse_number_by_item_id_from_wh_map,
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
    BIZ_IM_PURINBILL,
    IM_PURINBILL_ACCEPTOR_FIELD,
    IM_PURINBILL_ADD_PATH,
    IM_PURINBILL_BATCH_AUDIT_PATH,
    IM_PURINBILL_BATCH_SUBMIT_PATH,
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
from core.services.integration.kingdee_warehouse_push_routing import (
    PURCHASE_RECEIPT_ASSET_KEY,
    PURCHASE_RECEIPT_BASE_KEY,
    assert_purchase_receipt_asset_push_line_type_configured,
    finalize_purchase_receipt_asset_push_config,
    resolve_purchase_receipt_push_config,
    resolve_purchase_receipt_variant_key_from_order_type,
)
from apps.kuaiconnect.services.document_push.kingdee_im_batch_update_service import (
    kingdee_purchase_receipt_batch_update_linked_bill,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = BIZ_IM_PURINBILL
# 默认标品 add；自定义含验收人时在配置改 save_path=…/add2 且 acceptor_field=fd81_yanshou
DEFAULT_SAVE_PATH = IM_PURINBILL_ADD_PATH
DEFAULT_SUBMIT_PATH = IM_PURINBILL_BATCH_SUBMIT_PATH
DEFAULT_AUDIT_PATH = IM_PURINBILL_BATCH_AUDIT_PATH
TARGET_TYPE = "kingdee_im_purinbill"
TARGET_PROFILE = "kingdee_im_purinbill"
SOURCE_TYPE = "purchase_receipt"
PUSHABLE_STATUSES = frozenset({"已入库", "已完成", "processed", "COMPLETED", "POSTED"})
PUSH_DISABLED_MESSAGE = "金蝶采购入库推送未启用"


def purchase_receipt_push_skip_reason(
    receipt: PurchaseReceipt,
    *,
    already_pushed: bool = False,
    items: Optional[List[PurchaseReceiptItem]] = None,
) -> Optional[str]:
    from apps.kuaizhizao.constants.purchase_order_type import is_service_purchase_order_type

    if is_service_purchase_order_type(getattr(receipt, "order_type", None)):
        return "服务采购入库单不外推金蝶"
    if already_pushed:
        return "已推送过金蝶采购入库单"
    status = str(getattr(receipt, "status", None) or "").strip()
    status_upper = status.upper()
    if status not in PUSHABLE_STATUSES and status_upper not in PUSHABLE_STATUSES:
        return f"采购入库状态 {status or '-'} 不可推送（需已入库）"
    if items is not None and not items:
        return "采购入库单无明细行"
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


async def _resolve_supplier_number(
    tenant_id: int, receipt: PurchaseReceipt, cfg: Dict[str, Any]
) -> Optional[str]:
    configured = str(cfg.get("supplier_number") or "").strip()
    if configured:
        return configured
    try:
        from apps.master_data.models.supplier import Supplier

        supplier = await Supplier.get_or_none(
            tenant_id=tenant_id,
            id=int(receipt.supplier_id or 0),
            deleted_at__isnull=True,
        )
        if supplier and str(supplier.code or "").strip():
            return str(supplier.code).strip()
    except Exception as exc:
        logger.warning(
            "resolve supplier number failed receipt_id={} err={}", receipt.id, exc
        )
    return None


async def _resolve_warehouse_number(
    tenant_id: int,
    *,
    warehouse_id: Optional[int],
    cfg: Dict[str, Any],
) -> Optional[str]:
    """单据/行仓库优先；配置 warehouse_number 仅作未选仓时的缺省（不覆盖已选入库仓）。"""
    wh_id = int(warehouse_id or 0)
    if wh_id > 0:
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
    configured = str(cfg.get("warehouse_number") or cfg.get("stock_number") or "").strip()
    if configured:
        return configured
    return None


async def resolve_purchase_receipt_line_unit_qty(
    tenant_id: int,
    items: List[PurchaseReceiptItem],
    *,
    unit_code_map: Optional[Dict[str, Any]] = None,
    config_unit_number: Optional[str] = None,
) -> Dict[int, Dict[str, Any]]:
    """苍穹采购入库明细：库存单位/数量 + 辅助单位/数量（qtyunit2nd）。"""
    from apps.kuaiconnect.services.document_push.kingdee_warehouse_billentry_dual_qty import (
        resolve_warehouse_bill_line_unit_qty,
    )

    return await resolve_warehouse_bill_line_unit_qty(
        tenant_id,
        items,
        quantity_field="receipt_quantity",
        scene_label="采购入库",
        unit_code_map=unit_code_map,
        config_unit_number=config_unit_number,
    )


def build_kingdee_purchase_receipt_model(
    *,
    receipt: PurchaseReceipt,
    items: List[PurchaseReceiptItem],
    cfg: Optional[Dict[str, Any]] = None,
    supplier_number: Optional[str] = None,
    warehouse_numbers: Optional[Dict[int, Optional[str]]] = None,
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
    bill_date = _date_string(receipt.receipt_time or receipt.created_at)
    wh_map = warehouse_numbers or {}
    line_plan = line_unit_qty_by_item_id or {}

    entries: List[Dict[str, Any]] = []
    for item in items:
        planned = line_plan.get(int(item.id or 0)) or {}
        qty = _to_float(planned.get("qty", item.receipt_quantity))
        if qty <= 0:
            continue
        unit_number = (
            str(planned.get("unit_number") or "").strip()
            or str(config.get("unit_number") or DEFAULT_UNIT_NUMBER).strip()
            or DEFAULT_UNIT_NUMBER
        )
        line_wh = wh_map.get(int(item.id or 0)) or wh_map.get(0)
        entry: Dict[str, Any] = {
            "material_number": str(item.material_code or "").strip(),
            "qty": qty,
            "unit_number": unit_number,
            "invstatus_number": str(config.get("invstatus_number") or "").strip(),
            "invtype_number": str(config.get("invtype_number") or "").strip(),
            "linetype_number": str(config.get("linetype_number") or "").strip(),
        }
        from apps.kuaiconnect.services.document_push.kingdee_warehouse_billentry_dual_qty import (
            apply_billentry_dual_qty_fields,
        )

        apply_billentry_dual_qty_fields(entry, planned)
        if line_wh:
            entry["warehouse_number"] = line_wh
        location_number = kingdee_location_number_for_item(
            item, config, location_number_by_item_id
        )
        if location_number:
            entry["location_number"] = location_number
        if item.batch_number:
            entry["lotnumber"] = str(item.batch_number).strip()
        if item.manufacturing_date:
            entry["producedate"] = _date_string(item.manufacturing_date)
        if item.expiry_date:
            entry["expirydate"] = _date_string(item.expiry_date)
        if item.notes:
            entry["entrycomment"] = str(item.notes)
        # 价税以入库行金额为真源；库存单位数量换算后由金额反推单价，禁止用单据单位单价×库存数量重算。
        raw_tax = getattr(item, "tax_rate", None)
        if raw_tax is None:
            raw_tax = getattr(receipt, "tax_rate", None)
        if raw_tax is None:
            label = str(item.material_code or item.id or "")
            raise BusinessLogicError(f"采购入库明细缺少税率，无法推送金蝶：{label}")
        taxrate = _to_float(raw_tax)
        if not float(taxrate).is_integer():
            label = str(item.material_code or item.id or "")
            raise BusinessLogicError(
                f"采购入库明细税率 {taxrate} 无法对应金蝶税率编码：{label}"
            )
        taxrateid = f"V{int(taxrate)}"
        amount = _to_float(getattr(item, "total_amount", None))
        amountandtax = _to_float(getattr(item, "net_amount", None))
        if amount <= 0 or amountandtax <= 0:
            from apps.kuaizhizao.utils.document_line_amounts import calc_document_line_amounts

            doc_qty = _to_float(getattr(item, "receipt_quantity", None)) or qty
            display_raw = getattr(item, "display_unit_price", None)
            header_price_type = str(getattr(receipt, "price_type", None) or "tax_exclusive")
            if display_raw is not None and doc_qty > 0:
                excl, _tax, incl = calc_document_line_amounts(
                    Decimal(str(doc_qty)),
                    Decimal(str(display_raw)),
                    Decimal(str(taxrate)),
                    "tax_inclusive"
                    if header_price_type == "tax_inclusive"
                    else "tax_exclusive",
                )
                if amount <= 0:
                    amount = float(excl)
                if amountandtax <= 0:
                    amountandtax = float(incl)
            if amount <= 0:
                unit = _to_float(item.unit_price)
                if unit <= 0:
                    unit = _to_float(config.get("default_price"))
                if unit <= 0:
                    unit = 1.0
                amount = round(unit * doc_qty, 4)
            if amountandtax <= 0 and amount > 0 and doc_qty > 0:
                unit_excl = Decimal(str(amount)) / Decimal(str(doc_qty))
                price_type = (
                    "tax_inclusive"
                    if display_raw is not None
                    and Decimal(str(display_raw or 0)) > 0
                    and header_price_type == "tax_inclusive"
                    else "tax_exclusive"
                )
                unit_for_calc = (
                    Decimal(str(display_raw))
                    if price_type == "tax_inclusive"
                    else unit_excl
                )
                _excl, _tax, incl = calc_document_line_amounts(
                    Decimal(str(doc_qty)),
                    unit_for_calc,
                    Decimal(str(taxrate)),
                    price_type,
                )
                amountandtax = float(incl)
        amount = round(amount, 4)
        amountandtax = round(amountandtax, 4)
        if qty > 0 and amount > 0:
            price = round(amount / qty, 6)
        else:
            price = _to_float(item.unit_price)
            if price <= 0:
                price = _to_float(config.get("default_price"))
            if price <= 0:
                price = 1.0
        if qty > 0 and amountandtax > 0:
            priceandtax = round(amountandtax / qty, 6)
        else:
            priceandtax = round(price * (1 + taxrate / 100.0), 6)
        entry["price"] = price
        entry["amount"] = amount
        entry["taxrate"] = taxrate
        entry["taxrateid_number"] = taxrateid
        entry["priceandtax"] = priceandtax
        entry["amountandtax"] = amountandtax
        # 去掉空必填占位，避免把空串推给金蝶（配置缺失时由业务层报错）
        for key in ("invstatus_number", "invtype_number", "linetype_number"):
            if not entry.get(key):
                entry.pop(key, None)
        entries.append(entry)

    if entries:
        model["billentry"] = entries

    default_field_map = {
        "trdbillno": "trdbillno",
        "biztime": "biztime",
        "exratedate": "exratedate",
        "bookdate": "bookdate",
        "paymode": "paymode",
        "istax": "istax",
        "org_number": "org_number",
        "bizorg_number": "bizorg_number",
        "billtype_number": "billtype_number",
        "biztype_number": "biztype_number",
        "invscheme_number": "invscheme_number",
        "supplier_number": "supplier_number",
        "comment": "comment",
    }

    def local_value(key: str) -> Any:
        if key == "trdbillno":
            # 多租户共用连接时本地单号可撞；见 resolve_kingdee_local_bill_no。
            return resolve_kingdee_local_bill_no(
                config=config,
                local_code=receipt.receipt_code,
                org_number=org_number,
            )
        if key in {"biztime", "exratedate", "bookdate"}:
            return bill_date
        if key == "paymode":
            from apps.master_data.config.partner_settlement_codes import (
                kingdee_paymode_from_receipt_pay_mode,
            )

            mapped = kingdee_paymode_from_receipt_pay_mode(
                getattr(receipt, "pay_mode", None)
            )
            if mapped:
                return mapped
            return str(config.get("paymode") or "CREDIT").strip() or "CREDIT"
        if key == "istax":
            raw = config.get("istax")
            if raw is None:
                return True
            return bool(raw)
        if key == "org_number":
            return org_number
        if key == "bizorg_number":
            return str(config.get("bizorg_number") or org_number).strip()
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
        if key == "supplier_number":
            return supplier_number or config.get("supplier_number")
        if key == "comment":
            return _compact_text("从MES系统采购入库", receipt.receipt_code, receipt.notes)
        return getattr(receipt, key, None)

    apply_field_map(model, dict(default_field_map), local_value)

    # 采购员：单据工号优先，缺省才用租户配置（工号须在推送前按 buyer_id 重算，见 _push_now）
    doc_buyer = str(getattr(receipt, "buyer_operator_number", None) or "").strip()
    cfg_buyer = str(
        config.get("bizoperator_operatornumber") or config.get("buyer_operatornumber") or ""
    ).strip()
    buyer = doc_buyer or cfg_buyer
    if buyer:
        model["bizoperator_operatornumber"] = buyer
    buyer_group = str(
        config.get("bizoperatorgroup_number") or config.get("buyer_group_number") or ""
    ).strip()
    if buyer_group:
        model["bizoperatorgroup_number"] = buyer_group

    # 验收人：仅自定义 add2 时配置 acceptor_field（如 fd81_yanshou）才写入；单据 receiver_name 优先
    acceptor_field = str(config.get("acceptor_field") or "").strip()
    acceptor_text = str(
        getattr(receipt, "receiver_name", None)
        or config.get("acceptor_text")
        or config.get("acceptor")
        or getattr(receipt, "inspector_name", None)
        or getattr(receipt, "accepted_by_name", None)
        or ""
    ).strip()
    if acceptor_field and acceptor_text:
        model[acceptor_field] = acceptor_text
    elif acceptor_field and not acceptor_text:
        logger.warning(
            "采购入库推送缺少验收人文本 tenant=%s receipt=%s field=%s",
            getattr(receipt, "tenant_id", None),
            getattr(receipt, "receipt_code", None),
            acceptor_field,
        )

    # 库管员（operator_*）非必填：不主动写入，避免缺库管组导致保存失败

    fixed_values = config.get("fixed_values")
    if isinstance(fixed_values, dict):
        for target_path, value in fixed_values.items():
            path = str(target_path)
            # 单据已有采购员时，禁止 fixed_values 把工号盖回旧配置
            if doc_buyer and path in {
                "bizoperator_operatornumber",
                "bizoperator.operatornumber",
            }:
                continue
            set_path(model, path, value)

    return model


class KingdeePurchaseReceiptPushService:
    TARGET_PROFILE = TARGET_PROFILE

    async def push_purchase_receipt(
        self,
        *,
        tenant_id: int,
        purchase_receipt_id: int,
        acting_user_id: int,
        connection_code: Optional[str] = None,
        save_api_uuid: Optional[str] = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        receipt = await PurchaseReceipt.get_or_none(
            tenant_id=tenant_id,
            id=purchase_receipt_id,
            deleted_at__isnull=True,
        )
        if not receipt:
            return None

        items = await PurchaseReceiptItem.filter(
            tenant_id=tenant_id,
            receipt_id=purchase_receipt_id,
            deleted_at__isnull=True,
        ).order_by("id")
        early_skip = purchase_receipt_push_skip_reason(receipt, items=list(items))
        if early_skip:
            return {"success": True, "skipped": True, "message": early_skip}

        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        config = await resolve_purchase_receipt_push_config(
            tenant_id,
            warehouse,
            material_ids=[int(it.material_id) for it in items if getattr(it, "material_id", None)],
            order_type=getattr(receipt, "order_type", None),
        )
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

        prior_push_count = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=purchase_receipt_id,
            target_type=TARGET_TYPE,
        ).count()
        already_pushed = prior_push_count > 0
        # force=True：人工重新推送，跳过「已推送」拦截；静默自动推送勿传 force
        skip_reason = purchase_receipt_push_skip_reason(
            receipt,
            already_pushed=already_pushed and not force,
            items=list(items),
        )
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        try:
            return await self._push_now(
                tenant_id=tenant_id,
                receipt=receipt,
                items=list(items),
                acting_user_id=acting_user_id,
                config=config,
                dry_run=dry_run,
                prior_push_count=prior_push_count,
            )
        except Exception as exc:
            logger.warning(
                "采购入库推送金蝶苍穹失败 tenant_id={} purchase_receipt_id={} err={}",
                tenant_id,
                purchase_receipt_id,
                exc,
            )
            if bool(config.get("fail_on_error", False)):
                raise BusinessLogicError(f"推送金蝶采购入库失败：{exc}")
            return {
                "success": False,
                "source_type": SOURCE_TYPE,
                "source_id": int(purchase_receipt_id),
                "target_profile": TARGET_PROFILE,
                "message": str(exc),
            }

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        return merge_warehouse_kingdee_push_config(warehouse, PURCHASE_RECEIPT_BASE_KEY)

    async def _apply_add2_acceptor_field(
        self, tenant_id: int, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        out = dict(config)
        if str(out.get("acceptor_field") or "").strip():
            return out
        save_path = str(out.get("save_path") or "").lower()
        if "add2" in save_path:
            out["acceptor_field"] = IM_PURINBILL_ACCEPTOR_FIELD
            return out
        api_uuid = str(out.get("save_api_uuid") or "").strip()
        if not api_uuid:
            return out
        from core.models.api import API

        api_obj = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
        if api_obj and "add2" in str(api_obj.path or "").lower():
            out["acceptor_field"] = IM_PURINBILL_ACCEPTOR_FIELD
        return out

    async def batch_update_linked_kingdee_bill(
        self,
        *,
        tenant_id: int,
        receipt: PurchaseReceipt,
        items: List[PurchaseReceiptItem],
        acting_user_id: int,
        relation: DocumentRelation,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        async def _prepare(merged: Dict[str, Any]) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
            return await self._prepare_kingdee_push_model(
                tenant_id=tenant_id,
                receipt=receipt,
                items=items,
                acting_user_id=acting_user_id,
                config=merged,
                dry_run=dry_run,
            )

        return await kingdee_purchase_receipt_batch_update_linked_bill(
            tenant_id=tenant_id,
            receipt_id=int(receipt.id),
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
        receipt: PurchaseReceipt,
        items: List[PurchaseReceiptItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
        config = {
            **config,
            "form_id": str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID,
        }
        config = await enrich_kingdee_warehouse_push_config(tenant_id, config)
        config = await self._apply_add2_acceptor_field(tenant_id, config)
        variant_key = resolve_purchase_receipt_variant_key_from_order_type(
            getattr(receipt, "order_type", None)
        )
        if variant_key == PURCHASE_RECEIPT_ASSET_KEY:
            biz_config = await BusinessConfigService().get_business_config(tenant_id)
            warehouse = (biz_config.get("parameters") or {}).get("warehouse") or {}
            config = finalize_purchase_receipt_asset_push_config(
                config,
                warehouse,
                variant_key=variant_key,
            )
        assert_purchase_receipt_asset_push_line_type_configured(
            config,
            order_type=getattr(receipt, "order_type", None),
        )
        form_id = str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID
        save_path = str(config.get("save_path") or DEFAULT_SAVE_PATH).strip() or DEFAULT_SAVE_PATH

        required_cfg = (
            "org_number",
            "billtype_number",
            "biztype_number",
            "invscheme_number",
            "invstatus_number",
            "invtype_number",
            "linetype_number",
        )
        # billtype_number 也可写 bill_type_number；invscheme 允许 inwscheme_number 别名
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
            bound_api = str(config.get("save_api_uuid") or "").strip()
            where = (
                f"当前绑定 Save 接口 {bound_api}"
                if bound_api
                else "当前未绑定 Save 接口"
            )
            raise BusinessLogicError(
                "金蝶采购入库推送缺少配置：" + "、".join(missing)
                + "（业务配置 parameters.warehouse.kingdee_purchase_receipt_push，"
                + f"{where}。接口样例里的 REPLACE_ 占位会被跳过，须写成该账套真实编码）"
            )

        supplier_number = await _resolve_supplier_number(tenant_id, receipt, config)
        if not supplier_number and not dry_run:
            raise BusinessLogicError("缺少供应商编码，无法推送金蝶采购入库单")

        header_wh = await _resolve_warehouse_number(
            tenant_id, warehouse_id=receipt.warehouse_id, cfg=config
        )
        wh_map: Dict[int, Optional[str]] = {0: header_wh}
        for item in items:
            line_wh_id = int(item.warehouse_id or receipt.warehouse_id or 0)
            wh_map[int(item.id or 0)] = await _resolve_warehouse_number(
                tenant_id, warehouse_id=line_wh_id, cfg=config
            ) or header_wh

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
            allow_builtin_aliases=False,
        )
        config = finalize_kingdee_warehouse_im_push_config(
            {
                **config,
                **units,
                "api_unit_code_map": unit_code_map,
                "save_path": save_path,
            },
            default_submit_path=DEFAULT_SUBMIT_PATH,
            default_audit_path=DEFAULT_AUDIT_PATH,
        )

        line_unit_qty_by_item_id = await resolve_purchase_receipt_line_unit_qty(
            tenant_id,
            items,
            unit_code_map=unit_code_map,
            config_unit_number=str(config.get("unit_number") or "").strip() or None,
        )
        location_number_by_item_id = await build_kingdee_location_number_by_item_id(
            tenant_id,
            items,
            config,
            warehouse_number_by_item_id=warehouse_number_by_item_id_from_wh_map(items, wh_map),
        )
        # 外推前按当前采购员重算工号，避免编辑后仍推上一任的 buyer_operator_number
        from apps.kuaizhizao.utils.kingdee_warehouse_operator_utils import (
            resolve_document_operator_number,
        )

        resolved_buyer_op = await resolve_document_operator_number(
            tenant_id,
            getattr(receipt, "buyer_id", None),
            explicit=getattr(receipt, "buyer_operator_number", None),
        )
        if resolved_buyer_op != getattr(receipt, "buyer_operator_number", None):
            receipt.buyer_operator_number = resolved_buyer_op
            await PurchaseReceipt.filter(tenant_id=tenant_id, id=int(receipt.id)).update(
                buyer_operator_number=resolved_buyer_op
            )
        model = build_kingdee_purchase_receipt_model(
            receipt=receipt,
            items=items,
            cfg=config,
            supplier_number=supplier_number,
            warehouse_numbers=wh_map,
            location_number_by_item_id=location_number_by_item_id,
            line_unit_qty_by_item_id=line_unit_qty_by_item_id,
        )
        from apps.kuaiconnect.services.document_push.kingdee_warehouse_billentry_dual_qty import (
            log_billentry_dual_qty,
        )

        log_billentry_dual_qty(
            doc_label="purchase_receipt",
            doc_code=receipt.receipt_code,
            entries=model.get("billentry") or [],
        )
        if not (model.get("billentry") or []) and not dry_run:
            raise BusinessLogicError("采购入库单无有效明细数量，无法推送")

        acceptor_field = str(config.get("acceptor_field") or "").strip()
        if acceptor_field and not dry_run:
            acceptor_text = str(
                getattr(receipt, "receiver_name", None)
                or config.get("acceptor_text")
                or config.get("acceptor")
                or ""
            ).strip()
            if not acceptor_text:
                raise BusinessLogicError(
                    "采购入库推送金蝶须填写验收人（入库单 receiver_name 或业务配置 acceptor_text），"
                    "否则保存后无法提交到已审核"
                )
        return config, form_id, model

    async def _push_now(
        self,
        *,
        tenant_id: int,
        receipt: PurchaseReceipt,
        items: List[PurchaseReceiptItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
        prior_push_count: int = 0,
    ) -> Dict[str, Any]:
        push_seq = int(prior_push_count or 0) + 1
        is_repush = push_seq > 1
        relation_desc = (
            f"采购入库二次推送金蝶苍穹采购入库单（第{push_seq}次）"
            if is_repush
            else "采购入库推送金蝶苍穹采购入库单"
        )
        config, form_id, model = await self._prepare_kingdee_push_model(
            tenant_id=tenant_id,
            receipt=receipt,
            items=items,
            acting_user_id=acting_user_id,
            config=config,
            dry_run=dry_run,
        )

        request = DocumentPushRequest(
            source_type=SOURCE_TYPE,
            source_id=int(receipt.id),
            target_profile=TARGET_PROFILE,
            source_code=receipt.receipt_code,
            source_name=receipt.receipt_code,
            connection_code=str(config.get("connection_code") or "").strip() or None,
            save_api_uuid=str(config.get("save_api_uuid") or "").strip() or None,
            dry_run=dry_run,
        )
        prepared = DocumentPushPrepared(
            form_id=form_id,
            model=model,
            target_type=TARGET_TYPE,
            target_name="金蝶苍穹采购入库单",
            relation_desc=relation_desc,
            connector_type="kingdee_cosmic",
            config=config,
        )

        async def _persist(result: Dict[str, Any]) -> None:
            await DocumentRelation.create(
                tenant_id=tenant_id,
                source_type=str(result.get("source_type") or SOURCE_TYPE),
                source_id=int(result.get("source_id") or receipt.id),
                source_code=result.get("source_code") or receipt.receipt_code,
                source_name=result.get("source_name") or receipt.receipt_code,
                target_type=str(result.get("target_type") or TARGET_TYPE),
                target_id=int(result.get("bill_id") or 0),
                target_code=(result.get("bill_no") or None),
                target_name=str(result.get("target_name") or "金蝶苍穹采购入库单"),
                relation_type="source",
                relation_mode="push",
                relation_desc=str(result.get("relation_desc") or relation_desc),
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
