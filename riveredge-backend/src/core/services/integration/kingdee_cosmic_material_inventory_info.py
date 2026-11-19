"""苍穹物料库存信息（bd_materialinventoryinfo）：批号/序列号与界面「库存信息」页签一致。"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from core.services.data.sync_source_rows import normalize_api_body_to_rows
from core.services.integration.kingdee_cosmic_material_active import is_cosmic_material_row_active
from core.services.integration.kingdee_cosmic_since_filter import cosmic_paged_response_is_last_page
from infra.exceptions.exceptions import ValidationError

# 开放平台发布在供应链基础资料 appid=sbd（非 basedata；后者网关 2530）
MATERIAL_INVENTORY_INFO_BATCHQUERY_PATH = (
    "kapi/v2/sbd/bd_materialinventoryinfo/batchQuery"
)
# 自建操作 API（对齐 getsupplier/getcustomer）；标品 batchQuery 612 时可改用，仍受同一业务对象权限约束
MATERIAL_INVENTORY_INFO_GETMATINFO_PATH = (
    "kapi/v2/fd81/sbd/bd_materialinventoryinfo/getmatinfo"
)
MATERIAL_INVENTORY_INFO_FETCH_PATHS = (
    MATERIAL_INVENTORY_INFO_BATCHQUERY_PATH,
    MATERIAL_INVENTORY_INFO_GETMATINFO_PATH,
)
MATERIAL_INVENTORY_INFO_SYNC_SELECT = (
    "masterid.number,enablelot,enableserial,masterid_enablelot,masterid_enableserial,"
    "status,enable,org.number"
)


def _org_number_from_inventory_info_row(row: Dict[str, Any]) -> str:
    return str(row.get("org_number") or row.get("org.number") or "").strip()


def _inventory_tracking_flags_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """库存信息行：批号/序列号以 enablelot 为准，缺省时读 masterid_enablelot。"""
    enablelot = row.get("enablelot")
    if enablelot is None:
        enablelot = row.get("masterid_enablelot")
    enableserial = row.get("enableserial")
    if enableserial is None:
        enableserial = row.get("masterid_enableserial")
    out: Dict[str, Any] = {}
    if enablelot is not None:
        out["enablelot"] = enablelot
    if enableserial is not None:
        out["enableserial"] = enableserial
    return out


def _validation_error_for_inventory_info_response(body: Any, *, http_status: int) -> Optional[str]:
    if not isinstance(body, dict):
        if http_status < 200 or http_status >= 300:
            return f"苍穹物料库存信息查询失败：HTTP {http_status}"
        return None
    error_code = str(body.get("errorCode") or body.get("error_code") or "").strip()
    if error_code in {"", "0", "success", "SUCCESS"}:
        status = body.get("status")
        if status is False or str(status).lower() in {"false", "0"}:
            msg = str(body.get("message") or body.get("messagecn") or "").strip()
            return msg or "苍穹物料库存信息查询失败"
        return None
    msg = str(body.get("message") or body.get("messagecn") or body.get("msg") or "").strip()
    if error_code == "612":
        return (
            "金蝶 OpenAPI 612：集成连接器换票身份对应用 sbd、业务对象 bd_materialinventoryinfo "
            "无查询功能权限（与 ERP 界面能否打开「物料库存信息列表」不是同一套授权）。"
            "开放平台「API 组合」里能看到 batchQuery 只表示接口已发布，还须把该 API 授权给"
            "连接器使用的第三方应用（如 client_id=mes_conn）并给代理用户分配与 bd_warehouse 同级的"
            "库存信息查询权限。对照：同连接器 kapi/v2/sbd/bd_warehouse/getList 通常可正常调用。"
            f"路径含 {MATERIAL_INVENTORY_INFO_BATCHQUERY_PATH}、自建 getmatinfo 等；"
            "612 时换接口不能绕过，须给代理用户开 bd_materialinventoryinfo 查询功能权限。"
        )
    if error_code == "2530":
        return (
            "物料库存信息接口路由未发布（2530）。"
            f"请确认开放平台已发布 POST {MATERIAL_INVENTORY_INFO_BATCHQUERY_PATH}。"
        )
    return msg or f"苍穹物料库存信息查询失败（{error_code}）"


def material_number_from_inventory_info_row(row: Dict[str, Any]) -> str:
    raw = row.get("masterid_number") or row.get("masterid.number") or row.get("number")
    return str(raw or "").strip()


def apply_inventory_tracking_to_material_rows(
    rows: list[Dict[str, Any]],
    tracking_by_number: Dict[str, Dict[str, Any]],
) -> list[Dict[str, Any]]:
    """用库存信息页签的 enablelot/enableserial 覆盖主档行（按物料编码）。"""
    if not tracking_by_number:
        return rows
    out: list[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        num = str(item.get("number") or item.get("masterid_number") or "").strip()
        if num:
            inv = tracking_by_number.get(num)
            if inv:
                if "enablelot" in inv:
                    item["enablelot"] = inv["enablelot"]
                if "enableserial" in inv:
                    item["enableserial"] = inv["enableserial"]
        out.append(item)
    return out


async def fetch_cosmic_material_inventory_tracking_by_number(
    tenant_id: int,
    *,
    connection_uuid: UUID,
    org_number: Optional[str] = None,
    active_only: bool = True,
    timeout: float = 120.0,
) -> Dict[str, Dict[str, Any]]:
    """
    拉取管理组织下物料库存信息的批号/序列号开关。

    金蝶界面「启用批号管理」在库存信息页签（bd_materialinventoryinfo），
    与 bd_material 主档 enablelot 可能不一致。
    """
    from core.services.application.api_service import APIService
    from core.services.integration.kingdee_bill_query_page import MAX_PAGES

    org = str(org_number or "").strip()
    svc = APIService()
    page_size = 1000
    last_error: Optional[ValidationError] = None

    for path_index, api_path in enumerate(MATERIAL_INVENTORY_INFO_FETCH_PATHS):
        tracking: Dict[str, Dict[str, Any]] = {}
        try:
            for page_no in range(1, MAX_PAGES + 1):
                data: Dict[str, Any] = {}
                if org and org.upper() != "BU-00000":
                    data["org_number"] = [org]
                body = {
                    "data": data,
                    "pageNo": page_no,
                    "pageSize": page_size,
                    "select": MATERIAL_INVENTORY_INFO_SYNC_SELECT,
                }
                result = await svc.probe_api_draft(
                    tenant_id,
                    connection_uuid=connection_uuid,
                    path=api_path,
                    method="POST",
                    request_body=body,
                    timeout=timeout,
                )
                status_code = int(result.get("status_code") or 0)
                body_raw = result.get("body")
                err_msg = _validation_error_for_inventory_info_response(
                    body_raw, http_status=status_code
                )
                if err_msg:
                    raise ValidationError(err_msg)

                chunk = normalize_api_body_to_rows(body_raw)
                if not chunk:
                    break
                raw_chunk_len = len(chunk)
                for row in chunk:
                    if not isinstance(row, dict):
                        continue
                    # data.org_number 在部分环境不生效；若行上带回了 org 则行级再筛。
                    # 本环境 batchQuery 常不返回 org 字段（全空），此时不能误滤成 0 条，
                    # 批号开关随后只落到已按 materialcommon 组织范围筛过的物料行上。
                    if org and org.upper() != "BU-00000":
                        row_org = _org_number_from_inventory_info_row(row)
                        if row_org and row_org != org:
                            continue
                    if active_only and not is_cosmic_material_row_active(
                        {"enable": row.get("enable"), "status": row.get("status")}
                    ):
                        continue
                    num = material_number_from_inventory_info_row(row)
                    if not num:
                        continue
                    flags = _inventory_tracking_flags_from_row(row)
                    if not flags:
                        continue
                    tracking[num] = flags
                if cosmic_paged_response_is_last_page(
                    result.get("body"),
                    chunk_len=raw_chunk_len,
                    page_size=page_size,
                ):
                    break
            return tracking
        except ValidationError as exc:
            last_error = exc
            if path_index == 0 and "612" in str(exc):
                continue
            raise
    if last_error:
        raise last_error
    return {}
