"""金蝶星空/苍穹主数据行「仅有效」过滤与 is_active 盖戳（物料/客户/供应商共用）。"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple

KingdeeEntityKind = Literal["material", "customer", "supplier"]


def _path_norm(api_path: str) -> str:
    return str(api_path or "").replace("\\", "/").lower()


def resolve_kingdee_path_family(api_path: str) -> Tuple[bool, bool]:
    """返回 (is_cosmic_family, is_galaxy_family)。二者互斥；皆假则走通用主数据过滤。"""
    from core.services.integration.kingdee_galaxy_material_active import (
        is_galaxy_execute_bill_query_path,
    )

    path = _path_norm(api_path)
    is_galaxy = is_galaxy_execute_bill_query_path(path)
    if is_galaxy:
        return False, True
    is_cosmic = (
        "/bd_material/batchquery" in path
        or "/bd_customer/" in path
        or "getcustomer" in path
        or "/bd_supplier/query" in path
        or "/bd_supplier/getsupplier" in path
    )
    return is_cosmic, False


def filter_kingdee_master_rows_active(
    rows: List[Dict[str, Any]],
    *,
    api_path: str,
    active_only: bool,
    entity: KingdeeEntityKind = "material",
) -> Tuple[List[Dict[str, Any]], int]:
    """按接口路径选择苍穹/星空/通用过滤。返回 (kept_rows, skipped_count)。"""
    del entity  # 路径族已区分；保留参数便于调用方标注语义
    if not active_only:
        return list(rows), 0
    from apps.master_data.services.master_data_sync_common import (
        filter_kingdee_approved_active_master_rows,
    )
    from core.services.integration.kingdee_cosmic_material_active import (
        filter_cosmic_material_rows_active,
    )
    from core.services.integration.kingdee_galaxy_material_active import (
        filter_galaxy_material_rows_active,
    )

    is_cosmic, is_galaxy = resolve_kingdee_path_family(api_path)
    before = len(rows)
    if is_cosmic:
        kept = filter_cosmic_material_rows_active(rows)
        return kept, before - len(kept)
    if is_galaxy:
        kept = filter_galaxy_material_rows_active(rows)
        return kept, before - len(kept)
    kept, skipped = filter_kingdee_approved_active_master_rows(rows)
    return kept, int(skipped or 0)


def stamp_kingdee_sync_is_active(
    rows: List[Dict[str, Any]],
    *,
    api_path: str,
) -> List[Dict[str, Any]]:
    """为行写入 sync_is_active，供字段映射落到本地 is_active。"""
    from core.services.integration.kingdee_cosmic_material_active import (
        is_cosmic_material_row_active,
    )
    from core.services.integration.kingdee_galaxy_material_active import (
        is_galaxy_material_row_active,
    )

    is_cosmic, is_galaxy = resolve_kingdee_path_family(api_path)
    stamped: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        if is_cosmic:
            item["sync_is_active"] = is_cosmic_material_row_active(item)
        elif is_galaxy:
            item["sync_is_active"] = is_galaxy_material_row_active(item)
        else:
            item["sync_is_active"] = True
        stamped.append(item)
    return stamped
