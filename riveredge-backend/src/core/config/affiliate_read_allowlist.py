"""
附属只读 GET 白名单（宿主:read OR 模块:read）。

新增 OR 须在此登记并在 PR 说明 reason；禁止在 *_route_access.py 内联多码 return。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from core.config.permission_contract import build_permission_code

_MASTER_DATA_APP = "master-data"

# GET 物料头下 BOM 版本列表（无更深子路径）
_BOM_BY_MATERIAL_LIST_RE = re.compile(r"/materials/bom/material/\d+/?$", re.IGNORECASE)

# 单位目录 / 换算只读（物料编辑下拉）
_UNIT_CATALOG_PATH_RE = re.compile(
    r"/materials/(?:units|unit-conversions)(?:/|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AffiliateReadEntry:
    id: str
    app_code: str
    method: str
    path_pattern: re.Pattern[str]
    permission_codes: tuple[str, ...]
    reason: str


AFFILIATE_READ_ENTRIES: tuple[AffiliateReadEntry, ...] = (
    AffiliateReadEntry(
        id="master_data_bom_by_material_list",
        app_code=_MASTER_DATA_APP,
        method="GET",
        path_pattern=_BOM_BY_MATERIAL_LIST_RE,
        permission_codes=(
            build_permission_code(_MASTER_DATA_APP, "material", "read"),
            build_permission_code(_MASTER_DATA_APP, "process:engineering-bom", "read"),
        ),
        reason="物料编辑回显默认 BOM 版本列表",
    ),
    AffiliateReadEntry(
        id="master_data_unit_catalog_read",
        app_code=_MASTER_DATA_APP,
        method="GET",
        path_pattern=_UNIT_CATALOG_PATH_RE,
        permission_codes=(
            build_permission_code(_MASTER_DATA_APP, "material-unit", "read"),
            build_permission_code(_MASTER_DATA_APP, "material", "read"),
        ),
        reason="物料表单单位下拉与单位目录只读",
    ),
)


def resolve_affiliate_read_codes(
    app_code: str,
    method: str,
    path: str,
) -> list[str] | None:
    """匹配白名单则返回 OR 权限码列表；否则 None。"""
    app = (app_code or "").strip().lower()
    m = (method or "").upper()
    p = path or ""
    for entry in AFFILIATE_READ_ENTRIES:
        if entry.app_code != app:
            continue
        if entry.method != m:
            continue
        if entry.path_pattern.search(p):
            return list(entry.permission_codes)
    return None


def permission_codes_for_entry_id(entry_id: str) -> tuple[str, ...]:
    for entry in AFFILIATE_READ_ENTRIES:
        if entry.id == entry_id:
            return entry.permission_codes
    raise KeyError(f"Unknown affiliate read entry: {entry_id!r}")


__all__ = [
    "AffiliateReadEntry",
    "AFFILIATE_READ_ENTRIES",
    "resolve_affiliate_read_codes",
    "permission_codes_for_entry_id",
]
