"""业务适配：其他入库单 → 金蝶云苍穹其他入库单批量新增（im_otherinbill/batchAdd）。"""

from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.other_inbound import OtherInbound
from apps.kuaizhizao.models.other_inbound_item import OtherInboundItem
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
from core.services.integration.kingdee_warehouse_document_push_config import (
    enrich_kingdee_warehouse_push_config,
    finalize_kingdee_warehouse_im_push_config,
    merge_warehouse_kingdee_push_config,
    read_kingdee_push_workflow_bool,
)
from core.services.integration.kingdee_cosmic_api_presets import (
    BIZ_IM_OTHERINBILL,
    IM_OTHERINBILL_BATCH_ADD_PATH,
    IM_OTHERINBILL_BATCH_AUDIT_PATH,
    IM_OTHERINBILL_BATCH_SUBMIT_PATH,
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
    OTHER_INBOUND_REVOKE_SPEC,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = BIZ_IM_OTHERINBILL
DEFAULT_SAVE_PATH = IM_OTHERINBILL_BATCH_ADD_PATH
TARGET_TYPE = "kingdee_im_otherinbill"
TARGET_PROFILE = "kingdee_im_otherinbill"
SOURCE_TYPE = "other_inbound"
PUSHABLE_STATUSES = frozenset({"已入库", "已完成", "processed", "COMPLETED", "POSTED"})
PUSH_DISABLED_MESSAGE = "金蝶其他入库推送未启用"


def other_inbound_push_skip_reason(
    inbound: OtherInbound,
    *,
    already_pushed: bool = False,
    items: Optional[List[OtherInboundItem]] = None,
) -> Optional[str]:
    # already_pushed 不再在此跳过：有关联时走补提交/审核（对齐其他出库）
    _ = already_pushed
    status = str(getattr(inbound, "status", None) or "").strip()
    status_upper = status.upper()
    if status not in PUSHABLE_STATUSES and status_upper not in PUSHABLE_STATUSES:
        return f"其他入库状态 {status or '-'} 不可推送（需已入库）"
    if items is not None and not items:
        return "其他入库单无明细行"
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


def normalize_other_inbound_header_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """库管部门/库管员：与采购入库 bizoperator、bizdept 及开放平台 Operator 写键对齐。"""
    out = dict(config)
    keeper_group = _config_text(
        out, "operatorgroup_number", "bizoperatorgroup_number"
    )
    operator = _config_text(
        out,
        "operator_operatornumber",
        "bizoperator_operatornumber",
        "operator_number",
    )
    # 与采购入库一致：无库管组时不写库管员，避免苍穹报「没有对应可用的库管组」
    if operator and keeper_group:
        out["operator_operatornumber"] = operator
        out["bizoperator_operatornumber"] = operator
        out["operatorgroup_number"] = keeper_group
    else:
        for key in (
            "operator_operatornumber",
            "bizoperator_operatornumber",
            "operator_number",
            "operatorgroup_number",
        ):
            out.pop(key, None)
    dept = _config_text(out, "bizdept_number", "dept_number")
    if dept:
        out["bizdept_number"] = dept
        if not _config_text(out, "dept_number"):
            out["dept_number"] = dept
    return out


def apply_kingdee_other_inbill_entry_line_fields(
    entry: Dict[str, Any],
    *,
    config: Dict[str, Any],
    org_number: str,
) -> None:
    """im_otherinbill 明细：入库 inv* + 开放平台文档中的 outinv*（与其他出库对称）。"""
    invstatus = str(config.get("invstatus_number") or "").strip()
    invtype = str(config.get("invtype_number") or "").strip()
    if invstatus:
        entry["invstatus_number"] = invstatus
    if invtype:
        entry["invtype_number"] = invtype
    # 苍穹其他入库明细同样校验「出库库存类型/状态」；未单独配置时与入库 inv* 同源（与其他出库对称）
    out_invstatus = str(config.get("outinvstatus_number") or invstatus or "").strip()
    out_invtype = str(config.get("outinvtype_number") or invtype or "").strip()
    if out_invstatus:
        entry["outinvstatus_number"] = out_invstatus
    if out_invtype:
        entry["outinvtype_number"] = out_invtype

    owner_type = str(config.get("ownertype") or "bos_org").strip() or "bos_org"
    keeper_type = str(config.get("keepertype") or "bos_org").strip() or "bos_org"
    owner_number = str(config.get("owner_number") or org_number).strip()
    keeper_number = str(config.get("keeper_number") or org_number).strip()
    entry["ownertype"] = owner_type
    entry["keepertype"] = keeper_type
    if owner_number:
        entry["owner_number"] = owner_number
    if keeper_number:
        entry["keeper_number"] = keeper_number

    if str(config.get("outownertype") or "").strip():
        entry["outownertype"] = str(config.get("outownertype")).strip()
    if str(config.get("outkeepertype") or "").strip():
        entry["outkeepertype"] = str(config.get("outkeepertype")).strip()
    out_owner_number = str(config.get("outowner_number") or "").strip()
    out_keeper_number = str(config.get("outkeeper_number") or "").strip()
    if out_owner_number:
        entry["outowner_number"] = out_owner_number
    if out_keeper_number:
        entry["outkeeper_number"] = out_keeper_number


async def _resolve_user_department_code(tenant_id: int, user_id: int) -> Optional[str]:
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


async def enrich_other_inbound_header_config(
    tenant_id: int,
    inbound: OtherInbound,
    acting_user_id: int,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    out = normalize_other_inbound_header_config(config)
    if not _config_text(out, "bizdept_number", "dept_number"):
        actor_id = int(inbound.receiver_id or acting_user_id or 0)
        dept_code = await _resolve_user_department_code(tenant_id, actor_id)
        if dept_code:
            out["bizdept_number"] = dept_code
            if not _config_text(out, "dept_number"):
                out["dept_number"] = dept_code
    return out


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


def build_kingdee_other_inbound_model(
    *,
    inbound: OtherInbound,
    items: List[OtherInboundItem],
    cfg: Optional[Dict[str, Any]] = None,
    warehouse_number: Optional[str] = None,
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
    bill_date = _date_string(inbound.receipt_time or inbound.created_at)
    line_plan = line_unit_qty_by_item_id or {}

    entries: List[Dict[str, Any]] = []
    for item in items:
        planned = line_plan.get(int(item.id or 0)) or {}
        qty = _to_float(planned.get("qty", item.inbound_quantity))
        if qty <= 0:
            continue
        unit_number = (
            str(planned.get("unit_number") or "").strip()
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
        from apps.kuaiconnect.services.document_push.kingdee_warehouse_billentry_dual_qty import (
            apply_billentry_dual_qty_fields,
            restate_entry_prices_for_inventory_qty,
        )

        apply_billentry_dual_qty_fields(entry, planned)
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
        price = _to_float(item.unit_price)
        if price:
            entry["price"] = price
        restate_entry_prices_for_inventory_qty(
            entry,
            document_qty=_to_float(item.inbound_quantity) or qty,
            unit_price=price,
        )
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
                local_code=inbound.inbound_code,
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
                str(
                    config.get("bizdept_number")
                    or config.get("dept_number")
                    or ""
                ).strip()
                or None
            )
        if key in {"bizoperator_operatornumber", "operator_operatornumber"}:
            return (
                str(
                    config.get("operator_operatornumber")
                    or config.get("bizoperator_operatornumber")
                    or config.get("buyer_operatornumber")
                    or ""
                ).strip()
                or None
            )
        if key == "comment":
            return _compact_text(
                "从MES系统其他入库",
                inbound.inbound_code,
                inbound.reason_type,
                inbound.reason_desc,
                inbound.notes,
            )
        return getattr(inbound, key, None)

    apply_field_map(model, dict(default_field_map), local_value)

    fixed_values = config.get("fixed_values")
    if isinstance(fixed_values, dict):
        for target_path, value in fixed_values.items():
            set_path(model, str(target_path), value)

    return model


def validate_kingdee_other_inbound_entry_lines(entries: List[Dict[str, Any]]) -> None:
    """Save 前校验明细，避免苍穹报「出库库存类型/状态不能为空」。"""
    for idx, entry in enumerate(entries, start=1):
        missing: List[str] = []
        if not str(entry.get("outinvtype_number") or "").strip():
            missing.append("出库库存类型")
        if not str(entry.get("outinvstatus_number") or "").strip():
            missing.append("出库库存状态")
        if not str(entry.get("invtype_number") or "").strip():
            missing.append("入库库存类型")
        if not str(entry.get("invstatus_number") or "").strip():
            missing.append("入库库存状态")
        if missing:
            raise BusinessLogicError(
                f"金蝶其他入库明细第{idx}行缺少：{'、'.join(missing)}。"
                "请在业务配置 parameters.warehouse.kingdee_other_inbound_push 或所绑 Save 接口样例中填写 "
                "invstatus_number、invtype_number（outinv* 可留空，将与 inv* 一致），"
                "或从采购入库推送配置继承上述字段。"
            )


class KingdeeOtherInboundPushService:
    TARGET_PROFILE = TARGET_PROFILE

    async def push_other_inbound(
        self,
        *,
        tenant_id: int,
        other_inbound_id: int,
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

        inbound = await OtherInbound.get_or_none(
            tenant_id=tenant_id,
            id=other_inbound_id,
            deleted_at__isnull=True,
        )
        if not inbound:
            return None

        items = await OtherInboundItem.filter(
            tenant_id=tenant_id,
            inbound_id=other_inbound_id,
        ).order_by("id")

        relation = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=other_inbound_id,
            target_type=TARGET_TYPE,
        ).first()
        skip_reason = other_inbound_push_skip_reason(
            inbound,
            already_pushed=False,
            items=list(items),
        )
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        if relation is not None:
            status = str(getattr(inbound, "status", None) or "").strip()
            try:
                if relation_branch_should_batch_update(status):
                    return await self.batch_update_linked_kingdee_bill(
                        tenant_id=tenant_id,
                        inbound=inbound,
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
                    "其他入库补提交/审核金蝶失败 tenant_id={} other_inbound_id={} err={}",
                    tenant_id,
                    other_inbound_id,
                    exc,
                )
                if bool(config.get("fail_on_error", True)):
                    raise BusinessLogicError(f"金蝶其他入库补提交/审核失败：{exc}")
                return {"success": False, "message": str(exc)}

        try:
            return await self._push_now(
                tenant_id=tenant_id,
                inbound=inbound,
                items=list(items),
                acting_user_id=acting_user_id,
                config=config,
                dry_run=dry_run,
            )
        except Exception as exc:
            logger.warning(
                "其他入库推送金蝶苍穹失败 tenant_id={} other_inbound_id={} err={}",
                tenant_id,
                other_inbound_id,
                exc,
            )
            if bool(config.get("fail_on_error", True)):
                raise BusinessLogicError(f"推送金蝶其他入库失败：{exc}")
            return {"success": False, "message": str(exc)}

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        return merge_warehouse_kingdee_push_config(warehouse, "kingdee_other_inbound_push")

    async def _kingdee_submit_audit_only(
        self,
        *,
        tenant_id: int,
        config: Dict[str, Any],
        relation: DocumentRelation,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """已有关联时只调 batchSubmit / billbatchAudit。"""
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

    async def _prepare_kingdee_push_model(
        self,
        *,
        tenant_id: int,
        inbound: OtherInbound,
        items: List[OtherInboundItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool,
    ) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
        config = await enrich_kingdee_warehouse_push_config(tenant_id, config)
        config = await enrich_other_inbound_header_config(
            tenant_id, inbound, acting_user_id, config
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
        if missing and not dry_run:
            raise BusinessLogicError(
                "金蝶其他入库推送缺少配置：" + "、".join(missing)
                + "（业务配置 parameters.warehouse.kingdee_other_inbound_push）"
            )

        warehouse_number = await _resolve_warehouse_number(
            tenant_id, warehouse_id=inbound.warehouse_id, cfg=config
        )
        if not warehouse_number and not dry_run:
            raise BusinessLogicError("缺少仓库编码，无法推送金蝶其他入库单")

        first_code = items[0].material_code if items else None
        unit_code_map = await load_save_api_unit_code_map(
            tenant_id, str(config.get("save_api_uuid") or "").strip() or None
        )
        units = await resolve_unit_for_push(
            tenant_id,
            product_code=first_code,
            unit_hint=None,
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
            quantity_field="inbound_quantity",
            scene_label="其他入库",
            unit_code_map=unit_code_map,
            config_unit_number=str(config.get("unit_number") or "").strip() or None,
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
        model = build_kingdee_other_inbound_model(
            inbound=inbound,
            items=items,
            cfg=config,
            warehouse_number=warehouse_number,
            location_number_by_item_id=location_number_by_item_id,
            line_unit_qty_by_item_id=line_unit_qty_by_item_id,
        )
        log_billentry_dual_qty(
            doc_label="其他入库",
            doc_code=inbound.inbound_code,
            entries=model.get("billentry") or [],
        )
        billentry = model.get("billentry") or []
        if not billentry and not dry_run:
            raise BusinessLogicError("其他入库单无有效明细数量，无法推送")
        if billentry and not dry_run:
            validate_kingdee_other_inbound_entry_lines(billentry)
        return config, form_id, model

    async def batch_update_linked_kingdee_bill(
        self,
        *,
        tenant_id: int,
        inbound: OtherInbound,
        items: List[OtherInboundItem],
        acting_user_id: int,
        relation: DocumentRelation,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        async def _prepare(merged: Dict[str, Any]) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
            return await self._prepare_kingdee_push_model(
                tenant_id=tenant_id,
                inbound=inbound,
                items=items,
                acting_user_id=acting_user_id,
                config=merged,
                dry_run=dry_run,
            )

        return await kingdee_im_batch_update_linked_bill(
            tenant_id=tenant_id,
            spec=OTHER_INBOUND_REVOKE_SPEC,
            source_id=int(inbound.id),
            source_type=SOURCE_TYPE,
            relation=relation,
            base_config=config,
            prepare_model=_prepare,
            dry_run=dry_run,
        )

    async def _push_now(
        self,
        *,
        tenant_id: int,
        inbound: OtherInbound,
        items: List[OtherInboundItem],
        acting_user_id: int,
        config: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        config, form_id, model = await self._prepare_kingdee_push_model(
            tenant_id=tenant_id,
            inbound=inbound,
            items=items,
            acting_user_id=acting_user_id,
            config=config,
            dry_run=dry_run,
        )

        request = DocumentPushRequest(
            source_type=SOURCE_TYPE,
            source_id=int(inbound.id),
            target_profile=TARGET_PROFILE,
            source_code=inbound.inbound_code,
            source_name=inbound.inbound_code,
            connection_code=str(config.get("connection_code") or "").strip() or None,
            save_api_uuid=str(config.get("save_api_uuid") or "").strip() or None,
            dry_run=dry_run,
        )
        prepared = DocumentPushPrepared(
            form_id=form_id,
            model=model,
            target_type=TARGET_TYPE,
            target_name="金蝶苍穹其他入库单",
            relation_desc="其他入库推送金蝶苍穹其他入库单",
            connector_type="kingdee_cosmic",
            config=config,
        )

        async def _persist(result: Dict[str, Any]) -> None:
            await DocumentRelation.create(
                tenant_id=tenant_id,
                source_type=str(result.get("source_type") or SOURCE_TYPE),
                source_id=int(result.get("source_id") or inbound.id),
                source_code=result.get("source_code") or inbound.inbound_code,
                source_name=result.get("source_name") or inbound.inbound_code,
                target_type=str(result.get("target_type") or TARGET_TYPE),
                target_id=int(result.get("bill_id") or 0),
                target_code=(result.get("bill_no") or None),
                target_name=str(result.get("target_name") or "金蝶苍穹其他入库单"),
                relation_type="source",
                relation_mode="push",
                relation_desc=str(
                    result.get("relation_desc") or "其他入库推送金蝶苍穹其他入库单"
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
