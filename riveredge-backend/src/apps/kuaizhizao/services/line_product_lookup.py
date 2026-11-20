"""产线可生产自制件查找（软依赖 ind_relay；未装包时返回空）。

硬门禁约定：
- 产线有节拍行但不在 allow_map / 绑定为空 → 不可承接任何工单
- 工单 product_id 必须落在该线绑定集合内
"""

from __future__ import annotations

from typing import Dict, Optional, Set


async def load_line_allowed_product_ids(tenant_id: int) -> Dict[int, Set[int]]:
    """production_line_id -> 允许的自制件物料 ID 集合。"""
    try:
        from apps.ind_relay.models.line_product import RelayLineProduct
    except ImportError:
        return {}
    rows = await RelayLineProduct.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    ).all()
    out: Dict[int, Set[int]] = {}
    for row in rows:
        line_id = int(row.production_line_id or 0)
        product_id = int(row.product_id or 0)
        if line_id <= 0 or product_id <= 0:
            continue
        out.setdefault(line_id, set()).add(product_id)
    return out


def line_accepts_product(
    line_id: int,
    product_id: int,
    allow_map: Dict[int, Set[int]],
) -> bool:
    lid = int(line_id or 0)
    pid = int(product_id or 0)
    if lid <= 0 or pid <= 0:
        return False
    allowed = allow_map.get(lid)
    if not allowed:
        return False
    return pid in allowed


def eligible_line_ids_for_product(
    product_id: int,
    *,
    configured_line_ids: Optional[Set[int]] = None,
    allow_map: Dict[int, Set[int]],
) -> Set[int]:
    """已配节拍（可选）∩ 绑定含本产品。"""
    pid = int(product_id or 0)
    if pid <= 0:
        return set()
    hit = {lid for lid, products in allow_map.items() if pid in products}
    if configured_line_ids is not None:
        hit &= {int(x) for x in configured_line_ids if int(x or 0) > 0}
    return hit
