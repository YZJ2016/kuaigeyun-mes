"""业务适配：成品入库单 → 金蝶云苍穹其他入库单（im_otherinbill/batchAdd，单据类型=生产完工入库）。"""

from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.finished_goods_receipt import FinishedGoodsReceipt
from apps.kuaizhizao.models.finished_goods_receipt_item import FinishedGoodsReceiptItem
from apps.kuaiconnect.services.document_push.kingdee_other_inbound_push_service import (
    _resolve_warehouse_number,
    _resolve_user_department_code,
    apply_kingdee_other_inbill_entry_line_fields,
    normalize_other_inbound_header_config,
)
from apps.kuaiconnect.services.document_push.kingdee_push_location import (
    build_kingdee_location_number_by_item_id,
    kingdee_location_number_for_item,
)
from core.services.integration.document_push_codes import (
    DEFAULT_UNIT_NUMBER,
    apply_unit_code_map,
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
    BIZ_IM_OTHERINBILL,
    IM_OTHERINBILL_BATCH_ADD_PATH,
    IM_OTHERINBILL_BATCH_AUDIT_PATH,
    IM_OTHERINBILL_BATCH_SUBMIT_PATH,
)
from core.services.integration.kingdee_warehouse_document_push_config import (
    enrich_kingdee_warehouse_push_config,
    finalize_kingdee_warehouse_im_push_config,
    is_standard_other_inbill_billtype,
    read_kingdee_push_workflow_bool,
)
from core.services.integration.kingdee_warehouse_push_routing import (
    FINISHED_GOODS_RECEIPT_KEY,
    resolve_finished_goods_push_config,
)
from core.utils.timezone_utils import (
    resolve_business_datetime,
    to_api_isoformat,
    to_site_date,
    today_site_str,
)
from apps.kuaiconnect.services.document_push.kingdee_im_batch_update_service import (
    kingdee_im_batch_update_linked_bill,
    relation_branch_should_batch_update,
)
from apps.kuaiconnect.services.document_push.kingdee_im_warehouse_revoke_service import (
    FINISHED_GOODS_RECEIPT_REVOKE_SPEC,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = BIZ_IM_OTHERINBILL
DEFAULT_SAVE_PATH = IM_OTHERINBILL_BATCH_ADD_PATH
TARGET_TYPE = "kingdee_im_otherinbill"
TARGET_PROFILE = "kingdee_im_otherinbill"
SOURCE_TYPE = "finished_goods_receipt"
PUSHABLE_STATUSES = frozenset({"已入库", "已完成", "processed", "COMPLETED", "POSTED"})
PUSH_DISABLED_MESSAGE = "金蝶成品入库推送未启用"


def finished_goods_receipt_push_skip_reason(
    receipt: FinishedGoodsReceipt,
    *,
    already_pushed: bool = False,
    items: Optional[List[FinishedGoodsReceiptItem]] = None,
) -> Optional[str]:
    # already_pushed 不再在此跳过：有关联时走补提交/审核
    _ = already_pushed
    status = str(getattr(receipt, "status", None) or "").strip()
    status_upper = status.upper()
    if status not in PUSHABLE_STATUSES and status_upper not in PUSHABLE_STATUSES:
        return f"成品入库状态 {status or '-'} 不可推送（需已入库）"
    if items is not None and not items:
        return "成品入库单无明细行"
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


async def enrich_finished_goods_header_config(
    tenant_id: int,
    receipt: FinishedGoodsReceipt,
    acting_user_id: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    out = normalize_other_inbound_header_config(config)
    dept_keys = ("bizdept_number", "dept_number")
    if not any(str(out.get(k) or "").strip() for k in dept_keys):
        actor_id = int(getattr(receipt, "receiver_id", None) or acting_user_id or 0)
        dept_code = await _resolve_user_department_code(tenant_id, actor_id)
        if dept_code:
            out["bizdept_number"] = dept_code
            out["dept_number"] = dept_code
    return out


def build_kingdee_finished_goods_receipt_model(
    *,
    receipt: FinishedGoodsReceipt,
    items: List[FinishedGoodsReceiptItem],
    cfg: Optional[Dict[str, Any]] = None,
    warehouse_number: Optional[str] = None,
    location_number_by_item_id: Optional[Dict[int, str]] = None,
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
    entries: List[Dict[str, Any]] = []
    unit_map = (
        config.get("api_unit_code_map")
        if isinstance(config.get("api_unit_code_map"), dict)
        else None
    )
    for item in items:
        qty = _to_float(item.receipt_quantity or item.qualified_quantity)
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
        apply_kingdee_other_inbill_entry_line_fields(
            entry, config=config, org_number=org_number
        )
        if warehouse_number:
            entry["warehouse_number"] = warehouse_number
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
        for key in ("linetype_number", "invstatus_number", "invtype_number", "materialname"):
            if not entry.get(key):
                entry.pop(key, None)
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
        "operator_operatornumber": "operator_operatornumber",
        "bizoperator_operatornumber": "bizoperator_operatornumber",
        "comment": "comment",
    }

    def local_value(key: str) -> Any:
        if key == "billno":
            return resolve_kingdee_local_bill_no(
                config=config,
                local_code=receipt.receipt_code,
                org_number=org_number,
            )
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
        if key in {"dept_number", "bizdept_number"}:
            return (
                str(config.get("bizdept_number") or config.get("dept_number") or "").strip()
                or None
            )
        if key in {"bizoperator_operatornumber", "operator_operatornumber"}:
            return (
                str(
                    config.get("operator_operatornumber")
                    or config.get("bizoperator_operatornumber")
                    or ""
                ).strip()
                or None
            )
        if key == "comment":
            return _compact_text(
                "从MES系统成品入库",
                receipt.receipt_code,
                receipt.work_order_code,
                receipt.notes,
            )
        return getattr(receipt, key, None)

    apply_field_map(model, dict(default_field_map), local_value)

    fixed_values = config.get("fixed_values")
    if isinstance(fixed_values, dict):
        for target_path, value in fixed_values.items():
            set_path(model, str(target_path), value)

    return model


class KingdeeFinishedGoodsReceiptPushService:
    TARGET_PROFILE = TARGET_PROFILE

    async def push_finished_goods_receipt(
        self,
        *,
        tenant_id: int,
        finished_goods_receipt_id: int,
        acting_user_id: int,
        connection_code: Optional[str] = None,
        save_api_uuid: Optional[str] = None,
        dry_run: bool = False,
    ) -> Optional[Dict[str, Any]]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        config = resolve_finished_goods_push_config(warehouse)
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

        receipt = await FinishedGoodsReceipt.get_or_none(
            tenant_id=tenant_id,
            id=finished_goods_receipt_id,
            deleted_at__isnull=True,
        )
        if not receipt:
            return None

        items = await FinishedGoodsReceiptItem.filter(
            tenant_id=tenant_id,
            receipt_id=finished_goods_receipt_id,
        ).order_by("id")

        relation = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=finished_goods_receipt_id,
            target_type=TARGET_TYPE,
        ).first()
        skip_reason = finished_goods_receipt_push_skip_reason(
            receipt,
            already_pushed=False,
            items=list(items),
        )
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        if relation is not None:
            status = str(getattr(receipt, "status", None) or "").strip()
            try:
                if relation_branch_should_batch_update(status):
                    return await self.batch_update_linked_kingdee_bill(
                        tenant_id=tenant_id,
                        receipt=receipt,
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
                    "成品入库补提交/审核金蝶失败 tenant_id={} finished_goods_receipt_id={} err={}",
                    tenant_id,
                    finished_goods_receipt_id,
                    exc,
                )
                if bool(config.get("fail_on_error", True)):
                    raise BusinessLogicError(f"金蝶成品入库补提交/审核失败：{exc}")
                return {"success": False, "message": str(exc)}

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
                "成品入库推送金蝶苍穹失败 tenant_id={} finished_goods_receipt_id={} err={}",
                tenant_id,
                finished_goods_receipt_id,
                exc,
            )
            if bool(config.get("fail_on_error", True)):
                raise BusinessLogicError(f"推送金蝶成品入库失败：{exc}")
            return {"success": False, "message": str(exc)}

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        return resolve_finished_goods_push_config(warehouse)

    async def _kingdee_submit_audit_only(
        self,
        *,
        tenant_id: int,
        config: Dict[str, Any],
        relation: DocumentRelation,
        dry_run: bool,
    ) -> Dict[str, Any]:
        config = {
            **config,
            "form_id": str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID,
        }
        config = await enrich_kingdee_warehouse_push_config(
            tenant_id,
            config,
            expected_related_document=SOURCE_TYPE,
        )
        config = finalize_kingdee_warehouse_im_push_config(
            config,
            default_submit_path=IM_OTHERINBILL_BATCH_SUBMIT_PATH,
            default_audit_path=IM_OTHERINBILL_BATCH_AUDIT_PATH,
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
        receipt: FinishedGoodsReceipt,
        items: List[FinishedGoodsReceiptItem],
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

        return await kingdee_im_batch_update_linked_bill(
            tenant_id=tenant_id,
            spec=FINISHED_GOODS_RECEIPT_REVOKE_SPEC,
            source_id=int(receipt.id),
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
        receipt: FinishedGoodsReceipt,
        items: List[FinishedGoodsReceiptItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
        config = await enrich_kingdee_warehouse_push_config(
            tenant_id,
            config,
            expected_related_document=SOURCE_TYPE,
        )
        config = await enrich_finished_goods_header_config(
            tenant_id, receipt, acting_user_id, config
        )
        form_id = str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID
        save_path = str(config.get("save_path") or DEFAULT_SAVE_PATH).strip() or DEFAULT_SAVE_PATH

        required_cfg = (
            "org_number",
            "billtype_number",
            "biztype_number",
            "invscheme_number",
            "linetype_number",
            "invstatus_number",
            "invtype_number",
        )
        missing = []
        for key in required_cfg:
            if key == "billtype_number":
                if not (config.get("billtype_number") or config.get("bill_type_number")):
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
        billtype = str(
            config.get("billtype_number") or config.get("bill_type_number") or ""
        ).strip()
        if billtype and is_standard_other_inbill_billtype(billtype) and not dry_run:
            raise BusinessLogicError(
                "成品入库外推单据类型不能是标准其他入库单；"
                "请在接口库「苍穹成品入库其他入库批量新增」样例的 billtype_number "
                "填写本账套「生产完工入库」编码（勿用 im_OtherInBill_STD_*），"
                f"或修正业务配置 parameters.warehouse.{FINISHED_GOODS_RECEIPT_KEY}.billtype_number"
            )
        if missing and not dry_run:
            raise BusinessLogicError(
                "金蝶成品入库推送缺少配置：" + "、".join(missing)
                + f"（请在「苍穹成品入库其他入库批量新增」样例或 "
                f"parameters.warehouse.{FINISHED_GOODS_RECEIPT_KEY} 填写生产完工入库单据类型等编码）"
            )

        warehouse_number = await _resolve_warehouse_number(
            tenant_id, warehouse_id=receipt.warehouse_id, cfg=config
        )
        if not warehouse_number and not dry_run:
            raise BusinessLogicError("缺少仓库编码，无法推送金蝶成品入库单")

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
        submit_path = str(config.get("submit_path") or "").strip() or IM_OTHERINBILL_BATCH_SUBMIT_PATH
        audit_path = str(config.get("audit_path") or "").strip() or IM_OTHERINBILL_BATCH_AUDIT_PATH
        config = {
            **config,
            **units,
            "api_unit_code_map": unit_code_map,
            "save_path": save_path,
            "body_wrap": str(config.get("body_wrap") or "data_list").strip() or "data_list",
            "operate_body_wrap": str(config.get("operate_body_wrap") or "data").strip()
            or "data",
            "submit_path": submit_path,
            "audit_path": audit_path,
            "submit_after_save": read_kingdee_push_workflow_bool(
                config, "submit_after_save", default=True
            ),
            "audit_after_save": read_kingdee_push_workflow_bool(
                config, "audit_after_save", default=True
            ),
        }

        location_number_by_item_id = await build_kingdee_location_number_by_item_id(
            tenant_id,
            items,
            config,
            default_warehouse_number=warehouse_number,
        )
        model = build_kingdee_finished_goods_receipt_model(
            receipt=receipt,
            items=items,
            cfg=config,
            warehouse_number=warehouse_number,
            location_number_by_item_id=location_number_by_item_id,
        )
        if not (model.get("billentry") or []) and not dry_run:
            raise BusinessLogicError("成品入库单无有效明细数量，无法推送")
        return config, form_id, model

    async def _push_now(
        self,
        *,
        tenant_id: int,
        receipt: FinishedGoodsReceipt,
        items: List[FinishedGoodsReceiptItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
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
            target_name="金蝶苍穹成品入库单",
            relation_desc="成品入库推送金蝶苍穹其他入库单",
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
                target_name=str(result.get("target_name") or "金蝶苍穹成品入库单"),
                relation_type="source",
                relation_mode="push",
                relation_desc=str(
                    result.get("relation_desc") or "成品入库推送金蝶苍穹其他入库单"
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
