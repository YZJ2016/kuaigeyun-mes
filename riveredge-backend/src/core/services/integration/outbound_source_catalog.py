"""出站推送：本地数据表 / 实体目录（接口管理可选系统全部注册表）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.config.associated_table_registry import _get_model
from core.config.custom_field_system_fields import get_associated_table_model_fields


def _list_associated_table_names() -> List[str]:
    """custom_field_pages 注册表名列表（本地 associated_table_registry 结构等价物）。"""
    from core.config.custom_field_pages import CUSTOM_FIELD_PAGES

    return [
        str(p.get("table_name") or "").strip()
        for p in CUSTOM_FIELD_PAGES or []
        if isinstance(p, dict) and str(p.get("table_name") or "").strip()
    ]

# 表头 → 明细（选表头时自动带明细字段）
_HEADER_TO_ENTRY: Dict[str, str] = {
    "apps_kuaizhizao_purchase_receipts": "apps_kuaizhizao_purchase_receipt_items",
}

# 复合单据（优先展示）
_OUTBOUND_PROFILES: List[Dict[str, Any]] = [
    {
        "code": "purchase_receipt",
        "name": "采购入库单（表头+明细）",
        "match_paths": ["im_purinbill", "purinbill"],
        "tables": [
            {
                "table": "apps_kuaizhizao_purchase_receipts",
                "label": "采购入库单（表头）",
                "level": "header",
                "extra_fields": [
                    {"field": "supplier_number", "label": "供应商编码（解析后）"},
                    {"field": "org_number", "label": "库存组织编码（单据/接口默认）"},
                    {"field": "bizorg_number", "label": "采购组织编码（单据/接口默认）"},
                    {"field": "billtype_number", "label": "单据类型编码（单据/接口默认）"},
                    {"field": "biztype_number", "label": "业务类型编码（单据/接口默认）"},
                    {"field": "invscheme_number", "label": "库存事务编码（单据/接口默认）"},
                    {"field": "biztime", "label": "业务日期（取入库时间）"},
                    {"field": "comment", "label": "备注（推送文案）"},
                ],
            },
            {
                "table": "apps_kuaizhizao_purchase_receipt_items",
                "label": "采购入库明细",
                "level": "entry",
                "extra_fields": [
                    {"field": "qty", "label": "数量（同入库数量）"},
                    {"field": "unit_number", "label": "单位编码（解析后）"},
                    {"field": "warehouse_number", "label": "仓库编码（解析后）"},
                    {"field": "lotnumber", "label": "批号（同批次号）"},
                    {"field": "org_number", "label": "组织编码（用于货主/保管者等）"},
                ],
            },
        ],
    },
]


def _table_label_map() -> Dict[str, str]:
    """custom_field_pages 中文表名 + 模型类名兜底。"""
    labels: Dict[str, str] = {}
    try:
        from core.config.custom_field_pages import CUSTOM_FIELD_PAGES

        for page in CUSTOM_FIELD_PAGES or []:
            if not isinstance(page, dict):
                continue
            table = str(page.get("table_name") or "").strip()
            label = str(page.get("table_name_label") or page.get("page_name") or "").strip()
            if table and label:
                labels[table] = label
    except Exception:
        pass
    return labels


def _merge_table_fields(table_name: str, extra_fields: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    items = list(get_associated_table_model_fields(table_name) or [])
    seen = {str(i.get("field") or "") for i in items}
    for extra in extra_fields or []:
        field = str(extra.get("field") or "").strip()
        if not field or field in seen:
            continue
        seen.add(field)
        items.append({"field": field, "label": str(extra.get("label") or field).strip() or field})
    items.sort(key=lambda x: str(x.get("field") or ""))
    return items


def _build_table_item(
    *,
    profile_code: str,
    profile_name: str,
    table_name: str,
    label: str,
    level: str,
    extra_fields: Optional[List[Dict[str, str]]] = None,
) -> Optional[Dict[str, Any]]:
    if not table_name:
        return None
    if _get_model(table_name) is None and not extra_fields:
        return None
    return {
        "profile_code": profile_code,
        "profile_name": profile_name,
        "table": table_name,
        "label": label,
        "level": level,
        "fields": _merge_table_fields(table_name, extra_fields),
    }


def _profile_tables(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in profile.get("tables") or []:
        item = _build_table_item(
            profile_code=str(profile.get("code") or ""),
            profile_name=str(profile.get("name") or ""),
            table_name=str(t.get("table") or "").strip(),
            label=str(t.get("label") or t.get("table") or ""),
            level=str(t.get("level") or "header"),
            extra_fields=t.get("extra_fields"),
        )
        if item:
            out.append(item)
    return out


def _entity_tables_for_single(table_name: str, label: str) -> List[Dict[str, Any]]:
    """单表实体：表头用本表；若有配对明细表则一并返回。"""
    out: List[Dict[str, Any]] = []
    header = _build_table_item(
        profile_code=table_name,
        profile_name=label,
        table_name=table_name,
        label=label,
        level="header",
    )
    if header:
        out.append(header)
    entry_name = _HEADER_TO_ENTRY.get(table_name)
    if entry_name and _get_model(entry_name) is not None:
        labels = _table_label_map()
        entry = _build_table_item(
            profile_code=table_name,
            profile_name=label,
            table_name=entry_name,
            label=labels.get(entry_name) or entry_name,
            level="entry",
        )
        if entry:
            out.append(entry)
    elif header:
        # 无明细配对时，明细层级也可用同一表字段（方便固定值行）
        out.append(
            {
                **header,
                "level": "entry",
                "label": f"{label}（同表字段）",
            }
        )
    return out


def list_outbound_source_catalog(path: Optional[str] = None) -> Dict[str, Any]:
    """
    接口管理出站映射目录：
    - profiles：可选「本地单据/实体」（含复合单据 + 系统全部注册表）
    - tables：当前推荐表字段（按 path 匹配的复合单据优先；同时附带全部表字段供前端按 profile 过滤）
    """
    labels = _table_label_map()
    path_l = str(path or "").lower().replace("\\", "/")

    profiles: List[Dict[str, Any]] = []
    tables: List[Dict[str, Any]] = []
    seen_profile: set[str] = set()

    # 1) 复合单据置顶
    for profile in _OUTBOUND_PROFILES:
        code = str(profile.get("code") or "").strip()
        if not code or code in seen_profile:
            continue
        seen_profile.add(code)
        profiles.append(
            {
                "code": code,
                "name": str(profile.get("name") or code),
                "match_paths": list(profile.get("match_paths") or []),
            }
        )
        for item in _profile_tables(profile):
            tables.append(item)

    # 2) 系统全部注册表/实体
    for table_name in _list_associated_table_names():
        if table_name in seen_profile:
            continue
        # 明细表通常挂在表头下，不单独作为顶层「单据」；仍可单独选
        label = labels.get(table_name) or table_name
        # 避免与复合单据重复：采购入库表头已在 purchase_receipt 中
        if table_name == "apps_kuaizhizao_purchase_receipts":
            # 仍提供单表选项，名称区分
            label = f"{label}（仅表头）"
        profiles.append(
            {
                "code": table_name,
                "name": label,
                "match_paths": [],
            }
        )
        seen_profile.add(table_name)
        for item in _entity_tables_for_single(table_name, label):
            tables.append(item)

    # path 匹配时，把推荐 profile 的 match 信息保留；前端默认选中
    recommended: Optional[str] = None
    for profile in _OUTBOUND_PROFILES:
        for token in profile.get("match_paths") or []:
            if token and token in path_l:
                recommended = str(profile.get("code") or "")
                break
        if recommended:
            break

    return {
        "profiles": profiles,
        "tables": tables,
        "recommended_profile": recommended,
    }
