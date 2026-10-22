"""仿真物料包（Kit）硬预检：真实模式缺 BOM/工艺/标准工时即 blocking。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from apps.kuaizhizao.services.flow_sim.modes import SimMode


@dataclass
class KitPrecheckResult:
    ok: bool
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    kit: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "blocking": list(self.blocking),
            "warnings": list(self.warnings),
            "kit": dict(self.kit),
        }


def _ops_from_sequence(seq: Any) -> list[dict[str, Any]]:
    if seq is None:
        return []
    if isinstance(seq, dict):
        raw = seq.get("operations") or seq.get("items") or []
    elif isinstance(seq, list):
        raw = seq
    else:
        raw = getattr(seq, "operations", None) or []
    out: list[dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, dict):
            out.append(item)
        else:
            out.append(
                {
                    "standard_time": getattr(item, "standard_time", None),
                    "code": getattr(item, "code", None),
                    "name": getattr(item, "name", None),
                }
            )
    return out


async def precheck_simulation_kit(
    tenant_id: int,
    *,
    material_ids: list[int],
    mode: SimMode,
    warehouse_id: Optional[int] = None,
) -> KitPrecheckResult:
    """对成品物料检查 BOM / 工艺 / 标准工时。"""
    from apps.master_data.models.material import Material
    from apps.master_data.services.material_product_process_service import (
        MaterialProductProcessService,
    )
    from apps.master_data.services.material_service import MaterialService

    result = KitPrecheckResult(ok=True)
    ids = sorted({int(x) for x in material_ids if int(x or 0) > 0})
    if not ids:
        msg = "未指定仿真物料：请选择销售订单/预测行或 selected_material_ids"
        if mode == "real":
            result.ok = False
            result.blocking.append(msg)
        else:
            result.warnings.append(msg)
        return result

    materials = await Material.filter(
        tenant_id=tenant_id, id__in=ids, deleted_at__isnull=True
    ).all()
    found = {int(m.id): m for m in materials}
    missing = [i for i in ids if i not in found]
    if missing:
        msg = f"物料不存在或已删除：{missing}"
        if mode == "real":
            result.ok = False
            result.blocking.append(msg)
        else:
            result.warnings.append(msg)

    bom_map = await MaterialService.batch_check_has_bom(tenant_id, ids)
    kit_rows: list[dict[str, Any]] = []

    for mid in ids:
        mat = found.get(mid)
        if mat is None:
            continue
        code = str(
            getattr(mat, "main_code", None) or getattr(mat, "code", None) or mid
        )
        name = str(getattr(mat, "name", None) or "")
        has_bom = bool(bom_map.get(mid) or bom_map.get(str(mid)))
        has_process = False
        has_std = False
        op_count = 0
        try:
            seq, _ = await MaterialProductProcessService.resolve_sequence_for_material(
                tenant_id, mid
            )
            ops = _ops_from_sequence(seq)
            op_count = len(ops)
            has_process = op_count > 0
            for op in ops:
                try:
                    st = float(Decimal(str(op.get("standard_time") or 0)))
                except Exception:
                    st = 0.0
                if st > 0:
                    has_std = True
                    break
        except Exception as exc:
            result.warnings.append(f"{code} 工艺解析失败: {exc}")

        row = {
            "material_id": mid,
            "material_code": code,
            "material_name": name,
            "has_bom": has_bom,
            "has_process": has_process,
            "has_std_time": has_std,
            "operation_count": op_count,
        }
        if not has_bom:
            msg = f"物料 {code} 缺少 BOM"
            if mode == "real":
                result.ok = False
                result.blocking.append(msg)
            else:
                result.warnings.append(msg)
        if not has_process:
            msg = f"物料 {code} 缺少工艺工序"
            if mode == "real":
                result.ok = False
                result.blocking.append(msg)
            else:
                result.warnings.append(msg)
        elif not has_std:
            msg = f"物料 {code} 工艺工序均未配置标准工时"
            if mode == "real":
                result.ok = False
                result.blocking.append(msg)
            else:
                result.warnings.append(msg + "（填数模式将用步骤间隔）")
        kit_rows.append(row)

    if warehouse_id:
        result.kit["warehouse_id"] = int(warehouse_id)
    result.kit["materials"] = kit_rows
    result.kit["mode"] = mode
    if mode == "real":
        result.warnings.append(
            "真实模式：已关闭强制简易质检与默认跳过 IQC；Kit 缺项禁止开跑。"
        )
    return result
