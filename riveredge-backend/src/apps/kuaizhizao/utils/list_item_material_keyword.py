"""列表 keyword 扩展：按明细行物料编码/名称/规格/型号反查表头 ID。"""

from __future__ import annotations

from typing import Any, List, Sequence, Type

from tortoise.expressions import Q
from tortoise.models import Model


def _item_line_material_q(kw: str, *, include_spec: bool = True, include_model: bool = True) -> Q:
    filters: Any = Q(material_code__icontains=kw) | Q(material_name__icontains=kw)
    if include_spec:
        filters |= Q(material_spec__icontains=kw)
    if include_model:
        filters |= Q(material_model__icontains=kw)
    return filters


def _item_model_supports_material_model(item_model: Type[Model]) -> bool:
    return "material_model" in item_model._meta.fields_map


async def header_ids_matching_item_material(
    tenant_id: int,
    item_model: Type[Model],
    header_fk_field: str,
    keyword: str,
    *,
    include_spec: bool = True,
    include_model: bool = True,
) -> List[int]:
    """按物料 keyword 在明细表反查表头 ID 列表（去重）。"""
    kw = (keyword or "").strip()
    if not kw:
        return []
    use_model = include_model and _item_model_supports_material_model(item_model)
    filters = _item_line_material_q(kw, include_spec=include_spec, include_model=use_model)
    ids = (
        await item_model.filter(tenant_id=tenant_id)
        .filter(filters)
        .distinct()
        .values_list(header_fk_field, flat=True)
    )
    return [int(x) for x in ids if x is not None]


def build_header_keyword_or_clause(keyword_fields: Sequence[str], kw: str) -> Q:
    header_cond = Q()
    for field in keyword_fields:
        header_cond |= Q(**{f"{field}__icontains": kw})
    return header_cond


async def apply_query_header_or_line_material_keyword(
    query,
    *,
    tenant_id: int,
    kw: str,
    keyword_fields: Sequence[str],
    item_model: Type[Model],
    item_header_fk_field: str,
    header_pk_field: str = "id",
    include_spec: bool = True,
    include_model: bool = True,
):
    """表头 keyword_fields 与明细行物料 keyword 合并为 OR 过滤。"""
    keyword = (kw or "").strip()
    if not keyword:
        return query
    material_header_ids = await header_ids_matching_item_material(
        tenant_id,
        item_model,
        item_header_fk_field,
        keyword,
        include_spec=include_spec,
        include_model=include_model,
    )
    header_cond = build_header_keyword_or_clause(keyword_fields, keyword)
    return query.filter(header_cond | Q(**{f"{header_pk_field}__in": material_header_ids}))
