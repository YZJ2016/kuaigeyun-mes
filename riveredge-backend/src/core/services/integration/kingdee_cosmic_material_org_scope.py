"""苍穹物料：子公司使用范围（bd_materialcommon）与集团主档（bd_material）交集。"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional
from uuid import UUID

from core.services.data.sync_source_rows import normalize_api_body_to_rows
from core.services.integration.kingdee_cosmic_material_active import (
    is_cosmic_material_row_active,
)
from core.services.integration.kingdee_cosmic_paths import resolve_kingdee_cosmic_createorg_number
from core.services.integration.kingdee_cosmic_since_filter import cosmic_paged_response_is_last_page
from infra.exceptions.exceptions import ValidationError

MATERIALCOMMON_BATCHQUERY_PATH = "kapi/v2/basedata/bd_materialcommon/batchQuery"
# xkallocationtype=1 与苍穹物料列表「使用状态=可用」一致；仅 enable/status 会多出未分配行。
# 必须带 org.number：OpenAPI data.org_number 过滤在现场会被忽略，须行级再筛，
# 否则会把各组织已分配物料并成并集（能以信曾 2431，金蝶业务组织列表实为 2403）。
MATERIAL_ORG_SCOPE_SELECT = "masterid.number,enable,status,xkallocationtype,org.number"


def _material_number_from_common_row(row: Dict[str, Any]) -> str:
    raw = row.get("masterid_number") or row.get("number")
    return str(raw or "").strip()


def _org_number_from_common_row(row: Dict[str, Any]) -> str:
    return str(row.get("org_number") or row.get("org.number") or "").strip()


def filter_cosmic_material_rows_by_org_numbers(
    rows: List[Dict[str, Any]],
    allowed_numbers: FrozenSet[str],
) -> List[Dict[str, Any]]:
    # 空集合表示「该组织无已分配物料」，不得回退成不过滤（曾把多组织并集全放行）
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


async def fetch_cosmic_material_org_allowed_numbers(
    tenant_id: int,
    *,
    connection_uuid: UUID,
    org_number: str,
    active_only: bool = True,
    timeout: float = 120.0,
) -> FrozenSet[str]:
    """
    拉取已分配到管理组织 org_number 的物料编码集合（bd_materialcommon/batchQuery）。
    集团创建、子公司使用时，bd_material  alone 会多出行。

    注意：请求体 data.org_number 在部分苍穹环境不生效（与空 data 返回同一全量）；
    必须以响应行 org.number / org_number 与目标组织相等后再计入集合。
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
            "select": MATERIAL_ORG_SCOPE_SELECT,
        }
        result = await svc.probe_api_draft(
            tenant_id,
            connection_uuid=connection_uuid,
            path=MATERIALCOMMON_BATCHQUERY_PATH,
            method="POST",
            request_body=body,
            timeout=timeout,
        )
        status_code = int(result.get("status_code") or 0)
        if status_code < 200 or status_code >= 300:
            detail = result.get("body")
            if isinstance(detail, dict) and detail.get("message"):
                raise ValidationError(f"苍穹物料组织公共信息查询失败：{detail['message']}")
            raise ValidationError(f"苍穹物料组织公共信息查询失败：HTTP {status_code}")

        chunk = normalize_api_body_to_rows(result.get("body"))
        if not chunk:
            break
        # 末页判定必须用过滤前条数；active 过滤后再比 pageSize 会误判末页（曾卡在 999）
        raw_chunk_len = len(chunk)
        for r in chunk:
            if not isinstance(r, dict):
                continue
            # 请求侧 org 过滤不可靠：只认本行组织
            if _org_number_from_common_row(r) != org:
                continue
            num = _material_number_from_common_row(r)
            if not num:
                continue
            if active_only:
                if not is_cosmic_material_row_active(
                    {"enable": r.get("enable"), "status": r.get("status")}
                ):
                    continue
                # 与界面「可用」一致：须已分配（xkallocationtype=1）
                if str(r.get("xkallocationtype") or "").strip() != "1":
                    continue
            allowed.add(num)
        if cosmic_paged_response_is_last_page(
            result.get("body"),
            chunk_len=raw_chunk_len,
            page_size=page_size,
        ):
            break
    return frozenset(allowed)


def resolve_connector_org_for_material_scope(cfg: Optional[Dict[str, Any]]) -> str:
    return resolve_kingdee_cosmic_createorg_number(cfg)
