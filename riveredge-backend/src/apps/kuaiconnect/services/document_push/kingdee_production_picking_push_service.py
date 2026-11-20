"""业务适配：生产领料单 → 金蝶云苍穹其他出库单（im_otheroutbill/batchAdd，单据类型=生产领料）。"""

from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.production_picking import ProductionPicking
from apps.kuaizhizao.models.production_picking_item import ProductionPickingItem
from apps.kuaiconnect.services.document_push.kingdee_push_location import (
    build_kingdee_location_number_by_item_id,
    kingdee_location_number_for_item,
    warehouse_number_by_item_id_from_wh_map,
)
from apps.kuaiconnect.services.document_push.kingdee_other_outbound_push_service import (
    _resolve_warehouse_number,
    apply_kingdee_other_outbill_picker_header,
    enrich_pick_header_config,
    validate_kingdee_other_outbound_header,
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
    BIZ_IM_OTHEROUTBILL,
    IM_OTHEROUTBILL_BATCH_ADD_PATH,
    IM_OTHEROUTBILL_BATCH_AUDIT_PATH,
    IM_OTHEROUTBILL_BATCH_SUBMIT_PATH,
    is_im_otheroutbill_add3_path,
)
from core.services.integration.kingdee_warehouse_document_push_config import (
    enrich_kingdee_warehouse_push_config,
    finalize_kingdee_warehouse_im_push_config,
    is_standard_other_outbill_billtype,
)
from core.services.integration.kingdee_warehouse_push_routing import (
    PRODUCTION_PICKING_KEY,
    resolve_production_picking_push_config,
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
    PRODUCTION_PICKING_REVOKE_SPEC,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = BIZ_IM_OTHEROUTBILL
DEFAULT_SAVE_PATH = IM_OTHEROUTBILL_BATCH_ADD_PATH
DEFAULT_SUBMIT_PATH = IM_OTHEROUTBILL_BATCH_SUBMIT_PATH
DEFAULT_AUDIT_PATH = IM_OTHEROUTBILL_BATCH_AUDIT_PATH
TARGET_TYPE = "kingdee_im_otheroutbill"
TARGET_PROFILE = "kingdee_im_otheroutbill"
SOURCE_TYPE = "production_picking"
PUSHABLE_STATUSES = frozenset({"已领料", "已确认", "picked", "confirmed", "COMPLETED", "POSTED"})
PUSH_DISABLED_MESSAGE = "金蝶生产领料推送未启用"


def production_picking_push_skip_reason(
    picking: ProductionPicking,
    *,
    already_pushed: bool = False,
    items: Optional[List[ProductionPickingItem]] = None,
) -> Optional[str]:
    # 已推送不在此跳过：对齐销售出库，可补 batchSubmit / billbatchAudit
    _ = already_pushed
    status = str(getattr(picking, "status", None) or "").strip()
    status_upper = status.upper()
    if status not in PUSHABLE_STATUSES and status_upper not in PUSHABLE_STATUSES:
        return f"生产领料状态 {status or '-'} 不可推送（需已领料）"
    if items is not None and not items:
        return "生产领料单无明细行"
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


async def enrich_production_picking_header_config(
    tenant_id: int,
    picking: ProductionPicking,
    acting_user_id: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    from apps.kuaizhizao.utils.kingdee_warehouse_operator_utils import (
        resolve_document_operator_number,
    )

    picker_id = int(getattr(picking, "picker_id", None) or 0) or None
    doc_picker = await resolve_document_operator_number(
        tenant_id,
        picker_id,
        explicit=None,
    )
    return await enrich_pick_header_config(
        tenant_id,
        acting_user_id=acting_user_id,
        picker_user_id=picker_id,
        config=config,
        doc_picker_operator=doc_picker,
        doc_pickdept=str(getattr(picking, "pick_department_code", None) or "").strip()
        or None,
    )


def build_kingdee_production_picking_model(
    *,
    picking: ProductionPicking,
    items: List[ProductionPickingItem],
    cfg: Optional[Dict[str, Any]] = None,
    warehouse_numbers: Optional[Dict[int, Optional[str]]] = None,
    location_number_by_item_id: Optional[Dict[int, str]] = None,
    invtype_by_item_id: Optional[Dict[int, str]] = None,
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
    bill_date = _date_string(picking.picking_time or picking.created_at)
    wh_map = warehouse_numbers or {}
    invtype_map = invtype_by_item_id or {}

    entries: List[Dict[str, Any]] = []
    unit_map = (
        config.get("api_unit_code_map")
        if isinstance(config.get("api_unit_code_map"), dict)
        else None
    )
    for item in items:
        qty = _to_float(item.picked_quantity or item.required_quantity)
        if qty <= 0:
            continue
        unit_raw = str(item.material_unit or "").strip()
        unit_number = (
            apply_unit_code_map(unit_raw, unit_map)
            or str(config.get("unit_number") or DEFAULT_UNIT_NUMBER).strip()
            or DEFAULT_UNIT_NUMBER
        )
        line_wh = wh_map.get(int(item.id or 0)) or wh_map.get(int(item.warehouse_id or 0))
        entry: Dict[str, Any] = {
            "material_number": str(item.material_code or "").strip(),
            "materialname": str(item.material_name or "").strip() or None,
            "qty": qty,
            "unit_number": unit_number,
            "linetype_number": str(config.get("linetype_number") or "").strip(),
        }
        if line_wh:
            entry["warehouse_number"] = line_wh
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
        out_invstatus = str(config.get("outinvstatus_number") or "").strip()
        line_invtype = str(invtype_map.get(int(item.id or 0)) or "").strip()
        out_invtype = line_invtype or str(config.get("outinvtype_number") or "").strip()
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
        "pickeroperator_operatornumber": "pickeroperator_operatornumber",
        "comment": "comment",
    }

    def local_value(key: str) -> Any:
        if key == "billno":
            return resolve_kingdee_local_bill_no(
                config=config,
                local_code=picking.picking_code,
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
        if key in {"dept_number", "bizdept_number", "pickdept_number"}:
            return (
                str(
                    config.get("pickdept_number")
                    or config.get("bizdept_number")
                    or config.get("dept_number")
                    or ""
                ).strip()
                or None
            )
        if key in {
            "picker_number",
            "pickeroperator_number",
            "pickeroperator_operatornumber",
            "bizoperator_operatornumber",
        }:
            return (
                str(
                    config.get("pickeroperator_operatornumber")
                    or config.get("pickeroperator_number")
                    or config.get("picker_number")
                    or config.get("bizoperator_operatornumber")
                    or ""
                ).strip()
                or None
            )
        if key == "consumingorg_number":
            return str(config.get("consumingorg_number") or org_number).strip() or None
        if key == "comment":
            return _compact_text(
                "从MES系统生产领料",
                picking.picking_code,
                picking.work_order_code,
                picking.notes,
            )
        return getattr(picking, key, None)

    apply_field_map(model, dict(default_field_map), local_value)
    apply_kingdee_other_outbill_picker_header(model, config)

    fixed_values = config.get("fixed_values")
    if isinstance(fixed_values, dict):
        for target_path, value in fixed_values.items():
            set_path(model, str(target_path), value)

    return model


class KingdeeProductionPickingPushService:
    TARGET_PROFILE = TARGET_PROFILE

    async def push_production_picking(
        self,
        *,
        tenant_id: int,
        production_picking_id: int,
        acting_user_id: int,
        connection_code: Optional[str] = None,
        save_api_uuid: Optional[str] = None,
        dry_run: bool = False,
    ) -> Optional[Dict[str, Any]]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        config = resolve_production_picking_push_config(warehouse)
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

        picking = await ProductionPicking.get_or_none(
            tenant_id=tenant_id,
            id=production_picking_id,
            deleted_at__isnull=True,
        )
        if not picking:
            return None

        items = await ProductionPickingItem.filter(
            tenant_id=tenant_id,
            picking_id=production_picking_id,
        ).order_by("id")

        relation = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=production_picking_id,
            target_type=TARGET_TYPE,
        ).first()
        skip_reason = production_picking_push_skip_reason(
            picking,
            already_pushed=False,
            items=list(items),
        )
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        if relation is not None:
            status = str(getattr(picking, "status", None) or "").strip()
            try:
                if relation_branch_should_batch_update(status):
                    return await self.batch_update_linked_kingdee_bill(
                        tenant_id=tenant_id,
                        picking=picking,
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
                    "生产领料补提交/审核金蝶失败 tenant_id={} production_picking_id={} err={}",
                    tenant_id,
                    production_picking_id,
                    exc,
                )
                if bool(config.get("fail_on_error", False)):
                    raise BusinessLogicError(f"金蝶生产领料补提交/审核失败：{exc}")
                return {"success": False, "message": str(exc)}

        try:
            return await self._push_now(
                tenant_id=tenant_id,
                picking=picking,
                items=list(items),
                acting_user_id=acting_user_id,
                config=config,
                dry_run=dry_run,
            )
        except Exception as exc:
            logger.warning(
                "生产领料推送金蝶苍穹失败 tenant_id={} production_picking_id={} err={}",
                tenant_id,
                production_picking_id,
                exc,
            )
            if bool(config.get("fail_on_error", False)):
                raise BusinessLogicError(f"推送金蝶生产领料失败：{exc}")
            return {"success": False, "message": str(exc)}

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        return resolve_production_picking_push_config(warehouse)

    async def _kingdee_submit_audit_only(
        self,
        *,
        tenant_id: int,
        config: Dict[str, Any],
        relation: DocumentRelation,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """已有关联时只调 batchSubmit / billbatchAudit（对齐销售出库，修复金蝶仍暂存）。"""
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
        picking: ProductionPicking,
        items: List[ProductionPickingItem],
        acting_user_id: int,
        relation: DocumentRelation,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        async def _prepare(merged: Dict[str, Any]) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
            return await self._prepare_kingdee_push_model(
                tenant_id=tenant_id,
                picking=picking,
                items=items,
                acting_user_id=acting_user_id,
                config=merged,
                dry_run=dry_run,
            )

        return await kingdee_im_batch_update_linked_bill(
            tenant_id=tenant_id,
            spec=PRODUCTION_PICKING_REVOKE_SPEC,
            source_id=int(picking.id),
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
        picking: ProductionPicking,
        items: List[ProductionPickingItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
        config = {
            **config,
            "form_id": str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID,
        }
        config = await enrich_kingdee_warehouse_push_config(
            tenant_id,
            config,
            expected_related_document=SOURCE_TYPE,
        )
        config = await enrich_production_picking_header_config(
            tenant_id, picking, acting_user_id, config
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
        if billtype and is_standard_other_outbill_billtype(billtype) and not dry_run:
            raise BusinessLogicError(
                "生产领料外推单据类型不能是标准其他出库单；"
                "请在接口库「苍穹生产领料其他出库批量新增」样例的 billtype_number "
                "填写本账套「生产领料」编码（勿用 im_OtherOutBill_STD_*），"
                f"或修正业务配置 parameters.warehouse.{PRODUCTION_PICKING_KEY}.billtype_number"
            )
        if missing and not dry_run:
            raise BusinessLogicError(
                "金蝶生产领料推送缺少配置：" + "、".join(missing)
                + f"（请在「苍穹生产领料其他出库批量新增」样例或 "
                f"parameters.warehouse.{PRODUCTION_PICKING_KEY} 填写生产领料单据类型等编码）"
            )

        wh_numbers: Dict[int, Optional[str]] = {}
        for item in items:
            wh_id = int(item.warehouse_id or 0)
            if wh_id <= 0:
                continue
            wh_numbers[int(item.id or 0)] = await _resolve_warehouse_number(
                tenant_id, warehouse_id=wh_id, cfg=config
            )

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
        # 误配的 batchAudit 纠正为 billbatchAudit（与销售出库 finalize 对齐）
        raw_audit = str(config.get("audit_path") or "").strip().lower().replace("_", "")
        if "otheroutbill" in raw_audit and "batchaudit" in raw_audit and "billbatchaudit" not in raw_audit:
            config = {**config, "audit_path": DEFAULT_AUDIT_PATH}
        # 自定义 add3：单对象 data；标品 batchAdd：data 数组
        body_wrap = "data" if is_im_otheroutbill_add3_path(save_path) else "data_list"
        config = finalize_kingdee_warehouse_im_push_config(
            {
                **config,
                **units,
                "api_unit_code_map": unit_code_map,
                "save_path": save_path,
            },
            default_submit_path=DEFAULT_SUBMIT_PATH,
            default_audit_path=DEFAULT_AUDIT_PATH,
            default_body_wrap=body_wrap,
        )
        if is_im_otheroutbill_add3_path(str(config.get("save_path") or save_path)):
            config = {**config, "body_wrap": "data"}

        location_number_by_item_id = await build_kingdee_location_number_by_item_id(
            tenant_id,
            items,
            config,
            warehouse_number_by_item_id=warehouse_number_by_item_id_from_wh_map(items, wh_numbers),
        )
        from apps.kuaiconnect.services.document_push.kingdee_outbound_invtype_resolve import (
            resolve_kingdee_out_invtype_by_item_id,
        )

        qty_by_item = {
            int(it.id or 0): (it.picked_quantity or it.required_quantity or 0)
            for it in items
            if int(it.id or 0) > 0
        }
        preferred_invtype = str(
            config.get("outinvtype_number") or config.get("invtype_number") or ""
        ).strip()
        invtype_by_item_id = await resolve_kingdee_out_invtype_by_item_id(
            tenant_id,
            items=items,
            quantity_by_item_id=qty_by_item,
            warehouse_number_by_item_id=wh_numbers,
            location_number_by_item_id=location_number_by_item_id,
            preferred_invtype=preferred_invtype,
            dry_run=dry_run,
        )
        model = build_kingdee_production_picking_model(
            picking=picking,
            items=items,
            cfg=config,
            warehouse_numbers=wh_numbers,
            location_number_by_item_id=location_number_by_item_id,
            invtype_by_item_id=invtype_by_item_id,
        )
        if not dry_run:
            validate_kingdee_other_outbound_header(model)
        if not (model.get("billentry") or []) and not dry_run:
            raise BusinessLogicError("生产领料单无有效明细数量，无法推送")
        return config, form_id, model

    async def _push_now(
        self,
        *,
        tenant_id: int,
        picking: ProductionPicking,
        items: List[ProductionPickingItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        config, form_id, model = await self._prepare_kingdee_push_model(
            tenant_id=tenant_id,
            picking=picking,
            items=items,
            acting_user_id=acting_user_id,
            config=config,
            dry_run=dry_run,
        )

        request = DocumentPushRequest(
            source_type=SOURCE_TYPE,
            source_id=int(picking.id),
            target_profile=TARGET_PROFILE,
            source_code=picking.picking_code,
            source_name=picking.picking_code,
            connection_code=str(config.get("connection_code") or "").strip() or None,
            save_api_uuid=str(config.get("save_api_uuid") or "").strip() or None,
            dry_run=dry_run,
        )
        prepared = DocumentPushPrepared(
            form_id=form_id,
            model=model,
            target_type=TARGET_TYPE,
            target_name="金蝶苍穹生产领料出库单",
            relation_desc="生产领料推送金蝶苍穹其他出库单",
            connector_type="kingdee_cosmic",
            config=config,
        )

        async def _persist(result: Dict[str, Any]) -> None:
            await DocumentRelation.create(
                tenant_id=tenant_id,
                source_type=str(result.get("source_type") or SOURCE_TYPE),
                source_id=int(result.get("source_id") or picking.id),
                source_code=result.get("source_code") or picking.picking_code,
                source_name=result.get("source_name") or picking.picking_code,
                target_type=str(result.get("target_type") or TARGET_TYPE),
                target_id=int(result.get("bill_id") or 0),
                target_code=(result.get("bill_no") or None),
                target_name=str(result.get("target_name") or "金蝶苍穹生产领料出库单"),
                relation_type="source",
                relation_mode="push",
                relation_desc=str(
                    result.get("relation_desc") or "生产领料推送金蝶苍穹其他出库单"
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
