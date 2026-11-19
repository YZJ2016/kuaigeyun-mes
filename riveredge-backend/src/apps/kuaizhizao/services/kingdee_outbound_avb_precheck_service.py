"""出库确认前金蝶可用量预检（仅无感外推会执行的租户）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from infra.exceptions.exceptions import BusinessLogicError, ValidationError

from apps.kuaizhizao.services.inventory_sync_service import (
    _inventory_cell,
    _inventory_quantity,
)
from apps.master_data.services.master_data_sync_common import (
    fetch_sync_rows,
    lookup_mapped_source_value,
)
from apps.kuaizhizao.models.inventory_sync_binding import InventorySyncBinding
from core.services.integration.document_push_silent import silent_push_would_run_on_confirm

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutboundAvbDemandLine:
    material_id: int
    material_code: str
    material_name: Optional[str]
    warehouse_id: Optional[int]
    location_code: Optional[str]
    batch_no: Optional[str]
    quantity: Decimal


def _nested_str(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        found, val = lookup_mapped_source_value(row, key)
        if found and val not in (None, ""):
            return str(val).strip()
        text = _inventory_cell(row, key)
        if text:
            return text
    return ""


def _kingdee_location_matches_name(row: Dict[str, Any], location_name: str) -> bool:
    """用本系统库位名称对金蝶仓位；禁止解析本地复合库位编码。"""
    want = str(location_name or "").strip()
    if not want:
        return True
    kd_number = _nested_str(
        row, "location.number", "location_number", "location.code", "location_code"
    )
    kd_name = _nested_str(row, "location.name", "location_name")
    want_u = want.upper()
    return any(v.upper() == want_u for v in (kd_number, kd_name) if v)


def _match_row_to_demand(
    row: Dict[str, Any],
    *,
    material_code: str,
    warehouse_code: str,
    location_name: Optional[str],
    batch_no: Optional[str],
    use_lot: bool,
) -> bool:
    mat = _nested_str(row, "material.number", "material_number", "material.code", "material_code")
    if mat != material_code:
        return False
    wh = _nested_str(row, "warehouse.number", "warehouse_number", "warehouse.code", "warehouse_code")
    if warehouse_code and wh and wh != warehouse_code:
        return False
    if location_name:
        if not _kingdee_location_matches_name(row, location_name):
            return False
    if use_lot and batch_no:
        lot = _nested_str(row, "lotnum", "lot_number", "lot.number", "batch_no", "batch_number")
        if lot and lot != batch_no.strip():
            return False
    return True


def _sum_kingdee_avb(
    rows: Sequence[Dict[str, Any]],
    *,
    material_code: str,
    warehouse_code: str,
    location_name: Optional[str],
    batch_no: Optional[str],
    use_lot: bool,
) -> Decimal:
    total = Decimal("0")
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not _match_row_to_demand(
            row,
            material_code=material_code,
            warehouse_code=warehouse_code,
            location_name=location_name,
            batch_no=batch_no,
            use_lot=use_lot,
        ):
            continue
        qty = _inventory_quantity(row)
        if qty is None:
            continue
        total += Decimal(str(qty))
    return total


async def _resolve_location_name_by_local_code(
    tenant_id: int,
    lines: Sequence[OutboundAvbDemandLine],
) -> Dict[Tuple[Optional[int], str], str]:
    """
    (warehouse_id, 本地库位编码) → 库位名称。
    金蝶侧仓位与名称一致（如 0600 / 无货架）；本地编码可能是 W1004_0600，禁止字符串解析。
    """
    from apps.master_data.models.warehouse import StorageLocation

    codes = sorted(
        {
            str(line.location_code or "").strip()
            for line in lines
            if str(line.location_code or "").strip()
        }
    )
    if not codes:
        return {}

    rows = await StorageLocation.filter(
        tenant_id=tenant_id,
        code__in=codes,
        deleted_at__isnull=True,
    ).all()

    by_wh_code: Dict[Tuple[Optional[int], str], str] = {}
    by_code_only: Dict[str, str] = {}
    for row in rows:
        code = str(row.code or "").strip()
        name = str(row.name or "").strip()
        if not code or not name:
            continue
        wh_id = int(row.warehouse_id) if getattr(row, "warehouse_id", None) else None
        by_wh_code[(wh_id, code)] = name
        by_code_only.setdefault(code, name)

    out: Dict[Tuple[Optional[int], str], str] = {}
    for line in lines:
        code = str(line.location_code or "").strip()
        if not code:
            continue
        wh_id = int(line.warehouse_id) if line.warehouse_id else None
        name = by_wh_code.get((wh_id, code)) or by_code_only.get(code)
        if name:
            out[(wh_id, code)] = name
    return out


async def _resolve_inventory_balance_source(
    tenant_id: int,
) -> Optional[Tuple[Dict[str, Any], str]]:
    """返回 (source_dict, api_path_lower)。"""
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


async def assert_kingdee_avb_before_outbound_confirm(
    tenant_id: int,
    entity_type: str,
    lines: Sequence[OutboundAvbDemandLine],
) -> None:
    """
    若本租户该单据会在确认时无感外推金蝶，则在本地过账前预检金蝶可用量。
    未配置即时库存余额接口时跳过（仍由确认后外推失败回滚兜底）。
    """
    if not lines:
        return
    if not await silent_push_would_run_on_confirm(tenant_id, entity_type):
        return

    resolved = await _resolve_inventory_balance_source(tenant_id)
    if not resolved:
        logger.info(
            "金蝶可用预检跳过：未配置 getInventoryAvbQty 即时库存来源 tenant_id=%s entity_type=%s",
            tenant_id,
            entity_type,
        )
        return

    source, path_lower = resolved
    material_codes = sorted(
        {str(line.material_code or "").strip() for line in lines if str(line.material_code or "").strip()}
    )
    if not material_codes:
        raise ValidationError("金蝶可用预检失败：明细缺少物料编码")

    fill_path = str(source.get("batch_fill_path") or "").strip() or "params.material"
    try:
        raw_rows = await fetch_sync_rows(
            tenant_id,
            source_type="api",
            api_uuid=str(source.get("api_uuid") or "").strip(),
            dataset_uuid=None,
            active_only=False,
            request_body=source.get("request_body") if isinstance(source.get("request_body"), dict) else None,
            request_params=source.get("request_params") if isinstance(source.get("request_params"), dict) else None,
            batch_fill_path=fill_path,
            batch_fill_values=material_codes,
        )
    except Exception as exc:
        raise BusinessLogicError(f"金蝶可用量查询失败，已中止确认：{exc}") from exc

    use_lot = "getinventorydetail" in path_lower

    from apps.kuaizhizao.services.inventory_service import InventoryService
    from apps.master_data.models.warehouse import Warehouse

    wh_ids = {int(line.warehouse_id) for line in lines if line.warehouse_id}
    warehouses = (
        await Warehouse.filter(tenant_id=tenant_id, id__in=list(wh_ids), deleted_at__isnull=True).all()
        if wh_ids
        else []
    )
    wh_code_by_id = {int(w.id): str(w.code or "").strip() for w in warehouses}
    location_name_by_key = await _resolve_location_name_by_local_code(tenant_id, lines)

    shortages: List[str] = []

    for line in lines:
        need = Decimal(str(line.quantity or 0))
        if need <= 0:
            continue
        wh_code = wh_code_by_id.get(int(line.warehouse_id or 0), "")
        batch = str(line.batch_no or "").strip() or None
        loc = str(line.location_code or "").strip() or None
        wh_id = int(line.warehouse_id) if line.warehouse_id else None
        loc_name: Optional[str] = None
        if loc:
            loc_name = location_name_by_key.get((wh_id, loc)) or next(
                (name for (wid, code), name in location_name_by_key.items() if code == loc),
                None,
            )

        kd_avb = _sum_kingdee_avb(
            raw_rows,
            material_code=str(line.material_code).strip(),
            warehouse_code=wh_code,
            location_name=loc_name,
            batch_no=batch,
            use_lot=use_lot and bool(batch),
        )
        if kd_avb >= need:
            continue

        # 本地 InventoryService.get_quantity 没有 location_code；仓位只参与金蝶行匹配。
        local_avb = await InventoryService.get_quantity(
            tenant_id,
            line.material_id,
            warehouse_id=line.warehouse_id,
            batch_no=batch,
        )
        label = str(line.material_name or line.material_code or line.material_id)
        wh_part = f"仓库 {wh_code}" if wh_code else "仓库未指定"
        loc_part = f" 仓位 {loc_name or loc}" if (loc_name or loc) else ""
        batch_part = f" 批号 {batch}" if batch else ""
        shortages.append(
            f"{label}（{wh_part}{loc_part}{batch_part}）：本系统可用 {local_avb}，金蝶可用 {kd_avb}，本次需 {need}"
        )

    if shortages:
        preview = "；".join(shortages[:6])
        if len(shortages) > 6:
            preview = f"{preview} 等 {len(shortages)} 行"
        raise BusinessLogicError(f"金蝶可用库存不足，已中止确认：{preview}")
