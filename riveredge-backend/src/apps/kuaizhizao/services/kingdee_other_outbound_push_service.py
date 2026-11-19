"""业务适配：其他出库单 → 金蝶云苍穹其他出库单批量新增（im_otheroutbill/batchAdd）。"""

from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.other_outbound import OtherOutbound
from apps.kuaizhizao.models.other_outbound_item import OtherOutboundItem
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
from core.services.integration.kingdee_warehouse_document_push_config import (
    enrich_kingdee_warehouse_push_config,
    merge_warehouse_kingdee_push_config,
)
from core.services.integration.kingdee_cosmic_api_presets import (
    BIZ_IM_OTHEROUTBILL,
    IM_OTHEROUTBILL_BATCH_ADD_PATH,
)
from core.utils.timezone_utils import (
    resolve_business_datetime,
    to_api_isoformat,
    to_site_date,
    today_site_str,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = BIZ_IM_OTHEROUTBILL
DEFAULT_SAVE_PATH = IM_OTHEROUTBILL_BATCH_ADD_PATH
TARGET_TYPE = "kingdee_im_otheroutbill"
TARGET_PROFILE = "kingdee_im_otheroutbill"
SOURCE_TYPE = "other_outbound"
PUSHABLE_STATUSES = frozenset({"已出库", "已完成", "processed", "COMPLETED", "POSTED"})
PUSH_DISABLED_MESSAGE = "金蝶其他出库推送未启用"


def other_outbound_push_skip_reason(
    outbound: OtherOutbound,
    *,
    already_pushed: bool = False,
    items: Optional[List[OtherOutboundItem]] = None,
) -> Optional[str]:
    if already_pushed:
        return "已推送过金蝶其他出库单"
    status = str(getattr(outbound, "status", None) or "").strip()
    status_upper = status.upper()
    if status not in PUSHABLE_STATUSES and status_upper not in PUSHABLE_STATUSES:
        return f"其他出库状态 {status or '-'} 不可推送（需已出库）"
    if items is not None and not items:
        return "其他出库单无明细行"
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


def _config_text(config: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(config.get(key) or "").strip()
        if text:
            return text
    return ""


def normalize_other_outbound_pick_header_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """领用部门/领用人/客户：与采购入库 bizoperator、bizdept 等同源补齐。"""
    out = dict(config)
    picker = _config_text(
        out,
        "pickeroperator_number",
        "picker_number",
        "bizoperator_operatornumber",
    )
    if picker:
        out["pickeroperator_number"] = picker
        if not _config_text(out, "picker_number"):
            out["picker_number"] = picker
    pickdept = _config_text(out, "pickdept_number", "bizdept_number", "dept_number")
    if pickdept:
        out["pickdept_number"] = pickdept
    customer = _config_text(out, "customer_number", "consumer_number")
    if customer:
        out["customer_number"] = customer
        out["consumer_number"] = customer
    return out


async def _resolve_user_department_code(tenant_id: int, user_id: Optional[int]) -> Optional[str]:
    uid = int(user_id or 0)
    if uid <= 0:
        return None
    try:
        from infra.models.user import User
        from core.models.department import Department

        user = await User.get_or_none(tenant_id=tenant_id, id=uid, deleted_at__isnull=True)
        if not user:
            return None
        dept_id = getattr(user, "department_id", None)
        if not dept_id:
            return None
        dept = await Department.get_or_none(
            tenant_id=tenant_id,
            id=int(dept_id),
            deleted_at__isnull=True,
        )
        if not dept:
            return None
        code = str(dept.code or "").strip()
        return code or None
    except Exception as exc:
        logger.warning("resolve user department code failed user_id={} err={}", uid, exc)
        return None


async def enrich_other_outbound_pick_header_config(
    tenant_id: int,
    outbound: OtherOutbound,
    acting_user_id: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    out = normalize_other_outbound_pick_header_config(config)
    doc_pickdept = str(getattr(outbound, "pick_department_code", None) or "").strip()
    if doc_pickdept:
        out["pickdept_number"] = doc_pickdept
        if not _config_text(out, "bizdept_number"):
            out["bizdept_number"] = doc_pickdept
    doc_picker = str(getattr(outbound, "picker_operator_number", None) or "").strip()
    if doc_picker:
        out["pickeroperator_number"] = doc_picker
        if not _config_text(out, "picker_number"):
            out["picker_number"] = doc_picker
    doc_customer = str(getattr(outbound, "customer_number", None) or "").strip()
    if doc_customer:
        out["customer_number"] = doc_customer
    if not _config_text(out, "pickdept_number"):
        actor_id = int(outbound.picker_id or outbound.deliverer_id or acting_user_id or 0)
        dept_code = await _resolve_user_department_code(tenant_id, actor_id)
        if dept_code:
            out["pickdept_number"] = dept_code
            if not _config_text(out, "bizdept_number"):
                out["bizdept_number"] = dept_code
    return out


def validate_kingdee_other_outbound_header(model: Dict[str, Any]) -> None:
    pickdept = _config_text(model, "pickdept_number", "bizdept_number", "dept_number")
    customer = _config_text(model, "customer_number", "consumer_number")
    picker = _config_text(model, "pickeroperator_number", "picker_number", "bizoperator_operatornumber")
    if not pickdept and not customer:
        raise BusinessLogicError(
            "金蝶其他出库缺少领用部门或客户：请在业务配置 parameters.warehouse.kingdee_other_outbound_push "
            "填写 pickdept_number 或 customer_number，或在所选写入接口 request_body 样例中配置有效 "
            "pickdept_number / customer_number（可与采购入库 kingdee_purchase_receipt_push 共用 bizdept、bizoperator）"
        )
    if not picker:
        raise BusinessLogicError(
            "金蝶其他出库缺少领用人：请填写 pickeroperator_number（可与采购入库 bizoperator_operatornumber 同源）"
        )


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


def build_kingdee_other_outbound_model(
    *,
    outbound: OtherOutbound,
    items: List[OtherOutboundItem],
    cfg: Optional[Dict[str, Any]] = None,
    warehouse_number: Optional[str] = None,
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
    bill_date = _date_string(outbound.delivery_time or outbound.created_at)

    entries: List[Dict[str, Any]] = []
    unit_map = (
        config.get("api_unit_code_map")
        if isinstance(config.get("api_unit_code_map"), dict)
        else None
    )
    for item in items:
        qty = _to_float(item.outbound_quantity)
        if qty <= 0:
            continue
        unit_raw = str(item.material_unit or "").strip()
        unit_number = (
            apply_unit_code_map(unit_raw, unit_map)
            or str(config.get("unit_number") or DEFAULT_UNIT_NUMBER).strip()
            or DEFAULT_UNIT_NUMBER
        )
        entry: Dict[str, Any] = {
            "material_number": str(item.material_code or "").strip(),
            "materialname": str(item.material_name or "").strip() or None,
            "qty": qty,
            "unit_number": unit_number,
            "linetype_number": str(config.get("linetype_number") or "").strip(),
        }
        if warehouse_number:
            entry["warehouse_number"] = warehouse_number
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
        if item.expiry_date:
            entry["expirydate"] = _date_string(item.expiry_date)
        if item.notes:
            entry["entrycomment"] = str(item.notes)
        out_invstatus = str(config.get("outinvstatus_number") or "").strip()
        out_invtype = str(config.get("outinvtype_number") or "").strip()
        if out_invstatus:
            entry["outinvstatus_number"] = out_invstatus
        if out_invtype:
            entry["outinvtype_number"] = out_invtype
        owner_type = str(config.get("outownertype") or "bos_org").strip() or "bos_org"
        keeper_type = str(config.get("outkeepertype") or "bos_org").strip() or "bos_org"
        owner_number = str(
            config.get("outowner_number") or config.get("org_number") or org_number
        ).strip()
        keeper_number = str(
            config.get("outkeeper_number") or config.get("org_number") or org_number
        ).strip()
        entry["outownertype"] = owner_type
        entry["outkeepertype"] = keeper_type
        if owner_number:
            entry["outowner_number"] = owner_number
        if keeper_number:
            entry["outkeeper_number"] = keeper_number
        price = _to_float(item.unit_price)
        if price:
            entry["price"] = price
        if not entry.get("linetype_number"):
            entry.pop("linetype_number", None)
        if not entry.get("materialname"):
            entry.pop("materialname", None)
        entries.append(entry)

    if entries:
        model["billentry"] = entries

    default_field_map = {
        "billno": "billno",
        "biztime": "biztime",
        "bookdate": "bookdate",
        "org_number": "org_number",
        "billtype_number": "billtype_number",
        "biztype_number": "biztype_number",
        "invscheme_number": "invscheme_number",
        "dept_number": "dept_number",
        "bizdept_number": "bizdept_number",
        "consumingorg_number": "consumingorg_number",
        "picker_number": "picker_number",
        "pickdept_number": "pickdept_number",
        "pickeroperator_number": "pickeroperator_number",
        "consumer_number": "consumer_number",
        "customer_number": "customer_number",
        "bizoperator_operatornumber": "bizoperator_operatornumber",
        "comment": "comment",
    }

    def local_value(key: str) -> Any:
        if key == "billno":
            if config.get("use_local_bill_no", True):
                return outbound.outbound_code
            return None
        if key in {"biztime", "bookdate"}:
            return bill_date
        if key == "org_number":
            return org_number
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
        if key == "dept_number":
            return (
                str(config.get("dept_number") or config.get("bizdept_number") or "").strip()
                or None
            )
        if key == "bizdept_number":
            return (
                str(config.get("bizdept_number") or config.get("dept_number") or "").strip()
                or None
            )
        if key == "pickdept_number":
            doc = str(getattr(outbound, "pick_department_code", None) or "").strip()
            if doc:
                return doc
            return (
                str(
                    config.get("pickdept_number")
                    or config.get("bizdept_number")
                    or config.get("dept_number")
                    or ""
                ).strip()
                or None
            )
        if key == "pickeroperator_number":
            doc = str(getattr(outbound, "picker_operator_number", None) or "").strip()
            if doc:
                return doc
            return (
                str(
                    config.get("pickeroperator_number")
                    or config.get("picker_number")
                    or config.get("bizoperator_operatornumber")
                    or config.get("consumer_number")
                    or ""
                ).strip()
                or None
            )
        if key in {"picker_number", "consumer_number", "bizoperator_operatornumber"}:
            return (
                str(
                    config.get("picker_number")
                    or config.get("consumer_number")
                    or config.get("bizoperator_operatornumber")
                    or ""
                ).strip()
                or None
            )
        if key == "customer_number":
            doc = str(getattr(outbound, "customer_number", None) or "").strip()
            if doc:
                return doc
            return (
                str(config.get("customer_number") or config.get("consumer_number") or "").strip()
                or None
            )
        if key == "consumingorg_number":
            return str(config.get("consumingorg_number") or org_number).strip() or None
        if key == "comment":
            return _compact_text(
                "快格云其他出库",
                outbound.outbound_code,
                outbound.reason_type,
                outbound.reason_desc,
                outbound.notes,
            )
        return getattr(outbound, key, None)

    apply_field_map(model, dict(default_field_map), local_value)

    fixed_values = config.get("fixed_values")
    if isinstance(fixed_values, dict):
        for target_path, value in fixed_values.items():
            set_path(model, str(target_path), value)

    return model


class KingdeeOtherOutboundPushService:
    TARGET_PROFILE = TARGET_PROFILE

    async def push_other_outbound(
        self,
        *,
        tenant_id: int,
        other_outbound_id: int,
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

        outbound = await OtherOutbound.get_or_none(
            tenant_id=tenant_id,
            id=other_outbound_id,
            deleted_at__isnull=True,
        )
        if not outbound:
            return None

        items = await OtherOutboundItem.filter(
            tenant_id=tenant_id,
            outbound_id=other_outbound_id,
        ).order_by("id")

        already_pushed = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=other_outbound_id,
            target_type=TARGET_TYPE,
        ).exists()
        skip_reason = other_outbound_push_skip_reason(
            outbound,
            already_pushed=already_pushed,
            items=list(items),
        )
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        try:
            return await self._push_now(
                tenant_id=tenant_id,
                outbound=outbound,
                items=list(items),
                acting_user_id=acting_user_id,
                config=config,
                dry_run=dry_run,
            )
        except Exception as exc:
            logger.warning(
                "其他出库推送金蝶苍穹失败 tenant_id={} other_outbound_id={} err={}",
                tenant_id,
                other_outbound_id,
                exc,
            )
            if bool(config.get("fail_on_error", False)):
                raise BusinessLogicError(f"推送金蝶其他出库失败：{exc}")
            return {"success": False, "message": str(exc)}

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        return merge_warehouse_kingdee_push_config(warehouse, "kingdee_other_outbound_push")

    async def _push_now(
        self,
        *,
        tenant_id: int,
        outbound: OtherOutbound,
        items: List[OtherOutboundItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        config = await enrich_kingdee_warehouse_push_config(tenant_id, config)
        config = await enrich_other_outbound_pick_header_config(
            tenant_id, outbound, acting_user_id, config
        )
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
                "金蝶其他出库推送缺少配置：" + "、".join(missing)
                + "（业务配置 parameters.warehouse.kingdee_other_outbound_push）"
            )

        warehouse_number = await _resolve_warehouse_number(
            tenant_id, warehouse_id=outbound.warehouse_id, cfg=config
        )
        if not warehouse_number and not dry_run:
            raise BusinessLogicError("缺少仓库编码，无法推送金蝶其他出库单")

        first_code = items[0].material_code if items else None
        unit_code_map = await load_save_api_unit_code_map(
            tenant_id, str(config.get("save_api_uuid") or "").strip() or None
        )
        units = await resolve_unit_for_push(
            tenant_id,
            product_code=first_code,
            unit_hint=None,
            unit_code_map=unit_code_map,
        )
        config = {
            **config,
            **units,
            "api_unit_code_map": unit_code_map,
            "save_path": save_path,
            "body_wrap": str(config.get("body_wrap") or "data_list").strip() or "data_list",
        }

        model = build_kingdee_other_outbound_model(
            outbound=outbound,
            items=items,
            cfg=config,
            warehouse_number=warehouse_number,
        )
        if not (model.get("billentry") or []) and not dry_run:
            raise BusinessLogicError("其他出库单无有效明细数量，无法推送")
        if not dry_run:
            validate_kingdee_other_outbound_header(model)

        request = DocumentPushRequest(
            source_type=SOURCE_TYPE,
            source_id=int(outbound.id),
            target_profile=TARGET_PROFILE,
            source_code=outbound.outbound_code,
            source_name=outbound.outbound_code,
            connection_code=str(config.get("connection_code") or "").strip() or None,
            save_api_uuid=str(config.get("save_api_uuid") or "").strip() or None,
            dry_run=dry_run,
        )
        prepared = DocumentPushPrepared(
            form_id=form_id,
            model=model,
            target_type=TARGET_TYPE,
            target_name="金蝶苍穹其他出库单",
            relation_desc="其他出库推送金蝶苍穹其他出库单",
            connector_type="kingdee_cosmic",
            config=config,
        )

        async def _persist(result: Dict[str, Any]) -> None:
            await DocumentRelation.create(
                tenant_id=tenant_id,
                source_type=str(result.get("source_type") or SOURCE_TYPE),
                source_id=int(result.get("source_id") or outbound.id),
                source_code=result.get("source_code") or outbound.outbound_code,
                source_name=result.get("source_name") or outbound.outbound_code,
                target_type=str(result.get("target_type") or TARGET_TYPE),
                target_id=int(result.get("bill_id") or 0),
                target_code=(result.get("bill_no") or None),
                target_name=str(result.get("target_name") or "金蝶苍穹其他出库单"),
                relation_type="source",
                relation_mode="push",
                relation_desc=str(
                    result.get("relation_desc") or "其他出库推送金蝶苍穹其他出库单"
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
