"""单据推送：主数据编码解析（单位等），与具体业务单据解耦。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence

from loguru import logger

# 默认计量单位：金蝶 FNumber（常见账套「个」= 006）
DEFAULT_UNIT_NUMBER = "006"
# 仅目录/接口映射都未命中时的展示名兜底；目录已同步的编码（含字面量 kg）不得再经此改写
BUILTIN_UNIT_ALIASES: Dict[str, str] = {
    "个": "006",
    "pcs": "006",
    "Pcs": "006",
    "PCS": "006",
}

# Save 接口 source_type_conversion_map 中视为「单位」的 field_name（大小写不敏感）
UNIT_CONVERSION_FIELD_NAMES = frozenset(
    {
        "unit",
        "unit_number",
        "funitid",
        "funitid.fnumber",
        "fbaseunitid",
        "fbaseunitid.fnumber",
    }
)


def extract_unit_code_map_from_conversion(conversion: Any) -> Dict[str, str]:
    """从 API.source_type_conversion_map 提取单位编码映射（纯函数）。

    认 field_name：unit / unit_number / FUnitId / FUnitId.FNumber /
    FBaseUnitId / FBaseUnitId.FNumber（大小写不敏感）。多条匹配时后写覆盖先写。
    """
    out: Dict[str, str] = {}
    if isinstance(conversion, dict) and conversion:
        # 扁平旧格式无 field_name，无法判定为单位，忽略
        return out
    if not isinstance(conversion, list):
        return out
    for entry in conversion:
        if not isinstance(entry, dict):
            continue
        field = str(entry.get("field_name") or "").strip().lower()
        if field not in UNIT_CONVERSION_FIELD_NAMES:
            continue
        mapping = entry.get("mapping")
        if not isinstance(mapping, dict):
            continue
        for raw_key, raw_val in mapping.items():
            key = str(raw_key).strip()
            val = str(raw_val or "").strip()
            if key and val:
                out[key] = val
    return out


async def load_save_api_unit_code_map(
    tenant_id: int, save_api_uuid: Optional[str]
) -> Dict[str, str]:
    """按 Save 接口 uuid 加载单位转换表；无接口或无映射时返回空 dict。"""
    api_uuid = str(save_api_uuid or "").strip()
    if not api_uuid:
        return {}
    try:
        from core.models.api import API

        api_obj = await API.filter(tenant_id=tenant_id, uuid=api_uuid).first()
        if not api_obj:
            return {}
        return extract_unit_code_map_from_conversion(
            getattr(api_obj, "source_type_conversion_map", None)
        )
    except Exception as exc:
        logger.warning(
            "load save api unit code map failed tenant_id={} api={} err={}",
            tenant_id,
            api_uuid,
            exc,
        )
        return {}


def _map_lookup(raw: str, mapping: Dict[str, Any]) -> Optional[str]:
    if raw in mapping:
        val = str(mapping.get(raw) or "").strip()
        return val or None
    lowered = {str(k).strip().lower(): v for k, v in mapping.items() if str(k).strip()}
    hit = lowered.get(raw.lower())
    if hit is None:
        return None
    val = str(hit or "").strip()
    return val or None


def apply_unit_code_map(
    unit: str,
    unit_code_map: Optional[Dict[str, Any]] = None,
    *,
    use_builtin_aliases: bool = False,
) -> str:
    """接口单位 map（可选内置别名）→ 目标系统单位编码。不再读取 BusinessConfig。"""
    raw = str(unit or "").strip()
    if not raw:
        return ""
    if isinstance(unit_code_map, dict) and unit_code_map:
        api_hit = _map_lookup(raw, unit_code_map)
        if api_hit:
            return api_hit
    if use_builtin_aliases:
        builtin_hit = _map_lookup(raw, BUILTIN_UNIT_ALIASES)
        if builtin_hit:
            return builtin_hit
    return raw


async def lookup_unit_catalog_code(tenant_id: int, unit_ref: str) -> Optional[str]:
    """单位编码或名称 → 目录 code；未命中返回 None（不回落原串）。"""
    raw = str(unit_ref or "").strip()
    if not raw:
        return None
    try:
        from apps.master_data.models.unit import MaterialUnit

        unit = await MaterialUnit.filter(
            tenant_id=tenant_id, code=raw, deleted_at__isnull=True
        ).first()
        if unit:
            return str(unit.code).strip() or None
        unit = await MaterialUnit.filter(
            tenant_id=tenant_id, name=raw, deleted_at__isnull=True
        ).first()
        if unit:
            return str(unit.code).strip() or None
    except Exception as exc:
        logger.warning("lookup unit catalog code failed ref={} err={}", raw, exc)
    return None


async def resolve_unit_catalog_code(tenant_id: int, unit_ref: str) -> Optional[str]:
    """单位编码或名称 → 单位目录 code；未命中时回落原串（兼容旧调用）。"""
    raw = str(unit_ref or "").strip()
    if not raw:
        return None
    hit = await lookup_unit_catalog_code(tenant_id, raw)
    return hit if hit else raw


async def resolve_material_base_unit(tenant_id: int, product_code: Optional[str]) -> Optional[str]:
    """物料基本单位 → 目录 code。"""
    code = str(product_code or "").strip()
    if not code:
        return None
    try:
        from apps.master_data.services.sync_association_service import find_material_by_code

        material = await find_material_by_code(tenant_id, code)
        if not material:
            return None
        base = str(getattr(material, "base_unit", None) or "").strip()
        if not base:
            return None
        hit = await lookup_unit_catalog_code(tenant_id, base)
        return hit or base
    except Exception as exc:
        logger.warning("resolve material unit failed code={} err={}", code, exc)
    return None


def _iter_unit_refs(*refs: Any) -> Iterable[str]:
    seen: set[str] = set()
    for ref in refs:
        text = str(ref or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        yield text


async def resolve_push_unit_number(
    tenant_id: int,
    *,
    unit_refs: Sequence[Any],
    unit_code_map: Optional[Dict[str, Any]] = None,
    allow_builtin_aliases: bool = False,
) -> str:
    """按优先级解析推送单位编码。

    真相链：
    1. MaterialUnit 目录（code / name）命中 → 用目录 code，**禁止**再套 BUILTIN
    2. Save 接口 source_type_conversion_map
    3. （仅显式开启时）BUILTIN_UNIT_ALIASES（不含 kg→004）
    4. 原串透传
    5. DEFAULT_UNIT_NUMBER
    """
    refs = list(_iter_unit_refs(*unit_refs))
    for ref in refs:
        hit = await lookup_unit_catalog_code(tenant_id, ref)
        if hit:
            return hit
    for ref in refs:
        mapped = apply_unit_code_map(
            ref,
            unit_code_map,
            use_builtin_aliases=allow_builtin_aliases,
        )
        if mapped:
            return mapped
    return DEFAULT_UNIT_NUMBER


async def resolve_unit_for_push(
    tenant_id: int,
    *,
    product_code: Optional[str] = None,
    unit_hint: Optional[str] = None,
    base_unit_hint: Optional[str] = None,
    unit_code_map: Optional[Dict[str, Any]] = None,
    allow_builtin_aliases: bool = False,
) -> Dict[str, str]:
    """解析推送用单位编码。

    真相链（禁止读 BusinessConfig 单位键）：
    业务单据 unit_hint / 物料主数据 MaterialUnit.code
    → Save 接口 source_type_conversion_map 单位条目
    →（显式开启时）BUILTIN_UNIT_ALIASES
    → DEFAULT_UNIT_NUMBER

    默认透传目录/行单位（如 ``kg``）；禁止隐式别名改写。
    """
    hint = str(unit_hint or "").strip()
    if not hint:
        hint = await resolve_material_base_unit(tenant_id, product_code) or ""
    unit = await resolve_push_unit_number(
        tenant_id,
        unit_refs=[hint],
        unit_code_map=unit_code_map,
        allow_builtin_aliases=allow_builtin_aliases,
    )

    base_raw = str(base_unit_hint or "").strip()
    if not base_raw:
        base = unit
    else:
        base = await resolve_push_unit_number(
            tenant_id,
            unit_refs=[base_raw],
            unit_code_map=unit_code_map,
            allow_builtin_aliases=allow_builtin_aliases,
        )

    return {"unit_number": unit, "base_unit_number": base}
