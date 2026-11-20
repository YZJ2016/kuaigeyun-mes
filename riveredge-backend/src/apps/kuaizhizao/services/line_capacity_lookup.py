"""产线节拍/日产能查找（软依赖 ind_relay；未装包时返回空）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class LineCapacityInfo:
    production_line_id: int
    takt_seconds: float
    daily_capacity_qty: float
    changeover_minutes_default: float = 0.0


async def load_line_capacity_map(tenant_id: int) -> Dict[int, LineCapacityInfo]:
    try:
        from apps.ind_relay.models.line_capacity import RelayLineCapacity
    except ImportError:
        # 未安装/未挂载 ind_relay 时才空 map；其它异常必须上抛，禁止伪装成「未配节拍」
        return {}
    rows = await RelayLineCapacity.filter(
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        is_active=True,
    ).all()
    out: Dict[int, LineCapacityInfo] = {}
    for row in rows:
        line_id = int(row.production_line_id or 0)
        if line_id <= 0:
            continue
        out[line_id] = LineCapacityInfo(
            production_line_id=line_id,
            takt_seconds=float(row.takt_seconds or 0),
            daily_capacity_qty=float(row.daily_capacity_qty or 0),
            changeover_minutes_default=float(row.changeover_minutes_default or 0),
        )
    return out


def duration_hours_from_takt(quantity: float, takt_seconds: float) -> Optional[float]:
    if quantity <= 0 or takt_seconds <= 0:
        return None
    return max(quantity * takt_seconds / 3600.0, 1.0 / 60.0)
