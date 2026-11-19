"""苍穹主数据行有效判定：已审核（数据状态）+ 启用（使用状态）。

ExecuteBillQuery 的 FilterString 不适用 sbd getList；须在请求 data 与拉取后双重过滤。
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

# 与 kingdee_cosmic_api_presets.MASTER_DATA_INBOUND_FILTER 语义一致
_COSMIC_AUDITED_STATUS = "C"
_COSMIC_ENABLED = "1"


def is_cosmic_material_row_active(row: Dict[str, Any]) -> bool:
    """已审核 status=C 且使用状态 enable=1（暂存 status=A 等一律排除）。"""
    enable = str(row.get("enable") or "").strip()
    status = str(row.get("status") or "").strip().upper()
    return enable == _COSMIC_ENABLED and status == _COSMIC_AUDITED_STATUS


def filter_cosmic_material_rows_active(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if isinstance(r, dict) and is_cosmic_material_row_active(r)]


def is_cosmic_sbd_getlist_master_path(path: str) -> bool:
    """sbd 入站主数据 getList：拉取后可按 status/enable 复核，请求体可注入 data 筛选。

    bd_warelocareference/query 为仓库仓位关系，返回行无通用 status/enable，不得套用本路径。
    """
    lower = str(path or "").lower().replace("\\", "/")
    return any(
        token in lower
        for token in (
            "/bd_warehouse/getlist",
            "/bd_location/getlist",
        )
    )


def _data_field_blank(data: Dict[str, Any], key: str) -> bool:
    val = data.get(key)
    if val is None or val == "" or val == []:
        return True
    return False


def apply_cosmic_sbd_getlist_active_data(
    request_body: Optional[Dict[str, Any]],
    *,
    path: str,
    active_only: bool = True,
) -> Dict[str, Any]:
    """
    仓库/仓位 getList：源端按 data.status=已审核、data.enable=可用 收窄（审核状态优先于单独「可用」）。
    不覆盖用户已在 data 内显式填写的 status/enable。
    """
    body = copy.deepcopy(request_body) if isinstance(request_body, dict) else {}
    if not active_only or not is_cosmic_sbd_getlist_master_path(path):
        return body
    data = body.get("data")
    if not isinstance(data, dict):
        data = {}
        body["data"] = data
    if _data_field_blank(data, "status"):
        data["status"] = [_COSMIC_AUDITED_STATUS]
    if _data_field_blank(data, "enable"):
        data["enable"] = [_COSMIC_ENABLED]
    return body


def strip_cosmic_sbd_getlist_active_data(
    request_body: Optional[Dict[str, Any]],
    *,
    path: str,
    active_only: bool = True,
) -> Dict[str, Any]:
    """关闭「仅有效」时去掉默认注入的 status/enable，便于全量调试。"""
    body = copy.deepcopy(request_body) if isinstance(request_body, dict) else {}
    if active_only or not is_cosmic_sbd_getlist_master_path(path):
        return body
    data = body.get("data")
    if not isinstance(data, dict):
        return body
    if data.get("status") == [_COSMIC_AUDITED_STATUS]:
        data.pop("status", None)
    if data.get("enable") == [_COSMIC_ENABLED]:
        data.pop("enable", None)
    if not data:
        body["data"] = {}
    return body
