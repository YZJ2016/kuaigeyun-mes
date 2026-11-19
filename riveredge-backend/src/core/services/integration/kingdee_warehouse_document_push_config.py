"""仓储类苍穹出站：共用头字段从采购入库推送配置补齐，组织可从连接器读取。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.services.integration.kingdee_cosmic_paths import resolve_kingdee_cosmic_createorg_number

_SHARED_HEADER_KEYS = (
    "org_number",
    "bizorg_number",
    "createorg_number",
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
    "connection_code",
    "save_api_uuid",
    "bizdept_number",
    "dept_number",
    "pickdept_number",
    "picker_number",
    "pickeroperator_number",
    "consumer_number",
    "customer_number",
    "bizoperator_operatornumber",
    "outownertype",
    "outkeepertype",
    "outowner_number",
    "outkeeper_number",
)

_WORKFLOW_BOOL_KEYS = (
    "submit_after_save",
    "audit_after_save",
)


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
    for key in _SHARED_HEADER_KEYS:
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


def _is_placeholder_header_value(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or text.upper().startswith("REPLACE_")


def _header_row_from_save_api_body(body: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    if "billentry" in body and isinstance(body.get("billentry"), list):
        return body
    return None


async def _merge_header_from_save_api(tenant_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
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
        for key in _SHARED_HEADER_KEYS:
            if _non_empty(out.get(key)):
                continue
            val = row.get(key)
            if not _is_placeholder_header_value(val):
                out[key] = val
        if not _non_empty(out.get("linetype_number")):
            entries = row.get("billentry")
            if isinstance(entries, list) and entries and isinstance(entries[0], dict):
                lt = entries[0].get("linetype_number")
                if not _is_placeholder_header_value(lt):
                    out["linetype_number"] = lt
    except Exception:
        return out
    return out


async def enrich_kingdee_warehouse_push_config(
    tenant_id: int,
    config: Dict[str, Any],
    *,
    connector_type: str = "kingdee_cosmic",
) -> Dict[str, Any]:
    """推送前：采购入库头字段继承、Save 样例、连接器组织编码。"""
    out = dict(config)
    out = await _merge_header_from_save_api(tenant_id, out)
    if _has_org(out):
        return out
    from core.models.integration_config import IntegrationConfig

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
    return out
