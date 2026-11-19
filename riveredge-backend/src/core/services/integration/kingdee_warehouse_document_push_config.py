"""仓储类苍穹出站：共用头字段从采购入库推送配置补齐，组织可从连接器读取。"""

from __future__ import annotations

from typing import Any, Dict, Optional

# 仅跨单据安全共用：可从采购入库推送配置继承。
# 禁止继承 billtype/biztype/invscheme/save_api_uuid 等单据专属项
# （否则销售出库会带上「标准采购入库单 + 110 物料类采购」导致苍穹关联校验失败）。
_CROSS_DOC_INHERIT_KEYS = (
    "org_number",
    "bizorg_number",
    "createorg_number",
    "connection_code",
    "bizdept_number",
    "dept_number",
    "currency_number",
    "settlecurrency_number",
    "exratetable_number",
)

# 明细/领料人与采购入库同源（不继承 billtype/biztype/invscheme）
_ENTRY_INHERIT_FROM_PURCHASE_KEYS = (
    "invstatus_number",
    "invtype_number",
    "linetype_number",
    "unit_number",
    "bizoperator_operatornumber",
    "operator_operatornumber",
    "pickeroperator_operatornumber",
    "outinvstatus_number",
    "outinvtype_number",
)

# 本单据 Save 接口样例可补齐的头字段（含单据专属类型，不来自采购配置）
_API_SAMPLE_HEADER_KEYS = (
    *_CROSS_DOC_INHERIT_KEYS,
    "billtype_number",
    "bill_type_number",
    "biztype_number",
    "invscheme_number",
    "inwscheme_number",
    "inv_scheme_number",
    "linetype_number",
    "invstatus_number",
    "invtype_number",
    "outinvstatus_number",
    "outinvtype_number",
    "pickdept_number",
    "picker_number",
    "pickeroperator_number",
    "pickeroperator_operatornumber",
    "consumer_number",
    "customer_number",
    "bizoperator_operatornumber",
    "operator_operatornumber",
    "ownertype",
    "keepertype",
    "outownertype",
    "outkeepertype",
    "outowner_number",
    "outkeeper_number",
)

# 关联单据不一致时禁止从 Save 样例继承（避免领料绑标准其他出库带上 STD billtype）
_DOC_TYPE_SAMPLE_KEYS = frozenset(
    {
        "billtype_number",
        "bill_type_number",
        "biztype_number",
        "invscheme_number",
        "inwscheme_number",
        "inv_scheme_number",
    }
)

_WORKFLOW_BOOL_KEYS = (
    "submit_after_save",
    "audit_after_save",
)

# 仅继承 operate_body_wrap；submit_path/audit_path 按单据 im_* 不同，禁止跨单据继承
_WORKFLOW_PATH_KEYS = ("operate_body_wrap",)


def read_kingdee_push_workflow_bool(
    config: Dict[str, Any],
    key: str,
    *,
    default: bool = True,
) -> bool:
    """业务配置 JSON 里显式 null 时 bool(None) 为 False，会误关保存后提交/审核。"""
    if key not in config:
        return default
    val = config.get(key)
    if val is None:
        return default
    return bool(val)


def _non_empty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _has_org(config: Dict[str, Any]) -> bool:
    return any(_non_empty(config.get(k)) for k in ("org_number", "bizorg_number", "createorg_number"))


def merge_warehouse_kingdee_push_config(warehouse: Dict[str, Any], config_key: str) -> Dict[str, Any]:
    """读取某类仓储推送配置，头字段为空时从 kingdee_purchase_receipt_push 继承。"""
    raw = warehouse.get(config_key)
    out = dict(raw) if isinstance(raw, dict) else {}
    purchase = warehouse.get("kingdee_purchase_receipt_push")
    purchase = dict(purchase) if isinstance(purchase, dict) else {}
    for key in _CROSS_DOC_INHERIT_KEYS:
        if _non_empty(out.get(key)):
            continue
        if key in purchase and _non_empty(purchase.get(key)):
            out[key] = purchase[key]
    for key in _ENTRY_INHERIT_FROM_PURCHASE_KEYS:
        if _non_empty(out.get(key)):
            continue
        if key in purchase and _non_empty(purchase.get(key)):
            out[key] = purchase[key]
    if not _non_empty(out.get("pickeroperator_operatornumber")) and _non_empty(
        purchase.get("bizoperator_operatornumber")
    ):
        out["pickeroperator_operatornumber"] = purchase["bizoperator_operatornumber"]
    for key in _WORKFLOW_PATH_KEYS:
        if _non_empty(out.get(key)):
            continue
        if key in purchase and _non_empty(purchase.get(key)):
            out[key] = purchase[key]
    for key in _WORKFLOW_BOOL_KEYS:
        if key in out and out.get(key) is not None:
            continue
        if key in purchase and purchase.get(key) is not None:
            out[key] = purchase[key]
    return out


def finalize_kingdee_warehouse_im_push_config(
    config: Dict[str, Any],
    *,
    default_submit_path: str,
    default_audit_path: str,
    default_body_wrap: Optional[str] = None,
) -> Dict[str, Any]:
    """采购/销售等 im_* 出站：与采购入库 push 对齐 submit/audit 路径与工作流开关。"""
    submit_path = str(config.get("submit_path") or "").strip() or default_submit_path
    audit_path = str(config.get("audit_path") or "").strip() or default_audit_path
    out = {
        **config,
        "submit_path": submit_path,
        "audit_path": audit_path,
        "operate_body_wrap": str(config.get("operate_body_wrap") or "data").strip() or "data",
        "submit_after_save": read_kingdee_push_workflow_bool(
            config, "submit_after_save", default=True
        ),
        "audit_after_save": read_kingdee_push_workflow_bool(
            config, "audit_after_save", default=True
        ),
    }
    if default_body_wrap:
        out["body_wrap"] = str(config.get("body_wrap") or default_body_wrap).strip() or default_body_wrap
    return out


def _haystack(api: Any) -> str:
    return f"{getattr(api, 'path', '')} {getattr(api, 'code', '')} {getattr(api, 'name', '')}".lower()


_IM_OPERATE_SLOT_PATH_MARKERS: Dict[str, tuple[str, ...]] = {
    "withdraw": ("batchunaudit", "billbatchunaudit"),
    "unsubmit": ("batchunsubmit", "billbatchunsubmit"),
    "delete": ("batchdelete", "billbatchdelete"),
}


def validate_im_operate_api_path(path: str, slot: str, *, doc_label: str = "仓储单据") -> None:
    """operate 须为 batchUnaudit 等路径；误绑 add/add2 会在苍穹网关 HTTP 404。"""
    from infra.exceptions.exceptions import BusinessLogicError

    key = str(slot or "").strip()
    markers = _IM_OPERATE_SLOT_PATH_MARKERS.get(key)
    if not markers:
        return
    hay = str(path or "").lower().replace("_", "").replace("-", "")
    if any(marker in hay for marker in markers):
        return
    slot_label = {"withdraw": "反审核", "unsubmit": "撤销提交", "delete": "删除"}.get(key, key)
    raise BusinessLogicError(
        f"金蝶{doc_label}{slot_label}接口路径不正确（当前：{str(path or '').strip() or '空'}）。"
        f"须绑定开放平台 batch 接口（如 im_purinbill/batchUnaudit），"
        "勿选采购入库新增 add/add2；并在苍穹开放服务云发布且授权该 API。"
    )


def _compatible_related_for_im_operate(expected: Optional[str]) -> Optional[frozenset[str]]:
    """同一 im_* 对象上，MES 关联单据可与标准出/入库单据共享提交/审核接口。"""
    code = str(expected or "").strip()
    if not code:
        return None
    if code in ("other_outbound", "production_picking"):
        return frozenset({"other_outbound", "production_picking"})
    if code in ("other_inbound", "finished_goods_receipt"):
        return frozenset({"other_inbound", "finished_goods_receipt"})
    return frozenset({code})


async def attach_im_operate_apis_from_save_binding(
    tenant_id: int,
    config: Dict[str, Any],
    *,
    im_bill: str,
) -> Dict[str, Any]:
    """Save 走接口库时，在同连接器上解析 batchSubmit / batchAudit（与 batchAdd 同一换票通道）。"""
    out = dict(config)
    save_uuid = str(out.get("save_api_uuid") or "").strip()
    if not save_uuid:
        return out
    try:
        from core.models.api import API

        save_api = await API.filter(tenant_id=tenant_id, uuid=save_uuid).first()
        if not save_api or not getattr(save_api, "integration_config_id", None):
            return out
        conn_id = int(save_api.integration_config_id)
        apis = await API.filter(
            tenant_id=tenant_id,
            integration_config_id=conn_id,
            deleted_at__isnull=True,
            is_active=True,
            sync_direction="push",
        ).all()
        hint = str(im_bill or "").strip().lower()
        from core.config.api_library_contract import related_document_for_im_bill_form

        expected_related = related_document_for_im_bill_form(hint)
        save_related = str(getattr(save_api, "related_document_code", None) or "").strip()
        allowed_related = _compatible_related_for_im_operate(expected_related)
        if save_related:
            save_allowed = _compatible_related_for_im_operate(save_related)
            if save_allowed:
                allowed_related = (
                    save_allowed
                    if allowed_related is None
                    else frozenset(allowed_related | save_allowed)
                )
        for api in apis:
            hay = _haystack(api).replace("_", "")
            if hint and hint.replace("_", "") not in hay:
                continue
            api_related = str(getattr(api, "related_document_code", None) or "").strip()
            if allowed_related and api_related and api_related not in allowed_related:
                continue
            path = str(getattr(api, "path", None) or "").strip()
            if "batchsubmit" in hay:
                out["submit_api_uuid"] = str(api.uuid)
                # 以接口库路径为准（纠正业务配置误写的 batchAudit 等）
                if path:
                    out["submit_path"] = path
            if "billbatchaudit" in hay:
                out["audit_api_uuid"] = str(api.uuid)
                if path:
                    out["audit_path"] = path
            elif "batchaudit" in hay and "unaudit" not in hay:
                # 其他出/入库开放平台须 billbatchAudit；勿挂 batchAudit
                if "otheroutbill" in hay or "otherinbill" in hay:
                    continue
                out["audit_api_uuid"] = str(api.uuid)
                if path:
                    out["audit_path"] = path
            elif "batchunaudit" in hay:
                out["unaudit_api_uuid"] = str(api.uuid)
                if path:
                    out["unaudit_path"] = path
            elif "batchunsubmit" in hay:
                out["unsubmit_api_uuid"] = str(api.uuid)
                if path:
                    out["unsubmit_path"] = path
            elif "batchdelete" in hay:
                out["delete_api_uuid"] = str(api.uuid)
                if path:
                    out["delete_path"] = path
    except Exception:
        return out
    return out


def _is_placeholder_header_value(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or text.upper().startswith("REPLACE_")


def is_standard_other_outbill_billtype(value: Any) -> bool:
    """标准其他出库单据类型（不可用于生产领料）。"""
    text = str(value or "").strip()
    if not text:
        return False
    compact = text.lower().replace("-", "").replace("_", "")
    return "otheroutbill" in compact and "std" in compact


def is_standard_other_inbill_billtype(value: Any) -> bool:
    """标准其他入库单据类型（不可用于成品入库/生产完工入库）。"""
    text = str(value or "").strip()
    if not text:
        return False
    compact = text.lower().replace("-", "").replace("_", "")
    return "otherinbill" in compact and "std" in compact


def strip_mismatched_std_document_types(
    config: Dict[str, Any],
    *,
    expected_related_document: Optional[str] = None,
) -> Dict[str, Any]:
    """领料/成品入库业务配置若误填 STD 其他出/入库单据类型，推送前剔除，避免盖过专用接口。"""
    out = dict(config)
    expected = str(expected_related_document or "").strip()
    if expected == "production_picking":
        for key in ("billtype_number", "bill_type_number"):
            if is_standard_other_outbill_billtype(out.get(key)):
                out.pop(key, None)
    elif expected == "finished_goods_receipt":
        for key in ("billtype_number", "bill_type_number"):
            if is_standard_other_inbill_billtype(out.get(key)):
                out.pop(key, None)
    return out


# 样例常把库存状态/类型/行类型写在首行 billentry，头为空时从明细补齐
_API_SAMPLE_ENTRY_FALLBACK_KEYS = (
    "linetype_number",
    "invstatus_number",
    "invtype_number",
    "outinvstatus_number",
    "outinvtype_number",
)


def _header_row_from_save_api_body(body: Any) -> Optional[Dict[str, Any]]:
    """从 Save 接口 request_body 取出单据头行。

    兼容：``{data: {...}}``（采购入库 add/add2）、``{data: [{...}]}``、
    ``{data_list: [{...}]}``（销售出库 batchAdd）、无包裹且含 billentry 的头行。
    """
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    data_list = body.get("data_list")
    if isinstance(data_list, list) and data_list and isinstance(data_list[0], dict):
        return data_list[0]
    if "billentry" in body and isinstance(body.get("billentry"), list):
        return body
    return None


def purinbill_save_sample_has_real_codes(body: Any) -> bool:
    """采购入库 Save 样例已写真实编码时，加载预设不得用 REPLACE_* 样例覆盖。"""
    row = _header_row_from_save_api_body(body)
    if not isinstance(row, dict):
        return False
    header_keys = (
        "billtype_number",
        "bill_type_number",
        "biztype_number",
        "invscheme_number",
        "inwscheme_number",
        "inv_scheme_number",
        "invstatus_number",
        "invtype_number",
        "linetype_number",
    )
    for key in header_keys:
        if not _is_placeholder_header_value(row.get(key)):
            return True
    entries = row.get("billentry")
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        first = entries[0]
        for key in ("invstatus_number", "invtype_number", "linetype_number"):
            if not _is_placeholder_header_value(first.get(key)):
                return True
    return False


def _apply_entry_fallback_fields(out: Dict[str, Any], row: Dict[str, Any]) -> None:
    entries = row.get("billentry")
    if not (isinstance(entries, list) and entries and isinstance(entries[0], dict)):
        return
    first = entries[0]
    for key in _API_SAMPLE_ENTRY_FALLBACK_KEYS:
        if _non_empty(out.get(key)):
            continue
        val = first.get(key)
        if not _is_placeholder_header_value(val):
            out[key] = val


async def _merge_header_from_save_api(
    tenant_id: int,
    config: Dict[str, Any],
    *,
    expected_related_document: Optional[str] = None,
) -> Dict[str, Any]:
    """Save 接口 request_body 样例头字段补齐推送配置（跳过 REPLACE_*）。"""
    out = dict(config)
    api_uuid = str(out.get("save_api_uuid") or "").strip()
    if not api_uuid:
        return out
    try:
        from core.models.api import API

        api_obj = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
        if not api_obj:
            return out
        row = _header_row_from_save_api_body(getattr(api_obj, "request_body", None))
        if not row:
            return out
        expected = str(expected_related_document or "").strip()
        api_related = str(getattr(api_obj, "related_document_code", None) or "").strip()
        skip_doc_type = bool(expected and api_related != expected)
        for key in _API_SAMPLE_HEADER_KEYS:
            if skip_doc_type and key in _DOC_TYPE_SAMPLE_KEYS:
                continue
            val = row.get(key)
            if _is_placeholder_header_value(val):
                continue
            if key in _DOC_TYPE_SAMPLE_KEYS and expected == "production_picking":
                if is_standard_other_outbill_billtype(val):
                    continue
            if key in _DOC_TYPE_SAMPLE_KEYS and expected == "finished_goods_receipt":
                if is_standard_other_inbill_billtype(val):
                    continue
            existing = out.get(key)
            if _non_empty(existing):
                # 已有 STD 误配时允许被专用接口真实编码覆盖
                if key in ("billtype_number", "bill_type_number"):
                    if expected == "production_picking" and is_standard_other_outbill_billtype(
                        existing
                    ):
                        out[key] = val
                        continue
                    if expected == "finished_goods_receipt" and is_standard_other_inbill_billtype(
                        existing
                    ):
                        out[key] = val
                        continue
                continue
            out[key] = val
        _apply_entry_fallback_fields(out, row)
    except Exception:
        return out
    return out


# 采购入库推送：配置/样例都空时的安全默认（与对方常见主数据、默认映射一致）
_PURCHASE_RECEIPT_CODE_DEFAULTS = {
    "invstatus_number": "110",  # 可用
    "invtype_number": "110",  # 普通
    "linetype_number": "010",
    "outinvstatus_number": "110",
    "outinvtype_number": "110",
    "biztype_number": "110",  # 常见「物料类采购」；可按账套改
    "invscheme_number": "110",  # 常见采购入库库存事务；可按账套改
}


def hydrate_purchase_receipt_push_config_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    推送闸口前补齐编码：
    1) 出站映射行的 default_value（对方字段名 = 配置键）
    2) 采购入库内置默认（库存状态/类型/行类型等）
    不覆盖已有非空配置；不填组织/单据类型（须账套真实编码）。
    """
    out = dict(config)
    try:
        from core.services.integration.outbound_field_mappings import (
            normalize_outbound_field_mappings,
        )

        for row in normalize_outbound_field_mappings(out.get("outbound_field_mappings")):
            if not row.get("enabled"):
                continue
            remote = str(row.get("remote_field") or "").strip()
            if not remote or _non_empty(out.get(remote)):
                continue
            dv = row.get("default_value")
            if dv is None or str(dv).strip() == "":
                continue
            if _is_placeholder_header_value(dv):
                continue
            out[remote] = dv
    except Exception:
        pass
    for key, value in _PURCHASE_RECEIPT_CODE_DEFAULTS.items():
        if not _non_empty(out.get(key)):
            out[key] = value
    return out


# 采购入库常用固定编码（与对方主数据一致；组织仍须按账套/单据填写）
_PURCHASE_RECEIPT_CODE_FALLBACKS = {
    "billtype_number": "im_PurInBill_STD_BT_S",
    "biztype_number": "110",
    "invscheme_number": "110",
    "invstatus_number": "110",
    "invtype_number": "110",
    "linetype_number": "010",
    "outinvstatus_number": "110",
    "outinvtype_number": "110",
}

_CONFIG_KEYS_FROM_MAPPING_DEFAULTS = (
    "org_number",
    "bizorg_number",
    "billtype_number",
    "bill_type_number",
    "biztype_number",
    "invscheme_number",
    "inwscheme_number",
    "inv_scheme_number",
    "invstatus_number",
    "invtype_number",
    "linetype_number",
    "outinvstatus_number",
    "outinvtype_number",
    "ownertype",
    "keepertype",
    "paymode",
)


def hydrate_purchase_receipt_push_config_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    推送校验前：用出站映射默认值 + 采购入库常用编码补齐配置空项。
    不覆盖业务配置 / 接口样例已写入的真实编码。
    """
    out = dict(config)
    raw_maps = out.get("outbound_field_mappings")
    if isinstance(raw_maps, list):
        from core.services.integration.outbound_field_mappings import (
            normalize_outbound_field_mappings,
        )

        for row in normalize_outbound_field_mappings(raw_maps):
            if not row.get("enabled"):
                continue
            remote = str(row.get("remote_field") or "").strip()
            if remote not in _CONFIG_KEYS_FROM_MAPPING_DEFAULTS:
                continue
            if _non_empty(out.get(remote)):
                continue
            dv = row.get("default_value")
            if dv is None or dv == "":
                continue
            if _is_placeholder_header_value(dv):
                continue
            out[remote] = dv
    for key, value in _PURCHASE_RECEIPT_CODE_FALLBACKS.items():
        if not _non_empty(out.get(key)):
            out[key] = value
    return out


async def enrich_kingdee_warehouse_push_config(
    tenant_id: int,
    config: Dict[str, Any],
    *,
    connector_type: str = "kingdee_cosmic",
    expected_related_document: Optional[str] = None,
) -> Dict[str, Any]:
    """推送前：采购入库头字段继承、Save 样例、连接器组织编码。"""
    out = strip_mismatched_std_document_types(
        dict(config),
        expected_related_document=expected_related_document,
    )
    out = await _merge_header_from_save_api(
        tenant_id,
        out,
        expected_related_document=expected_related_document,
    )
    for key in _WORKFLOW_BOOL_KEYS:
        if out.get(key) is None:
            out[key] = True
    form_id = str(out.get("form_id") or "").strip()
    if form_id.startswith("im_"):
        out = await attach_im_operate_apis_from_save_binding(
            tenant_id, out, im_bill=form_id
        )
    if _has_org(out):
        return out
    from core.models.integration_config import IntegrationConfig
    from core.services.integration.kingdee_cosmic_paths import (
        resolve_kingdee_cosmic_createorg_number,
    )

    code = str(out.get("connection_code") or "").strip()
    query = IntegrationConfig.filter(
        tenant_id=tenant_id,
        type=str(connector_type or "kingdee_cosmic").strip() or "kingdee_cosmic",
        is_active=True,
        deleted_at__isnull=True,
    )
    connection = await query.filter(code=code).first() if code else await query.first()
    if not connection:
        return out
    conn_cfg = connection.get_config()
    if not isinstance(conn_cfg, dict):
        return out
    org = resolve_kingdee_cosmic_createorg_number(conn_cfg)
    if not org:
        return out
    out["org_number"] = org
    if not _non_empty(out.get("bizorg_number")):
        out["bizorg_number"] = org
    for key in _WORKFLOW_BOOL_KEYS:
        if out.get(key) is None:
            out[key] = True
    return out
