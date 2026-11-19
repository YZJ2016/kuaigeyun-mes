"""金蝶分录 location_number 与本地库位编码解析。"""
from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence, Tuple

from apps.master_data.models.warehouse import StorageLocation


def index_storage_locations_for_inbound_sync(
    storage_locations: Sequence[StorageLocation],
) -> Tuple[
    Dict[str, StorageLocation],
    Dict[Tuple[int, str], StorageLocation],
    Dict[str, StorageLocation],
]:
    """入站同步：本地 code、仓库+苍穹 source、名称 三类索引。"""
    by_code: Dict[str, StorageLocation] = {}
    by_wh_source: Dict[Tuple[int, str], StorageLocation] = {}
    by_name: Dict[str, StorageLocation] = {}
    for loc in storage_locations:
        code = str(loc.code or "").strip()
        if code:
            by_code[code] = loc
            upper = code.upper()
            if upper != code:
                by_code[upper] = loc
        name = str(loc.name or "").strip()
        if name:
            by_name[name] = loc
        src = str(getattr(loc, "source_location_code", None) or "").strip().upper()
        wh_id = getattr(loc, "warehouse_id", None)
        if src and wh_id is not None:
            try:
                by_wh_source[(int(wh_id), src)] = loc
            except (TypeError, ValueError):
                pass
    return by_code, by_wh_source, by_name


def resolve_storage_location_for_inbound_sync(
    *,
    warehouse_id: int,
    source_location_key: str,
    location_by_code: Mapping[str, StorageLocation],
    location_by_wh_source: Mapping[Tuple[int, str], StorageLocation],
    location_by_name: Mapping[str, StorageLocation],
    location_name: str = "",
) -> Optional[StorageLocation]:
    """金蝶行上常为苍穹仓位号；本地可能为 仓库_库位 复合编码。"""
    key = str(source_location_key or "").strip()
    if key:
        direct = location_by_code.get(key) or location_by_code.get(key.upper())
        if direct is not None:
            wh = getattr(direct, "warehouse_id", None)
            if wh is None or int(wh) == int(warehouse_id):
                return direct
        matched = location_by_wh_source.get((int(warehouse_id), key.upper()))
        if matched is not None:
            return matched
    name = str(location_name or "").strip()
    if name:
        by_name = location_by_name.get(name)
        if by_name is not None:
            wh = getattr(by_name, "warehouse_id", None)
            if wh is None or int(wh) == int(warehouse_id):
                return by_name
    return None


def derive_kingdee_location_number_from_composite_local_code(
    local_code: str,
    warehouse_number: str,
) -> Optional[str]:
    """与 warehouse_location_ref 本地 ``仓库_苍穹库位`` 编码规则互逆（须已知行仓库编码）。"""
    local = str(local_code or "").strip()
    wh = str(warehouse_number or "").strip()
    if not local or not wh:
        return None
    prefix = f"{wh}_"
    if local.startswith(prefix):
        return local[len(prefix) :]
    upper_prefix = f"{wh.upper()}_"
    if local.upper().startswith(upper_prefix):
        return local[len(upper_prefix) :]
    return None


def resolve_kingdee_location_number_from_codes(
    *,
    local_code: str,
    source_location_code: Optional[str] = None,
    warehouse_number: Optional[str] = None,
) -> str:
    ext = str(source_location_code or "").strip()
    local = str(local_code or "").strip()
    if ext and local and ext.upper() != local.upper():
        return ext
    wh = str(warehouse_number or "").strip()
    if wh and local:
        derived = derive_kingdee_location_number_from_composite_local_code(local, wh)
        if derived:
            return derived
    if ext:
        return ext
    return local


def kingdee_location_number_from_storage_location(
    loc: StorageLocation,
    *,
    warehouse_number: Optional[str] = None,
) -> str:
    return resolve_kingdee_location_number_from_codes(
        local_code=str(loc.code or "").strip(),
        source_location_code=str(getattr(loc, "source_location_code", None) or "").strip() or None,
        warehouse_number=warehouse_number,
    )


async def lookup_storage_location_for_kingdee_push(
    tenant_id: int,
    *,
    location_id: Optional[int] = None,
    location_code: Optional[str] = None,
) -> Optional[StorageLocation]:
    """按 id 或本地/苍穹编码查库位（推送金蝶时用，避免把 仓库_库位 复合码当苍穹号）。"""
    if location_id is not None:
        try:
            lid = int(location_id)
        except (TypeError, ValueError):
            lid = 0
        if lid > 0:
            loc = await StorageLocation.filter(
                tenant_id=tenant_id,
                id=lid,
                deleted_at__isnull=True,
            ).first()
            if loc:
                return loc

    code = str(location_code or "").strip()
    if not code:
        return None

    loc = await StorageLocation.filter(
        tenant_id=tenant_id,
        code=code,
        deleted_at__isnull=True,
    ).first()
    if loc:
        return loc

    code_upper = code.upper()
    if code_upper != code:
        loc = await StorageLocation.filter(
            tenant_id=tenant_id,
            code=code_upper,
            deleted_at__isnull=True,
        ).first()
        if loc:
            return loc

    return await StorageLocation.filter(
        tenant_id=tenant_id,
        source_location_code=code_upper,
        deleted_at__isnull=True,
    ).first()


async def build_kingdee_location_number_by_local_code(
    tenant_id: int,
    local_codes: Sequence[str],
    warehouse_number_by_local_code: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """批量：本地库位编码 → 金蝶 location_number。"""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in local_codes:
        code = str(raw or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(code)

    if not normalized:
        return {}

    upper_variants = {c.upper() for c in normalized}
    query_codes = list({*normalized, *upper_variants})

    rows = await StorageLocation.filter(
        tenant_id=tenant_id,
        code__in=query_codes,
        deleted_at__isnull=True,
    ).all()

    by_code: Dict[str, StorageLocation] = {}
    for row in rows:
        key = str(row.code or "").strip()
        if key:
            by_code[key] = row
            by_code[key.upper()] = row

    missing_upper = [c.upper() for c in normalized if c not in by_code and c.upper() not in by_code]
    if missing_upper:
        for row in await StorageLocation.filter(
            tenant_id=tenant_id,
            source_location_code__in=list(set(missing_upper)),
            deleted_at__isnull=True,
        ).all():
            src = str(row.source_location_code or "").strip().upper()
            if src:
                by_code[src] = row

    wh_by_code = warehouse_number_by_local_code or {}
    out: Dict[str, str] = {}
    for code in normalized:
        wh = str(wh_by_code.get(code) or "").strip()
        loc = by_code.get(code) or by_code.get(code.upper())
        if loc:
            num = kingdee_location_number_from_storage_location(loc, warehouse_number=wh or None)
        else:
            num = resolve_kingdee_location_number_from_codes(
                local_code=code,
                warehouse_number=wh or None,
            )
        if not num:
            continue
        if num.upper() != code.upper():
            out[code] = num
            continue
        if not wh or "_" not in code:
            out[code] = num
            continue
        derived = derive_kingdee_location_number_from_composite_local_code(code, wh)
        if derived:
            out[code] = derived
    return out


async def resolve_kingdee_location_number(
    tenant_id: int,
    *,
    location_id: Optional[int] = None,
    location_code: Optional[str] = None,
    warehouse_number: Optional[str] = None,
) -> str:
    loc = await lookup_storage_location_for_kingdee_push(
        tenant_id,
        location_id=location_id,
        location_code=location_code,
    )
    if loc:
        return kingdee_location_number_from_storage_location(
            loc,
            warehouse_number=warehouse_number,
        )
    return resolve_kingdee_location_number_from_codes(
        local_code=str(location_code or "").strip(),
        warehouse_number=warehouse_number,
    )
