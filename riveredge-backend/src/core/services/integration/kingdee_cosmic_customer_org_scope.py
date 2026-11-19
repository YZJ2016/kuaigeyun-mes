"""苍穹客户：自定义 getcustomer 按使用组织过滤（对齐供应商 getsupplier）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.services.integration.kingdee_cosmic_material_org_scope import (
    resolve_connector_org_for_material_scope,
)

CUSTOMER_GETCUSTOMER_PATH_SUFFIX = "/bd_customer/getcustomer"
_BIZ_BD_CUSTOMER_MARKER = "bd_customer"


def is_cosmic_customer_getcustomer_path(path: str) -> bool:
    lower = str(path or "").lower().replace("\\", "/")
    return CUSTOMER_GETCUSTOMER_PATH_SUFFIX in lower


def is_cosmic_customer_getcustomer_api(*, path: str, code: str = "") -> bool:
    """自定义 getcustomer：认路径或接口 code（避免库内 path 仍为标品时误升级）。"""
    if is_cosmic_customer_getcustomer_path(path):
        return True
    code_lower = str(code or "").strip().lower()
    return "getcustomer" in code_lower and _BIZ_BD_CUSTOMER_MARKER in code_lower


def filter_cosmic_customer_rows_by_management_org_number(
    rows: List[Dict[str, Any]],
    org_number: str,
) -> List[Dict[str, Any]]:
    """自定义 getcustomer：按返回行 org_number（使用组织）过滤，不用 createorg_number。"""
    org = str(org_number or "").strip()
    if not org or org.upper() == "BU-00000":
        return rows
    kept: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("org_number") or "").strip() == org:
            kept.append(row)
    return kept


def resolve_connector_org_for_customer_scope(cfg: Optional[Dict[str, Any]]) -> str:
    return resolve_connector_org_for_material_scope(cfg)
