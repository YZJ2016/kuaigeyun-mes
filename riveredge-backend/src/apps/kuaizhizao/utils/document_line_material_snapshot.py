"""
单据行物料快照：伙伴料号/品名 + 型号（写路径真源）。

Author: Agent
Date: 2026-10-21
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from apps.master_data.models.material import Material
from apps.master_data.models.material_code_alias import MaterialCodeAlias
@dataclass(frozen=True)
class LineMaterialSnapshot:
    partner_material_code: Optional[str]
    partner_material_name: Optional[str]
    material_model: Optional[str]
    material_spec: Optional[str]


def _strip_or_none(value: Any, max_len: int) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len]


def snapshot_from_material(material: Optional[Material]) -> LineMaterialSnapshot:
    if not material:
        return LineMaterialSnapshot(None, None, None, None)
    return LineMaterialSnapshot(
        partner_material_code=None,
        partner_material_name=None,
        material_model=_strip_or_none(getattr(material, "model", None), 200),
        material_spec=_strip_or_none(getattr(material, "specification", None), 200),
    )


def snapshot_from_alias_and_material(
    alias: Optional[MaterialCodeAlias],
    material: Optional[Material],
) -> LineMaterialSnapshot:
    base = snapshot_from_material(material)
    if not alias:
        return base
    return LineMaterialSnapshot(
        partner_material_code=_strip_or_none(alias.code, 100),
        partner_material_name=_strip_or_none(alias.name, 200),
        material_model=base.material_model,
        material_spec=base.material_spec,
    )


async def resolve_line_material_snapshots(
    tenant_id: int,
    *,
    partner_type: Optional[str],
    partner_id: Optional[int],
    material_ids: Iterable[int],
) -> Dict[int, LineMaterialSnapshot]:
    """批量解析物料行快照（伙伴映射 + 型号/规格补全）。"""
    ids = sorted({int(mid) for mid in material_ids if mid})
    if not ids:
        return {}

    materials = await Material.filter(tenant_id=tenant_id, id__in=ids, deleted_at__isnull=True).all()
    material_by_id = {m.id: m for m in materials}

    alias_by_material: Dict[int, MaterialCodeAlias] = {}
    pid = int(partner_id or 0)
    ptype = (partner_type or "").strip().lower()
    if pid > 0 and ptype in ("customer", "supplier"):
        code_type = "CUSTOMER" if ptype == "customer" else "SUPPLIER"
        aliases = await MaterialCodeAlias.filter(
            tenant_id=tenant_id,
            material_id__in=ids,
            code_type=code_type,
            external_entity_type=ptype,
            external_entity_id=pid,
            deleted_at__isnull=True,
        ).all()
        alias_by_material = {a.material_id: a for a in aliases}

    out: Dict[int, LineMaterialSnapshot] = {}
    for mid in ids:
        out[mid] = snapshot_from_alias_and_material(
            alias_by_material.get(mid),
            material_by_id.get(mid),
        )
    return out


def apply_snapshot_to_line_dict(
    line: Dict[str, Any],
    snapshot: LineMaterialSnapshot,
    *,
    fill_spec_if_empty: bool = True,
) -> Dict[str, Any]:
    """将快照写入行 dict（create/update/push 共用）。"""
    line["partner_material_code"] = snapshot.partner_material_code
    line["partner_material_name"] = snapshot.partner_material_name
    line["material_model"] = snapshot.material_model
    if fill_spec_if_empty and snapshot.material_spec:
        existing = str(line.get("material_spec") or "").strip()
        if not existing:
            line["material_spec"] = snapshot.material_spec
    return line


async def enrich_line_dicts_with_partner_snapshots(
    tenant_id: int,
    *,
    partner_type: Optional[str],
    partner_id: Optional[int],
    lines: Sequence[Mapping[str, Any]],
    material_id_key: str = "material_id",
) -> List[Dict[str, Any]]:
    """对多行明细批量补伙伴料号/品名/型号快照。"""
    material_ids = [
        int(line.get(material_id_key) or 0)
        for line in lines
        if int(line.get(material_id_key) or 0) > 0
    ]
    snaps = await resolve_line_material_snapshots(
        tenant_id,
        partner_type=partner_type,
        partner_id=partner_id,
        material_ids=material_ids,
    )
    enriched: List[Dict[str, Any]] = []
    for raw in lines:
        row = dict(raw)
        mid = int(row.get(material_id_key) or 0)
        if mid > 0 and mid in snaps:
            apply_snapshot_to_line_dict(row, snaps[mid])
        enriched.append(row)
    return enriched


def snapshot_kwargs_for_orm(row: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    return {
        "partner_material_code": _strip_or_none(row.get("partner_material_code"), 100),
        "partner_material_name": _strip_or_none(row.get("partner_material_name"), 200),
        "material_model": _strip_or_none(row.get("material_model"), 200),
    }


def partner_snapshot_fields_from_source_line(source: Any) -> Dict[str, Optional[str]]:
    """下推/复制：优先沿用源行快照。"""
    return {
        "partner_material_code": _strip_or_none(getattr(source, "partner_material_code", None), 100),
        "partner_material_name": _strip_or_none(getattr(source, "partner_material_name", None), 200),
        "material_model": _strip_or_none(getattr(source, "material_model", None), 200),
    }


async def resolve_customer_id_for_finished_goods_receipt(
    tenant_id: int,
    *,
    sales_order_id: Optional[int],
) -> Optional[int]:
    """成品入库：经销售订单解析客户 ID。"""
    so_id = int(sales_order_id or 0)
    if so_id <= 0:
        return None
    from apps.kuaizhizao.models.sales_order import SalesOrder

    order = await SalesOrder.get_or_none(
        tenant_id=tenant_id, id=so_id, deleted_at__isnull=True
    )
    if not order:
        return None
    cid = int(getattr(order, "customer_id", None) or 0)
    return cid if cid > 0 else None


async def resolve_line_partner_material_snapshots(
    tenant_id: int,
    *,
    partner_type: str,
    partner_id: int,
    material_ids: Iterable[int],
) -> Dict[int, Dict[str, Optional[str]]]:
    """批量伙伴料号/品名 + 型号（供 MaterialCodeService 委托）。"""
    snaps = await resolve_line_material_snapshots(
        tenant_id,
        partner_type=partner_type,
        partner_id=partner_id,
        material_ids=material_ids,
    )
    return {
        mid: {
            "partner_material_code": s.partner_material_code,
            "partner_material_name": s.partner_material_name,
            "material_model": s.material_model,
        }
        for mid, s in snaps.items()
    }
