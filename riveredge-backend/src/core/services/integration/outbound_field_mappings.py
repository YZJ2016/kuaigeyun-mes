"""出站接口字段映射：接口管理配置 → 推送组报文。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from core.services.integration.document_push_mapping import set_path

OutboundMappingRow = Dict[str, Any]


def normalize_outbound_field_mappings(raw: Any) -> List[OutboundMappingRow]:
    """规范化接口上的 outbound_field_mappings 列表。"""
    if not isinstance(raw, list):
        return []
    out: List[OutboundMappingRow] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        remote = str(item.get("remote_field") or item.get("target_field") or "").strip()
        if not remote:
            continue
        level = str(item.get("level") or "header").strip().lower()
        if level not in ("header", "entry"):
            level = "header"
        enabled = item.get("enabled")
        if enabled is None:
            enabled = True
        source_table = str(
            item.get("source_table") or item.get("local_table") or item.get("table") or ""
        ).strip()
        out.append(
            {
                "enabled": bool(enabled),
                "level": level,
                "source_table": source_table,
                "local_field": str(item.get("local_field") or item.get("source_field") or "").strip(),
                "remote_field": remote,
                "default_value": item.get("default_value"),
            }
        )
    return out


_PR_HEADER = "apps_kuaizhizao_purchase_receipts"
_PR_ENTRY = "apps_kuaizhizao_purchase_receipt_items"


def default_purchase_receipt_outbound_mappings() -> List[OutboundMappingRow]:
    """采购入库 → 苍穹 im_purinbill 默认映射（可在接口管理改）。"""
    return [
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "receipt_code", "remote_field": "trdbillno", "default_value": ""},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "biztime", "remote_field": "biztime", "default_value": ""},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "biztime", "remote_field": "exratedate", "default_value": ""},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "biztime", "remote_field": "bookdate", "default_value": ""},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "pay_mode", "remote_field": "paymode", "default_value": "CREDIT"},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "", "remote_field": "istax", "default_value": True},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "org_number", "remote_field": "org_number", "default_value": ""},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "bizorg_number", "remote_field": "bizorg_number", "default_value": ""},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "billtype_number", "remote_field": "billtype_number", "default_value": "im_PurInBill_STD_BT_S"},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "biztype_number", "remote_field": "biztype_number", "default_value": "110"},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "invscheme_number", "remote_field": "invscheme_number", "default_value": "110"},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "supplier_number", "remote_field": "supplier_number", "default_value": ""},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "comment", "remote_field": "comment", "default_value": ""},
        {"enabled": True, "level": "header", "source_table": _PR_HEADER, "local_field": "buyer_operator_number", "remote_field": "bizoperator_operatornumber", "default_value": ""},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "material_code", "remote_field": "material_number", "default_value": ""},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "receipt_quantity", "remote_field": "qty", "default_value": ""},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "material_unit", "remote_field": "unit_number", "default_value": ""},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "warehouse_number", "remote_field": "warehouse_number", "default_value": ""},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "batch_number", "remote_field": "lotnumber", "default_value": ""},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "", "remote_field": "linetype_number", "default_value": "010"},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "", "remote_field": "invtype_number", "default_value": "110"},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "", "remote_field": "invstatus_number", "default_value": "110"},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "", "remote_field": "outinvtype_number", "default_value": "110"},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "", "remote_field": "outinvstatus_number", "default_value": "110"},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "", "remote_field": "ownertype", "default_value": "bos_org"},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "", "remote_field": "keepertype", "default_value": "bos_org"},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "org_number", "remote_field": "owner_number", "default_value": ""},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "org_number", "remote_field": "keeper_number", "default_value": ""},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "org_number", "remote_field": "entryreqorg_number", "default_value": ""},
        {"enabled": True, "level": "entry", "source_table": _PR_ENTRY, "local_field": "org_number", "remote_field": "entrysettleorg_number", "default_value": ""},
    ]


def _coalesce_value(resolved: Any, default_value: Any) -> Any:
    if resolved is not None and resolved != "":
        return resolved
    if default_value is None or default_value == "":
        return None
    return default_value


def apply_outbound_field_mappings(
    model: Dict[str, Any],
    mappings: Sequence[Mapping[str, Any]],
    *,
    resolve_header: Callable[[str], Any],
    resolve_entry: Callable[[Dict[str, Any], str], Any],
) -> Dict[str, Any]:
    """按启用的映射行覆盖/补齐 model（含 billentry 明细）。"""
    rows = normalize_outbound_field_mappings(list(mappings))
    if not rows:
        return model

    for row in rows:
        if not row.get("enabled"):
            continue
        if row["level"] != "header":
            continue
        local_key = str(row.get("local_field") or "")
        resolved = resolve_header(local_key) if local_key else None
        value = _coalesce_value(resolved, row.get("default_value"))
        if value is not None and value != "":
            set_path(model, str(row["remote_field"]), value)

    entries = model.get("billentry")
    if not isinstance(entries, list):
        return model

    entry_rows = [r for r in rows if r.get("enabled") and r.get("level") == "entry"]
    if not entry_rows:
        return model

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for row in entry_rows:
            local_key = str(row.get("local_field") or "")
            resolved = resolve_entry(entry, local_key) if local_key else None
            # 明细也可引用头字段（如 org_number → owner_number）
            if (resolved is None or resolved == "") and local_key:
                resolved = resolve_header(local_key)
            value = _coalesce_value(resolved, row.get("default_value"))
            if value is not None and value != "":
                set_path(entry, str(row["remote_field"]), value)
    return model


def is_purchase_receipt_outbound_save_api(api_obj: Any) -> bool:
    """是否采购入库单新增出站接口（仅此类可回退默认映射并回写）。"""
    if api_obj is None:
        return False
    code = str(getattr(api_obj, "code", None) or "").lower()
    path = str(getattr(api_obj, "path", None) or "").lower().replace("\\", "/")
    name = str(getattr(api_obj, "name", None) or "").lower()
    hay = f"{code} {path} {name}"
    if (
        "add_im_purinbill" in code
        or "add2_im_purinbill" in code
        or "push_im_purinbill" in code
    ):
        return True
    if "im_purinbill" in path and ("/add" in path or path.endswith("add") or "/add2" in path):
        return True
    if ("purinbill" in hay or "采购入库" in name) and ("add" in hay or "新增" in name):
        return True
    return False


def outbound_mappings_need_purchase_receipt_defaults(
    mappings: Optional[Sequence[Mapping[str, Any]]],
) -> bool:
    """
    接口管理未配置可用映射（空列表），或未填写本地单据/实体表时，需要启用代码默认对齐。
    已有任一行填了 source_table（本地单据）则视为已人工匹配，不覆盖。
    """
    rows = normalize_outbound_field_mappings(mappings)
    if not rows:
        return True
    return not any(str(r.get("source_table") or "").strip() for r in rows)


async def load_outbound_field_mappings_from_save_api(
    tenant_id: int,
    save_api_uuid: Optional[str],
) -> List[OutboundMappingRow]:
    """从绑定的 Save 接口读取出站字段映射。"""
    api_uuid = str(save_api_uuid or "").strip()
    if not api_uuid:
        return []
    try:
        from core.models.api import API

        api_obj = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
        if not api_obj:
            return []
        return normalize_outbound_field_mappings(
            getattr(api_obj, "outbound_field_mappings", None)
        )
    except Exception:
        return []


async def ensure_purchase_receipt_outbound_mappings(
    tenant_id: int,
    save_api_uuid: Optional[str],
    *,
    persist: bool = True,
) -> List[OutboundMappingRow]:
    """
    采购入库推送专用：接口无本地单据映射时用代码默认对齐；
    启用后把默认映射写回该 Save 接口，下次可直接在接口管理使用。
    非采购入库新增接口：只读已有映射，不启用默认、不回写。
    """
    api_uuid = str(save_api_uuid or "").strip()
    if not api_uuid:
        return []

    try:
        from core.models.api import API
        from loguru import logger

        api_obj = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
        if not api_obj:
            return []

        existing_raw = getattr(api_obj, "outbound_field_mappings", None)
        existing = normalize_outbound_field_mappings(existing_raw)

        if not is_purchase_receipt_outbound_save_api(api_obj):
            return existing

        if not outbound_mappings_need_purchase_receipt_defaults(existing_raw):
            return existing

        defaults = default_purchase_receipt_outbound_mappings()
        if persist:
            # 仅在仍为空/无本地单据时写入，避免覆盖并发下已人工保存的配置
            fresh = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
            if fresh and outbound_mappings_need_purchase_receipt_defaults(
                getattr(fresh, "outbound_field_mappings", None)
            ):
                fresh.outbound_field_mappings = defaults
                await fresh.save(update_fields=["outbound_field_mappings", "updated_at"])
                logger.info(
                    "采购入库出站映射为空，已写入代码默认映射 api={} tenant={}",
                    api_uuid,
                    tenant_id,
                )
        return defaults
    except Exception:
        return []
