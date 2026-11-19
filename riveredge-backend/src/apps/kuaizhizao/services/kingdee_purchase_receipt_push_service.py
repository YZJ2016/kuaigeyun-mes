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
    BIZ_IM_PURINBILL,
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


def build_kingdee_purchase_receipt_model(
    *,
    receipt: PurchaseReceipt,
    items: List[PurchaseReceiptItem],
    cfg: Optional[Dict[str, Any]] = None,
    supplier_number: Optional[str] = None,
    warehouse_numbers: Optional[Dict[int, Optional[str]]] = None,
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

    entries: List[Dict[str, Any]] = []
    unit_map = (
        config.get("api_unit_code_map")
        if isinstance(config.get("api_unit_code_map"), dict)
        else None
    )
    for item in items:
        qty = _to_float(item.receipt_quantity)
        if qty <= 0:
            continue
        unit_raw = str(item.material_unit or "").strip()
        unit_number = (
            apply_unit_code_map(unit_raw, unit_map)
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
        if line_wh:
            entry["warehouse_number"] = line_wh
        location_number = str(
            item.location_code
            or config.get("location_number")
            or config.get("location_code")
            or ""
        ).strip()
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
        # 提交/审核要求明细金额、税率；单据头税率优先，其次配置缺省
        price = _to_float(item.unit_price)
        if price <= 0:
            price = _to_float(config.get("default_price"))
        if price <= 0:
            price = 1.0
        amount = _to_float(item.total_amount) or round(price * qty, 4)
        taxrate = _to_float(getattr(receipt, "tax_rate", None))
        if taxrate <= 0:
            taxrate = _to_float(config.get("taxrate"))
        if taxrate <= 0:
            taxrate = 13.0
        taxrateid = str(config.get("taxrateid_number") or "").strip()
        if not taxrateid:
            taxrateid = f"V{int(taxrate)}" if float(taxrate).is_integer() else "V13"
        taxrateid = taxrateid or "V13"
        priceandtax = round(price * (1 + taxrate / 100.0), 6)
        amountandtax = round(amount * (1 + taxrate / 100.0), 4)
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
            if config.get("use_local_bill_no", True):
                return receipt.receipt_code
            return None
        if key in {"biztime", "exratedate", "bookdate"}:
            return bill_date
        if key == "paymode":
            return (
                str(getattr(receipt, "pay_mode", None) or "").strip()
                or config.get("paymode")
                or "CREDIT"
            )
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
            return _compact_text("快格云采购入库", receipt.receipt_code, receipt.notes)
        return getattr(receipt, key, None)

    apply_field_map(model, dict(default_field_map), local_value)

    # 采购员：供应链业务员（传工号/编码；单据 buyer_operator_number 优先于租户配置）
    buyer = str(
        getattr(receipt, "buyer_operator_number", None)
        or config.get("bizoperator_operatornumber")
        or config.get("buyer_operatornumber")
        or ""
    ).strip()
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
            set_path(model, str(target_path), value)

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

        already_pushed = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=purchase_receipt_id,
            target_type=TARGET_TYPE,
        ).exists()
        skip_reason = purchase_receipt_push_skip_reason(
            receipt,
            already_pushed=already_pushed,
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
            return {"success": False, "message": str(exc)}

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        raw = warehouse.get("kingdee_purchase_receipt_push") or {}
        return dict(raw) if isinstance(raw, dict) else {}

    async def _push_now(
        self,
        *,
        tenant_id: int,
        receipt: PurchaseReceipt,
        items: List[PurchaseReceiptItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
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
            raise BusinessLogicError(
                "金蝶采购入库推送缺少配置：" + "、".join(missing)
                + "（业务配置 parameters.warehouse.kingdee_purchase_receipt_push）"
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
        )
        config = {
            **config,
            **units,
            "api_unit_code_map": unit_code_map,
            "save_path": save_path,
        }

        model = build_kingdee_purchase_receipt_model(
            receipt=receipt,
            items=items,
            cfg=config,
            supplier_number=supplier_number,
            warehouse_numbers=wh_map,
        )
        if not (model.get("billentry") or []) and not dry_run:
            raise BusinessLogicError("采购入库单无有效明细数量，无法推送")

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
            relation_desc="采购入库推送金蝶苍穹采购入库单",
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
                relation_desc=str(
                    result.get("relation_desc") or "采购入库推送金蝶苍穹采购入库单"
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
