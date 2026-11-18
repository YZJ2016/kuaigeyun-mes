"""业务适配：盘点单（盘亏行）→ 金蝶云苍穹盘亏单批量新增（im_deficitbill/batchAdd）。"""

from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.stocktaking import Stocktaking, StocktakingItem
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
    BIZ_IM_DEFICITBILL,
    IM_DEFICITBILL_BATCH_ADD_PATH,
)
from core.utils.timezone_utils import (
    resolve_business_datetime,
    to_api_isoformat,
    to_site_date,
    today_site_str,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

DEFAULT_FORM_ID = BIZ_IM_DEFICITBILL
DEFAULT_SAVE_PATH = IM_DEFICITBILL_BATCH_ADD_PATH
TARGET_TYPE = "kingdee_im_deficitbill"
TARGET_PROFILE = "kingdee_im_deficitbill"
SOURCE_TYPE = "stocktaking"
PUSHABLE_STATUSES = frozenset({"completed", "COMPLETED", "已完成"})


def stocktaking_deficit_push_skip_reason(
    stocktaking: Stocktaking,
    *,
    already_pushed: bool = False,
    loss_items: Optional[List[StocktakingItem]] = None,
) -> Optional[str]:
    if already_pushed:
        return "已推送过金蝶盘亏单"
    status = str(getattr(stocktaking, "status", None) or "").strip()
    status_upper = status.upper()
    if status not in PUSHABLE_STATUSES and status_upper not in PUSHABLE_STATUSES:
        return f"盘点单状态 {status or '-'} 不可推送（需已完成）"
    if loss_items is not None and not loss_items:
        return "盘点单无盘亏明细行（差异数量须小于 0）"
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


def filter_deficit_items(items: List[StocktakingItem]) -> List[StocktakingItem]:
    result: List[StocktakingItem] = []
    for item in items:
        diff = _to_float(item.difference_quantity)
        if diff < 0:
            result.append(item)
            continue
        actual = _to_float(item.actual_quantity)
        book = _to_float(item.book_quantity)
        if actual < book:
            result.append(item)
    return result


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


def build_kingdee_deficit_model(
    *,
    stocktaking: Stocktaking,
    items: List[StocktakingItem],
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
    bill_date = _date_string(stocktaking.stocktaking_date or stocktaking.completed_at or stocktaking.created_at)
    owner_type = str(config.get("outownertype") or config.get("ownertype") or "bos_org").strip() or "bos_org"
    keeper_type = str(config.get("outkeepertype") or config.get("keepertype") or "bos_org").strip() or "bos_org"
    owner_number = str(
        config.get("outowner_number") or config.get("owner_number") or org_number
    ).strip()
    keeper_number = str(
        config.get("outkeeper_number") or config.get("keeper_number") or org_number
    ).strip()

    entries: List[Dict[str, Any]] = []
    unit_map = (
        config.get("api_unit_code_map")
        if isinstance(config.get("api_unit_code_map"), dict)
        else None
    )
    for item in items:
        book = _to_float(item.book_quantity)
        actual = _to_float(item.actual_quantity)
        loss = -_to_float(item.difference_quantity)
        if loss <= 0:
            loss = book - actual
        if loss <= 0:
            continue
        if actual < 0:
            actual = book - loss
        unit_raw = str(item.material_unit or "").strip()
        unit_number = (
            apply_unit_code_map(unit_raw, unit_map)
            or str(config.get("unit_number") or DEFAULT_UNIT_NUMBER).strip()
            or DEFAULT_UNIT_NUMBER
        )
        entry: Dict[str, Any] = {
            "material_number": str(item.material_code or "").strip(),
            "linetype_number": str(config.get("linetype_number") or "").strip(),
            "outinvstatus_number": str(
                config.get("outinvstatus_number") or config.get("invstatus_number") or ""
            ).strip(),
            "outinvtype_number": str(
                config.get("outinvtype_number") or config.get("invtype_number") or ""
            ).strip(),
            "outownertype": owner_type,
            "outkeepertype": keeper_type,
            "outowner_number": owner_number,
            "outkeeper_number": keeper_number,
            "qty": actual,
            "invlossqty": loss,
            "invqtyacc": book,
            "unit_number": unit_number,
        }
        if warehouse_number:
            entry["warehouse_number"] = warehouse_number
        if item.location_code:
            entry["location_number"] = str(item.location_code).strip()
        if item.batch_no:
            entry["lotnumber"] = str(item.batch_no).strip()
        if item.remarks:
            entry["entrycomment"] = str(item.remarks)
        for key in ("linetype_number", "outinvstatus_number", "outinvtype_number"):
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
        "comment": "comment",
    }

    def local_value(key: str) -> Any:
        if key == "billno":
            if config.get("use_local_bill_no", True):
                return stocktaking.code
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
            return str(config.get("dept_number") or "").strip() or None
        if key == "comment":
            return _compact_text("快格云盘亏", stocktaking.code, stocktaking.remarks)
        return getattr(stocktaking, key, None)

    apply_field_map(model, dict(default_field_map), local_value)

    fixed_values = config.get("fixed_values")
    if isinstance(fixed_values, dict):
        for target_path, value in fixed_values.items():
            set_path(model, str(target_path), value)

    return model


class KingdeeStocktakingDeficitPushService:
    TARGET_PROFILE = TARGET_PROFILE

    async def push_stocktaking_deficit(
        self,
        *,
        tenant_id: int,
        stocktaking_id: int,
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

        stocktaking = await Stocktaking.get_or_none(
            tenant_id=tenant_id,
            id=stocktaking_id,
            deleted_at__isnull=True,
        )
        if not stocktaking:
            return None

        items = await StocktakingItem.filter(
            tenant_id=tenant_id,
            stocktaking_id=stocktaking_id,
            deleted_at__isnull=True,
        ).order_by("id")
        loss_items = filter_deficit_items(list(items))

        already_pushed = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE,
            source_id=stocktaking_id,
            target_type=TARGET_TYPE,
        ).exists()
        skip_reason = stocktaking_deficit_push_skip_reason(
            stocktaking,
            already_pushed=already_pushed,
            loss_items=loss_items,
        )
        if skip_reason:
            return {"success": True, "skipped": True, "message": skip_reason}

        try:
            return await self._push_now(
                tenant_id=tenant_id,
                stocktaking=stocktaking,
                loss_items=loss_items,
                acting_user_id=acting_user_id,
                config=config,
                dry_run=dry_run,
            )
        except Exception as exc:
            logger.warning(
                "盘点盘亏推送金蝶苍穹失败 tenant_id={} stocktaking_id={} err={}",
                tenant_id,
                stocktaking_id,
                exc,
            )
            if bool(config.get("fail_on_error", False)):
                raise BusinessLogicError(f"推送金蝶盘亏单失败：{exc}")
            return {"success": False, "message": str(exc)}

    async def get_push_config(self, tenant_id: int) -> Dict[str, Any]:
        biz_config = await BusinessConfigService().get_business_config(tenant_id)
        warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
        raw = warehouse.get("kingdee_stocktaking_deficit_push") or {}
        return dict(raw) if isinstance(raw, dict) else {}

    async def _push_now(
        self,
        *,
        tenant_id: int,
        stocktaking: Stocktaking,
        loss_items: List[StocktakingItem],
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
            "linetype_number",
            "outinvstatus_number",
            "outinvtype_number",
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
            elif key == "outinvstatus_number":
                if not (
                    config.get("outinvstatus_number") or config.get("invstatus_number")
                ):
                    missing.append(key)
            elif key == "outinvtype_number":
                if not (
                    config.get("outinvtype_number") or config.get("invtype_number")
                ):
                    missing.append(key)
            elif not str(config.get(key) or "").strip():
                missing.append(key)
        if missing and not dry_run:
            raise BusinessLogicError(
                "金蝶盘亏推送缺少配置：" + "、".join(missing)
                + "（业务配置 parameters.warehouse.kingdee_stocktaking_deficit_push）"
            )

        warehouse_number = await _resolve_warehouse_number(
            tenant_id, warehouse_id=stocktaking.warehouse_id, cfg=config
        )
        if not warehouse_number and not dry_run:
            raise BusinessLogicError("缺少仓库编码，无法推送金蝶盘亏单")

        first_code = loss_items[0].material_code if loss_items else None
        first_unit = (
            str(getattr(loss_items[0], "material_unit", None) or "").strip() if loss_items else ""
        )
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

        model = build_kingdee_deficit_model(
            stocktaking=stocktaking,
            items=loss_items,
            cfg=config,
            warehouse_number=warehouse_number,
        )
        if not (model.get("billentry") or []) and not dry_run:
            raise BusinessLogicError("盘点单无有效盘亏明细，无法推送")

        request = DocumentPushRequest(
            source_type=SOURCE_TYPE,
            source_id=int(stocktaking.id),
            target_profile=TARGET_PROFILE,
            source_code=stocktaking.code,
            source_name=stocktaking.code,
            connection_code=str(config.get("connection_code") or "").strip() or None,
            save_api_uuid=str(config.get("save_api_uuid") or "").strip() or None,
            dry_run=dry_run,
        )
        prepared = DocumentPushPrepared(
            form_id=form_id,
            model=model,
            target_type=TARGET_TYPE,
            target_name="金蝶苍穹盘亏单",
            relation_desc="盘点盘亏推送金蝶苍穹盘亏单",
            connector_type="kingdee_cosmic",
            config=config,
        )

        async def _persist(result: Dict[str, Any]) -> None:
            await DocumentRelation.create(
                tenant_id=tenant_id,
                source_type=str(result.get("source_type") or SOURCE_TYPE),
                source_id=int(result.get("source_id") or stocktaking.id),
                source_code=result.get("source_code") or stocktaking.code,
                source_name=result.get("source_name") or stocktaking.code,
                target_type=str(result.get("target_type") or TARGET_TYPE),
                target_id=int(result.get("bill_id") or 0),
                target_code=(result.get("bill_no") or None),
                target_name=str(result.get("target_name") or "金蝶苍穹盘亏单"),
                relation_type="source",
                relation_mode="push",
                relation_desc=str(
                    result.get("relation_desc") or "盘点盘亏推送金蝶苍穹盘亏单"
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
