"""生产领料过账口径：正式发料 (GI) vs 线边备料转移（主仓→线边）。

线边备料单 / 补料申请 = 仅备料转移，不算工单耗用。
生产领料单确认 = 正式发料（扣减所选仓库库存），须回写明细已领数量。
历史补料曾误生成「已领料」领料单并做转移；靠备注识别并排除出 GI/齐套「已领」累计。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from apps.kuaizhizao.utils.mrp_quantity import MRP_QTY_STEP, mrp_qty

# 补料申请计入正式领料上限的状态（取消单不计入）
_MATERIAL_CALL_EXTRA_STATUSES = frozenset(
    {"pending", "processing", "partial", "completed"}
)

# 正式发料完成态（生产领料确认、退料选取、成本核算、报表等唯一口径）
PRODUCTION_PICKING_COST_ELIGIBLE_STATUSES = frozenset(
    {"已领料", "已确认", "picked", "confirmed", "已完成"}
)

# 历史叫料完成自动生成领料单的备注特征（主仓→线边转移，非正式发料）
_STAGING_PICKING_NOTE_MARKERS = (
    "主仓→线边",
    "叫料单",
)


def is_staging_transfer_picking_notes(notes: Optional[str]) -> bool:
    text = (notes or "").strip()
    if not text:
        return False
    return any(marker in text for marker in _STAGING_PICKING_NOTE_MARKERS)


def filter_gi_picking_ids(
    pickings: Sequence[object],
) -> List[int]:
    """从领料单列表中筛出正式发料单 ID（排除备料转移型历史单据）。"""
    result: List[int] = []
    for p in pickings:
        pid = getattr(p, "id", None)
        if pid is None:
            continue
        if is_staging_transfer_picking_notes(getattr(p, "notes", None)):
            continue
        result.append(int(pid))
    return result


def exclude_staging_picking_ids(
    picking_ids: Iterable[int],
    staging_ids: Iterable[int],
) -> List[int]:
    staging = {int(x) for x in staging_ids}
    return [int(x) for x in picking_ids if int(x) not in staging]


def resolve_work_order_pick_limit(
    allowed_bom: Decimal,
    over_issue_allowance_ratio: Decimal,
) -> Decimal:
    """
    工单领料上限 = BOM 配方毛需求 × (1 + 组织允许超发比例)。
    over_issue_allowance_ratio 取值 0～1，默认 0 与历史口径一致。
    """
    ratio = mrp_qty(over_issue_allowance_ratio)
    if ratio < 0:
        ratio = Decimal("0")
    if ratio > 1:
        ratio = Decimal("1")
    base = mrp_qty(allowed_bom)
    return mrp_qty(base * (Decimal("1") + ratio))


def resolve_work_order_pick_cap(
    allowed_bom: Decimal,
    over_issue_allowance_ratio: Decimal,
    material_call_extra: Decimal = Decimal("0"),
) -> Decimal:
    """
    正式发料防超发上限 = BOM×(1+超发比例) + 工单补料申请授权数量。

    补料（报废/失误等）经申请后应可领，不得仍按纯 BOM 配方拦截。
    """
    bom_cap = resolve_work_order_pick_limit(allowed_bom, over_issue_allowance_ratio)
    extra = mrp_qty(material_call_extra)
    if extra < 0:
        extra = Decimal("0")
    return mrp_qty(bom_cap + extra)


async def load_work_order_material_call_extra_map(
    tenant_id: int,
    work_order_id: int,
    material_ids: Sequence[int],
) -> Dict[int, Decimal]:
    """按物料汇总工单未取消补料申请的申请数量（正式领料额外额度）。"""
    mids = sorted({int(x) for x in material_ids if x is not None and int(x) > 0})
    if not mids or work_order_id <= 0:
        return {}

    from apps.kuaizhizao.models.material_call_request import MaterialCallRequest
    from apps.kuaizhizao.models.material_call_request_item import MaterialCallRequestItem

    call_ids = await MaterialCallRequest.filter(
        tenant_id=tenant_id,
        work_order_id=work_order_id,
        deleted_at__isnull=True,
        status__in=list(_MATERIAL_CALL_EXTRA_STATUSES),
    ).values_list("id", flat=True)
    ids = [int(x) for x in call_ids if x]
    if not ids:
        return {}

    rows = await MaterialCallRequestItem.filter(
        tenant_id=tenant_id,
        request_id__in=ids,
        material_id__in=mids,
    ).all()
    out: Dict[int, Decimal] = {}
    for row in rows:
        mid = int(getattr(row, "material_id", 0) or 0)
        if mid <= 0:
            continue
        out[mid] = out.get(mid, Decimal("0")) + mrp_qty(
            getattr(row, "requested_quantity", 0) or 0
        )
    return out


def exceeds_work_order_pick_limit(total_attempt: Decimal, allowed: Decimal) -> bool:
    """
    工单领料是否超出已解析上限（组织/物料超发比例与补料额度已计入 allowed）。

    全程 Decimal + mrp_qty；仅允许一个数量步长内的显示精度误差，禁止再叠硬编码超发比例。
    """
    total = mrp_qty(total_attempt)
    limit = mrp_qty(allowed)
    if limit <= 0:
        return total > 0
    if total <= limit:
        return False
    # 超出上限但在 1 个数量步长内：视为显示精度内相等，不拦截
    if total - limit <= MRP_QTY_STEP:
        return False
    return True


def format_pick_limit_qty(value: Decimal) -> str:
    """防超发提示数量：去尾零，最多四位小数。"""
    q = mrp_qty(value)
    text = format(q, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def picking_item_belongs_to_work_order(
    item: object,
    picking: object,
    work_order_id: int,
) -> bool:
    item_wo = getattr(item, "work_order_id", None)
    if item_wo is not None and int(item_wo or 0) > 0:
        return int(item_wo) == int(work_order_id)
    return int(getattr(picking, "work_order_id", 0) or 0) == int(work_order_id)


def max_reportable_units_from_picked(
    plan_qty: Decimal,
    pick_requirements: Sequence[Tuple[int, Decimal]],
    picked_by_material: Dict[int, Decimal],
) -> Optional[Decimal]:
    """
    按 BOM 事前领料件与已正式发料数量，计算可支撑的最大成品报工量。

    pick_requirements: (material_id, 整单计划量对应的需求数量)
    无事前领料件时返回 None（不做数量门禁）；有领料件但未领则为 0。
    """
    plan = mrp_qty(plan_qty)
    if plan <= 0:
        return Decimal("0")

    max_units: Optional[Decimal] = None
    for material_id, required_for_plan in pick_requirements:
        mid = int(material_id or 0)
        if mid <= 0:
            continue
        required = mrp_qty(required_for_plan)
        if required <= 0:
            continue
        need_per_unit = mrp_qty(required / plan)
        if need_per_unit <= 0:
            continue
        picked = mrp_qty(picked_by_material.get(mid, Decimal("0")))
        units = mrp_qty(picked / need_per_unit)
        if max_units is None or units < max_units:
            max_units = units

    return max_units


async def list_work_order_cost_pickings(tenant_id: int, work_order_id: int) -> List[object]:
    """工单已正式发料的领料单（头表或明细挂工单，排除备料转移型）。"""
    from apps.kuaizhizao.models.production_picking import ProductionPicking
    from apps.kuaizhizao.models.production_picking_item import ProductionPickingItem

    statuses = list(PRODUCTION_PICKING_COST_ELIGIBLE_STATUSES)
    by_id: dict[int, object] = {}

    header_rows = await ProductionPicking.filter(
        tenant_id=tenant_id,
        work_order_id=work_order_id,
        status__in=statuses,
        deleted_at__isnull=True,
    ).all()
    for row in header_rows:
        by_id[int(row.id)] = row

    item_picking_ids = await ProductionPickingItem.filter(
        tenant_id=tenant_id,
        work_order_id=work_order_id,
        deleted_at__isnull=True,
    ).values_list("picking_id", flat=True)
    extra_ids = sorted({int(pid) for pid in item_picking_ids if pid})
    if extra_ids:
        extra_rows = await ProductionPicking.filter(
            tenant_id=tenant_id,
            id__in=extra_ids,
            status__in=statuses,
            deleted_at__isnull=True,
        ).all()
        for row in extra_rows:
            by_id[int(row.id)] = row

    if not by_id:
        return []
    gi_ids = set(filter_gi_picking_ids(list(by_id.values())))
    return [p for p in by_id.values() if int(getattr(p, "id")) in gi_ids]


async def sum_confirmed_picked_by_material(
    tenant_id: int, work_order_id: int
) -> Dict[int, Decimal]:
    """工单正式发料明细已领数量，按物料汇总。"""
    pickings = await list_work_order_cost_pickings(tenant_id, work_order_id)
    if not pickings:
        return {}
    from apps.kuaizhizao.models.production_picking_item import ProductionPickingItem

    by_id = {int(p.id): p for p in pickings}
    items = await ProductionPickingItem.filter(
        tenant_id=tenant_id,
        picking_id__in=list(by_id.keys()),
        deleted_at__isnull=True,
    ).all()
    out: Dict[int, Decimal] = {}
    for item in items:
        picking = by_id.get(int(getattr(item, "picking_id", 0) or 0))
        if picking is None:
            continue
        if not picking_item_belongs_to_work_order(item, picking, work_order_id):
            continue
        mid = int(getattr(item, "material_id", 0) or 0)
        if mid <= 0:
            continue
        out[mid] = out.get(mid, Decimal("0")) + mrp_qty(
            getattr(item, "picked_quantity", 0) or 0
        )
    return out
