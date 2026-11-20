"""
物料编码搜索模式（租户业务配置 master_data.material_code_search_mode）

- fuzzy：编码/名称/规格包含匹配（现状）
- prefix：关键词仅对物料编码（main_code、code、编号别名 code）从头匹配
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Sequence, Tuple

from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from apps.master_data.models.material_code_alias import MaterialCodeAlias

MaterialCodeSearchMode = Literal["fuzzy", "prefix"]

_MATERIAL_CODE_SEARCH_MODES = frozenset({"fuzzy", "prefix"})


def coerce_material_code_search_mode(
    raw: Any,
    *,
    default: MaterialCodeSearchMode = "fuzzy",
) -> MaterialCodeSearchMode:
    text = str(raw or "").strip().lower()
    if text in _MATERIAL_CODE_SEARCH_MODES:
        return text  # type: ignore[return-value]
    return default


def material_row_matches_keyword(row: Any, keyword: str, mode: MaterialCodeSearchMode) -> bool:
    kw = (keyword or "").strip()
    if not kw:
        return True
    kw_lower = kw.lower()
    if mode == "prefix":
        for val in (getattr(row, "main_code", None), getattr(row, "code", None)):
            if val and str(val).lower().startswith(kw_lower):
                return True
        return False

    for val in (
        getattr(row, "main_code", None),
        getattr(row, "name", None),
        getattr(row, "specification", None),
        getattr(row, "code", None),
    ):
        if val and kw_lower in str(val).lower():
            return True
    attrs = getattr(row, "variant_attributes", None)
    if attrs:
        try:
            import json

            attrs_text = json.dumps(attrs, ensure_ascii=False).lower()
            if kw_lower in attrs_text:
                return True
        except (TypeError, ValueError):
            pass
    return False


def build_material_main_keyword_q(keyword: str, mode: MaterialCodeSearchMode) -> Q:
    text = (keyword or "").strip()
    if mode == "prefix":
        return Q(main_code__istartswith=text) | Q(code__istartswith=text)
    return (
        Q(main_code__icontains=text)
        | Q(name__icontains=text)
        | Q(specification__icontains=text)
        | Q(code__icontains=text)
    )


async def material_ids_from_code_alias_keyword(
    tenant_id: int,
    keyword: str,
    mode: MaterialCodeSearchMode,
) -> list[int]:
    text = (keyword or "").strip()
    if not text:
        return []
    alias_q = MaterialCodeAlias.filter(tenant_id=tenant_id, deleted_at__isnull=True)
    if mode == "prefix":
        alias_q = alias_q.filter(code__istartswith=text)
    else:
        alias_q = alias_q.filter(code__icontains=text)
    raw_ids = await alias_q.values_list("material_id", flat=True)
    ids = sorted({int(i) for i in raw_ids if i is not None and int(i) > 0})
    return ids


async def apply_material_keyword_filter(
    query: QuerySet,
    *,
    tenant_id: int,
    keyword: Optional[str],
    mode: MaterialCodeSearchMode,
) -> QuerySet:
    text = (keyword or "").strip()
    if not text:
        return query
    main_q = build_material_main_keyword_q(text, mode)
    alias_ids = await material_ids_from_code_alias_keyword(tenant_id, text, mode)
    if alias_ids:
        return query.filter(main_q | Q(id__in=alias_ids))
    return query.filter(main_q)


async def page_materials_by_keyword(
    queryset: QuerySet,
    *,
    tenant_id: int,
    keyword: Optional[str],
    mode: MaterialCodeSearchMode,
    page: int = 1,
    page_size: int = 20,
    order_by: Sequence[str] = (),
) -> Tuple[list, int]:
    from core.utils.search_utils import page_queryset_by_keyword

    text = (keyword or "").strip()
    if mode == "fuzzy":
        return await page_queryset_by_keyword(
            queryset,
            keyword=text or None,
            fields=("code", "main_code", "name", "specification", "model"),
            page=page,
            page_size=page_size,
            order_by=order_by,
        )

    if not text:
        ordered = queryset.order_by(*order_by) if order_by else queryset
        total = await ordered.count()
        start = max(page - 1, 0) * page_size
        rows = await ordered.offset(start).limit(page_size).all()
        return list(rows), total

    filtered = await apply_material_keyword_filter(
        queryset,
        tenant_id=tenant_id,
        keyword=text,
        mode=mode,
    )
    ordered = filtered.order_by(*order_by) if order_by else filtered
    total = await ordered.count()
    start = max(page - 1, 0) * page_size
    rows = await ordered.offset(start).limit(page_size).all()
    return list(rows), total