"""金蝶推送：分录 location_number 解析（优先苍穹 source_location_code）。"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from apps.master_data.models.warehouse import StorageLocation, Warehouse
from apps.master_data.utils.kingdee_location_number import (
    build_kingdee_location_number_by_local_code,
    kingdee_location_number_from_storage_location,
    resolve_kingdee_location_number,
)


def warehouse_number_by_item_id_from_wh_map(
    items: Sequence[Any],
    wh_map: Mapping[int, Optional[str]],
) -> Dict[int, str]:
    """明细 id → 金蝶仓库编码（wh_map 常用 key 0 为单据头默认仓）。"""
    out: Dict[int, str] = {}
    header_wh = str(wh_map.get(0) or "").strip()
    for item in items:
        try:
            item_id = int(getattr(item, "id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if item_id <= 0:
            continue
        wh = str(wh_map.get(item_id) or header_wh or "").strip()
        if wh:
            out[item_id] = wh
    return out


async def build_kingdee_location_number_by_item_id(
    tenant_id: int,
    items: Sequence[Any],
    config: Optional[Mapping[str, Any]] = None,
    *,
    warehouse_number_by_item_id: Optional[Mapping[int, str]] = None,
    default_warehouse_number: Optional[str] = None,
) -> Dict[int, str]:
    """按明细 id 批量解析金蝶 location_number（一次查库）。"""
    cfg = config or {}
    default_loc = str(cfg.get("location_number") or "").strip()
    default_wh = str(default_warehouse_number or cfg.get("warehouse_number") or "").strip()

    location_ids: list[int] = []
    for item in items:
        lid = getattr(item, "location_id", None)
        if lid is None:
            continue
        try:
            parsed = int(lid)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            location_ids.append(parsed)

    loc_by_id: Dict[int, StorageLocation] = {}
    if location_ids:
        rows = await StorageLocation.filter(
            tenant_id=tenant_id,
            id__in=list(set(location_ids)),
            deleted_at__isnull=True,
        ).all()
        loc_by_id = {int(row.id): row for row in rows}

    warehouse_ids = [
        int(loc.warehouse_id)
        for loc in loc_by_id.values()
        if getattr(loc, "warehouse_id", None)
    ]
    warehouse_code_by_id: Dict[int, str] = {}
    if warehouse_ids:
        for wh in await Warehouse.filter(
            tenant_id=tenant_id,
            id__in=list(set(warehouse_ids)),
            deleted_at__isnull=True,
        ).all():
            code = str(wh.code or "").strip()
            if code:
                warehouse_code_by_id[int(wh.id)] = code

    wh_by_item = dict(warehouse_number_by_item_id or {})
    pending_code_by_item_id: Dict[int, str] = {}
    pending_wh_by_item_id: Dict[int, str] = {}
    result: Dict[int, str] = {}
    for item in items:
        try:
            item_id = int(getattr(item, "id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if item_id <= 0:
            continue

        local_line = str(getattr(item, "location_code", None) or "").strip()
        loc_wh = ""
        loc_num = ""
        lid = getattr(item, "location_id", None)
        parsed_lid = 0
        if lid is not None:
            try:
                parsed_lid = int(lid)
            except (TypeError, ValueError):
                parsed_lid = 0
        if parsed_lid > 0 and parsed_lid in loc_by_id:
            loc = loc_by_id[parsed_lid]
            loc_wh = warehouse_code_by_id.get(int(loc.warehouse_id or 0), "")
            loc_num = kingdee_location_number_from_storage_location(
                loc,
                warehouse_number=loc_wh or None,
            )
        if loc_num and (not local_line or loc_num.upper() != local_line.upper()):
            result[item_id] = loc_num
            continue

        line_code = local_line
        if line_code:
            pending_code_by_item_id[item_id] = line_code
            if loc_wh:
                pending_wh_by_item_id[item_id] = loc_wh
        elif default_loc:
            pending_code_by_item_id[item_id] = default_loc

    if pending_code_by_item_id:
        wh_by_local: Dict[str, str] = {}
        for item_id, local_code in pending_code_by_item_id.items():
            wh = pending_wh_by_item_id.get(item_id) or str(
                wh_by_item.get(item_id) or default_wh or ""
            ).strip()
            if wh:
                wh_by_local[local_code] = wh
        kingdee_by_local = await build_kingdee_location_number_by_local_code(
            tenant_id,
            list(pending_code_by_item_id.values()),
            warehouse_number_by_local_code=wh_by_local,
        )
        for item_id, local_code in pending_code_by_item_id.items():
            loc_num = str(kingdee_by_local.get(local_code) or "").strip()
            if loc_num and loc_num.upper() != local_code.upper():
                result[item_id] = loc_num

    return result


def kingdee_location_number_for_item(
    item: Any,
    config: Mapping[str, Any],
    location_number_by_item_id: Optional[Dict[int, str]] = None,
) -> str:
    try:
        item_id = int(getattr(item, "id", 0) or 0)
    except (TypeError, ValueError):
        item_id = 0
    if location_number_by_item_id is not None and item_id > 0:
        resolved = str(location_number_by_item_id.get(item_id) or "").strip()
        if resolved:
            return resolved
        return str(config.get("location_number") or "").strip()
    return str(
        config.get("location_number")
        or config.get("location_code")
        or getattr(item, "location_code", None)
        or ""
    ).strip()


async def resolve_kingdee_location_number_for_push_item(
    tenant_id: int,
    item: Any,
    config: Optional[Mapping[str, Any]] = None,
) -> str:
    cfg = config or {}
    lid = getattr(item, "location_id", None)
    fallback = (
        getattr(item, "location_code", None)
        or cfg.get("location_number")
        or cfg.get("location_code")
    )
    wh = str(cfg.get("warehouse_number") or "").strip() or None
    return await resolve_kingdee_location_number(
        tenant_id,
        location_id=int(lid) if lid is not None else None,
        location_code=str(fallback) if fallback is not None else None,
        warehouse_number=wh,
    )
