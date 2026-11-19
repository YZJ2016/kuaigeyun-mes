"""苍穹供应商：子公司使用范围（bd_suppliercommon）与集团主档（bd_supplier/query）交集。"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional
from uuid import UUID

from core.services.data.sync_source_rows import normalize_api_body_to_rows
from core.services.integration.kingdee_cosmic_material_active import (
    filter_cosmic_material_rows_active,
)
from core.services.integration.kingdee_cosmic_material_org_scope import (
    resolve_connector_org_for_material_scope,
)
from core.services.integration.kingdee_cosmic_since_filter import cosmic_paged_response_is_last_page
from infra.exceptions.exceptions import ValidationError

SUPPLIERCOMMON_BATCHQUERY_PATH = "kapi/v2/basedata/bd_suppliercommon/batchQuery"
SUPPLIER_GETSUPPLIER_PATH_SUFFIX = "/bd_supplier/getsupplier"
# 须带 org.number：data.org_number 在部分苍穹环境不生效，与物料 common 相同须行级再筛
SUPPLIER_ORG_SCOPE_SELECT = "masterid.number,enable,status,org.number"
_BIZ_BD_SUPPLIER_MARKER = "bd_supplier"
_COSMIC_AUDITED_STATUS = "C"
_COSMIC_ENABLED = "1"


def is_cosmic_supplier_getsupplier_path(path: str) -> bool:
    lower = str(path or "").lower().replace("\\", "/")
    return SUPPLIER_GETSUPPLIER_PATH_SUFFIX in lower


def is_cosmic_supplier_pbdfl_path(path: str) -> bool:
    """定制 pbdfl：返回 enable + group_*，无标品 status 列。"""
    lower = str(path or "").lower().replace("\\", "/")
    return "/bd_supplier/pbdfl/" in lower


def is_cosmic_supplier_getsupplier_api(*, path: str, code: str = "") -> bool:
    """自定义 getsupplier：认路径或接口 code（避免库内 path 仍为标品 query 时误走 suppliercommon）。"""
    if is_cosmic_supplier_getsupplier_path(path):
        return True
    code_lower = str(code or "").strip().lower()
    return "getsupplier" in code_lower and _BIZ_BD_SUPPLIER_MARKER in code_lower


def is_cosmic_supplier_row_active(row: Dict[str, Any], *, path: str = "") -> bool:
    """
    苍穹供应商行是否「仅有效」。

    - 标品 bd_supplier/query、getsupplier：status=C 且 enable=1（缺 status / 空串不放行）
    - 定制 pbdfl：无 status，仅 enable=1（套标品过滤器会把全部行滤成 0）
    """
    if not isinstance(row, dict):
        return False
    enable = str(row.get("enable") or "").strip()
    if enable != _COSMIC_ENABLED:
        return False
    if is_cosmic_supplier_pbdfl_path(path):
        return True
    status = str(row.get("status") or "").strip().upper()
    return status == _COSMIC_AUDITED_STATUS


def filter_cosmic_supplier_rows_active(
    rows: List[Dict[str, Any]],
    *,
    path: str = "",
) -> List[Dict[str, Any]]:
    return [
        r
        for r in rows
        if isinstance(r, dict) and is_cosmic_supplier_row_active(r, path=path)
    ]


def filter_cosmic_supplier_rows_by_management_org_number(
    rows: List[Dict[str, Any]],
    org_number: str,
) -> List[Dict[str, Any]]:
    """自定义 getsupplier：按返回行 org_number（使用组织）过滤，不用 createorg_number。"""
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


def _supplier_number_from_common_row(row: Dict[str, Any]) -> str:
    raw = row.get("masterid_number") or row.get("number")
    return str(raw or "").strip()


def filter_cosmic_supplier_rows_by_org_numbers(
    rows: List[Dict[str, Any]],
    allowed_numbers: FrozenSet[str],
) -> List[Dict[str, Any]]:
    if not allowed_numbers:
        return []
    kept: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        num = str(row.get("number") or "").strip()
        if num and num in allowed_numbers:
            kept.append(row)
    return kept


def _org_number_from_supplier_common_row(row: Dict[str, Any]) -> str:
    return str(row.get("org_number") or row.get("org.number") or "").strip()


async def fetch_cosmic_supplier_org_allowed_numbers(
    tenant_id: int,
    *,
    connection_uuid: UUID,
    org_number: str,
    active_only: bool = True,
    timeout: float = 120.0,
) -> FrozenSet[str]:
    """
    拉取已分配到管理组织 org_number 的供应商编码集合（bd_suppliercommon/batchQuery）。
    集团创建、子公司使用时，bd_supplier/query  alone 会多出行。

    请求体 data.org_number 在部分苍穹环境不生效，须按响应行 org.number 再筛。
    """
    org = str(org_number or "").strip()
    if not org:
        return frozenset()
    if org.upper() == "BU-00000":
        return frozenset()

    from core.services.application.api_service import APIService
    from core.services.integration.kingdee_bill_query_page import MAX_PAGES

    svc = APIService()
    allowed: set[str] = set()
    page_size = 1000
    for page_no in range(1, MAX_PAGES + 1):
        body = {
            "data": {"org_number": [org]},
            "pageNo": page_no,
            "pageSize": page_size,
            "select": SUPPLIER_ORG_SCOPE_SELECT,
        }
        result = await svc.probe_api_draft(
            tenant_id,
            connection_uuid=connection_uuid,
            path=SUPPLIERCOMMON_BATCHQUERY_PATH,
            method="POST",
            request_body=body,
            timeout=timeout,
        )
        status_code = int(result.get("status_code") or 0)
        if status_code < 200 or status_code >= 300:
            detail = result.get("body")
            if isinstance(detail, dict) and detail.get("message"):
                raise ValidationError(f"苍穹供应商组织公共信息查询失败：{detail['message']}")
            raise ValidationError(f"苍穹供应商组织公共信息查询失败：HTTP {status_code}")

        body_payload = result.get("body")
        if isinstance(body_payload, dict) and body_payload.get("status") is False:
            code = body_payload.get("errorCode") or body_payload.get("code")
            message = body_payload.get("message") or str(code or "未知错误")
            if str(code) == "2530" or "2530" in str(message):
                raise ValidationError(
                    "本环境开放平台未发布 bd_suppliercommon/batchQuery（2530）。"
                    "请在开放平台为 basedata 应用授权「供应商组织公共信息」batchQuery，"
                    "与物料 bd_materialcommon/batchQuery 相同，再重试供应商同步。"
                )
            raise ValidationError(f"苍穹供应商组织公共信息查询失败：{message}")

        chunk = normalize_api_body_to_rows(body_payload)
        if not chunk:
            break
        # 末页判定必须用过滤前条数；active 过滤后再比 pageSize 会误判末页
        raw_chunk_len = len(chunk)
        scoped = [
            r
            for r in chunk
            if isinstance(r, dict) and _org_number_from_supplier_common_row(r) == org
        ]
        if active_only:
            active_rows = filter_cosmic_material_rows_active(
                [
                    {
                        "number": _supplier_number_from_common_row(r),
                        "enable": r.get("enable"),
                        "status": r.get("status"),
                    }
                    for r in scoped
                ]
            )
            for row in active_rows:
                num = str(row.get("number") or "").strip()
                if num:
                    allowed.add(num)
        else:
            for row in scoped:
                num = _supplier_number_from_common_row(row)
                if num:
                    allowed.add(num)
        if cosmic_paged_response_is_last_page(
            body_payload,
            chunk_len=raw_chunk_len,
            page_size=page_size,
        ):
            break
    return frozenset(allowed)


def resolve_connector_org_for_supplier_scope(cfg: Optional[Dict[str, Any]]) -> str:
    return resolve_connector_org_for_material_scope(cfg)
