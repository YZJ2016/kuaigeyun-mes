"""出库推送金蝶：按仓位可用量选择库存类型（普通/赠品）。

本地台账不拆金蝶库存类型（同仓同位普通+赠品累加），配置默认常为普通(110)。
若仓位上普通可用不足、赠品(111)足够，推送须改写 invtype/outinvtype，否则金蝶报可用短缺。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from uuid import UUID

from infra.exceptions.exceptions import BusinessLogicError

from apps.kuaizhizao.services.inventory_sync_service import (
    _inventory_cell,
    _inventory_quantity,
)
from apps.master_data.services.master_data_sync_common import (
    fetch_sync_rows,
    lookup_mapped_source_value,
)
from apps.kuaizhizao.models.inventory_sync_binding import InventorySyncBinding

logger = logging.getLogger(__name__)


def _nested_str(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        found, val = lookup_mapped_source_value(row, key)
        if found and val not in (None, ""):
            return str(val).strip()
        text = _inventory_cell(row, key)
        if text:
            return text
    return ""


def _location_matches(row: Dict[str, Any], location_number: Optional[str]) -> bool:
    want = str(location_number or "").strip()
    if not want:
        return True
    kd_number = _nested_str(
        row, "location.number", "location_number", "location.code", "location_code"
    )
    kd_name = _nested_str(row, "location.name", "location_name")
    want_u = want.upper()
    return any(v.upper() == want_u for v in (kd_number, kd_name) if v)


def _row_invtype(row: Dict[str, Any]) -> Tuple[str, str]:
    number = _nested_str(row, "invtype.number", "invtype_number", "invType.number")
    name = _nested_str(row, "invtype.name", "invtype_name", "invType.name")
    return number, name


def _avb_by_invtype(
    rows: Sequence[Dict[str, Any]],
    *,
    material_code: str,
    warehouse_code: str,
    location_number: Optional[str],
) -> Dict[str, Tuple[Decimal, str]]:
    """invtype.number → (avbqty, invtype.name)。"""
    totals: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    names: Dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        mat = _nested_str(
            row, "material.number", "material_number", "material.code", "material_code"
        )
        if mat != material_code:
            continue
        wh = _nested_str(
            row, "warehouse.number", "warehouse_number", "warehouse.code", "warehouse_code"
        )
        if warehouse_code and wh and wh != warehouse_code:
            continue
        if not _location_matches(row, location_number):
            continue
        invtype_number, invtype_name = _row_invtype(row)
        if not invtype_number:
            continue
        qty = _inventory_quantity(row)
        if qty is None:
            continue
        totals[invtype_number] += Decimal(str(qty))
        if invtype_name:
            names[invtype_number] = invtype_name
    return {k: (v, names.get(k, "")) for k, v in totals.items()}


def pick_invtype_for_demand(
    by_type: Mapping[str, Tuple[Decimal, str]],
    *,
    need: Decimal,
    preferred: str,
) -> Optional[str]:
    """优先配置默认类型；不足则选能覆盖需求量的类型（可用量大者优先）。"""
    pref = str(preferred or "").strip()
    if pref:
        avail, _ = by_type.get(pref, (Decimal("0"), ""))
        if avail >= need:
            return pref
    candidates = [
        (number, avail)
        for number, (avail, _name) in by_type.items()
        if avail >= need
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[1], x[0] != pref, x[0]))
    return candidates[0][0]


def format_invtype_shortage(
    by_type: Mapping[str, Tuple[Decimal, str]],
    *,
    need: Decimal,
    preferred: str,
) -> str:
    pref = str(preferred or "").strip() or "（未配置）"
    if not by_type:
        return f"金蝶该仓位无库存明细，需 {need}，配置库存类型 {pref}"
    parts = []
    for number, (avail, name) in sorted(by_type.items(), key=lambda x: x[0]):
        label = f"{name}({number})" if name else number
        parts.append(f"{label}可用{avail}")
    return f"配置库存类型 {pref}；仓位分类型：{'、'.join(parts)}；需 {need}"


async def _resolve_inventory_balance_source(
    tenant_id: int,
) -> Optional[Tuple[Dict[str, Any], str]]:
    from core.services.application.api_service import APIService

    binding = await InventorySyncBinding.filter(tenant_id=tenant_id).first()
    if not binding:
        return None
    sources = list(getattr(binding, "sources", None) or [])
    api_svc = APIService()
    for src in sources:
        if str(src.get("kind") or "").strip() != "api":
            continue
        api_uuid = str(src.get("api_uuid") or "").strip()
        if not api_uuid:
            continue
        try:
            api = await api_svc.get_api_by_uuid(tenant_id, UUID(api_uuid))
        except Exception:
            continue
        path = str(getattr(api, "path", None) or "").lower()
        if "getinventoryavbqty" in path or "getinventorydetail" in path:
            return src, path
    return None


async def resolve_kingdee_out_invtype_by_item_id(
    tenant_id: int,
    *,
    items: Sequence[Any],
    quantity_attr: str = "outbound_quantity",
    quantity_by_item_id: Optional[Mapping[int, Any]] = None,
    warehouse_number_by_item_id: Mapping[int, Optional[str]],
    location_number_by_item_id: Mapping[int, str],
    preferred_invtype: str,
    dry_run: bool = False,
) -> Dict[int, str]:
    """
    按明细行解析应写入金蝶的库存类型编码。

    未配置即时库存接口时返回空 dict（沿用配置默认）。
    仓位上默认类型不足、其它类型足够时改写为足够的类型。
    """
    preferred = str(preferred_invtype or "").strip()
    if not items:
        return {}
    qty_override = quantity_by_item_id or {}

    demands: List[Tuple[int, str, str, Optional[str], Decimal]] = []
    for item in items:
        item_id = int(getattr(item, "id", 0) or 0)
        if item_id <= 0:
            continue
        if item_id in qty_override:
            qty = Decimal(str(qty_override.get(item_id) or 0))
        else:
            qty = Decimal(str(getattr(item, quantity_attr, None) or 0))
        if qty <= 0:
            continue
        material_code = str(getattr(item, "material_code", None) or "").strip()
        if not material_code:
            continue
        wh = str(warehouse_number_by_item_id.get(item_id) or "").strip()
        loc = str(location_number_by_item_id.get(item_id) or "").strip() or None
        demands.append((item_id, material_code, wh, loc, qty))

    if not demands:
        return {}

    resolved = await _resolve_inventory_balance_source(tenant_id)
    if not resolved:
        logger.info(
            "出库库存类型解析跳过：未配置即时库存来源 tenant_id=%s",
            tenant_id,
        )
        return {}

    source, _path = resolved
    material_codes = sorted({m for _i, m, _w, _l, _q in demands})
    fill_path = str(source.get("batch_fill_path") or "").strip() or "params.material"
    try:
        raw_rows = await fetch_sync_rows(
            tenant_id,
            source_type="api",
            api_uuid=str(source.get("api_uuid") or "").strip(),
            dataset_uuid=None,
            active_only=False,
            request_body=source.get("request_body")
            if isinstance(source.get("request_body"), dict)
            else None,
            request_params=source.get("request_params")
            if isinstance(source.get("request_params"), dict)
            else None,
            batch_fill_path=fill_path,
            batch_fill_values=material_codes,
        )
    except Exception as exc:
        if dry_run:
            logger.warning("dry_run 库存类型解析查询失败，沿用配置：%s", exc)
            return {}
        raise BusinessLogicError(f"金蝶库存类型解析失败，已中止推送：{exc}") from exc

    rows = [r for r in (raw_rows or []) if isinstance(r, dict)]
    out: Dict[int, str] = {}
    shortages: List[str] = []

    for item_id, material_code, wh, loc, need in demands:
        if not wh:
            continue
        by_type = _avb_by_invtype(
            rows,
            material_code=material_code,
            warehouse_code=wh,
            location_number=loc,
        )
        chosen = pick_invtype_for_demand(by_type, need=need, preferred=preferred)
        if chosen:
            out[item_id] = chosen
            if preferred and chosen != preferred:
                logger.info(
                    "出库推送改写库存类型 item_id=%s material=%s wh=%s loc=%s %s→%s need=%s",
                    item_id,
                    material_code,
                    wh,
                    loc,
                    preferred,
                    chosen,
                    need,
                )
            continue
        # 仓位有按类型拆行但无一够量：明确报错，避免金蝶笼统「短缺」
        if by_type:
            mat_label = material_code
            loc_part = f" 仓位 {loc}" if loc else ""
            shortages.append(
                f"{mat_label}（仓库 {wh}{loc_part}）："
                f"{format_invtype_shortage(by_type, need=need, preferred=preferred)}"
            )

    if shortages and not dry_run:
        preview = "；".join(shortages[:6])
        if len(shortages) > 6:
            preview = f"{preview} 等 {len(shortages)} 行"
        raise BusinessLogicError(
            f"金蝶按库存类型可用量不足，已中止推送：{preview}"
        )
    return out
