"""入站同步：表头 + 明细数组（entry / FEntity 等）摊成扁平行。

勿把 data / items / rows 当作明细键——那些是响应外壳，由 normalize_api_body_to_rows 解包。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

# 业务单据明细数组名（苍穹 BOM/订单常见 entry；星空常见 FEntity）
NESTED_DETAIL_KEYS: Sequence[str] = (
    "entry",
    "billentry",
    "BillEntry",
    "FEntity",
    "fentity",
    "TreeEntity",
    "treeEntity",
)


def _is_plain_object(value: Any) -> bool:
    return isinstance(value, dict) and not isinstance(value, type(None))


def _flatten_fields(
    obj: Mapping[str, Any],
    *,
    prefix: str = "",
    glue_first: bool = True,
) -> Dict[str, Any]:
    """嵌套对象摊平：entry + material.number → entrymaterial_number。

    明细项字段若已以明细键开头（如 entrymaterial），不再叠加前缀，
    避免苍穹 BOM 出现 entryentrymaterial_number。
    """
    out: Dict[str, Any] = {}
    for raw_key, value in obj.items():
        key = str(raw_key)
        if not key:
            continue
        if prefix:
            if glue_first and key.lower().startswith(prefix.lower()):
                full = key
            elif glue_first:
                full = f"{prefix}{key}"
            else:
                full = f"{prefix}_{key}"
        else:
            full = key
        if _is_plain_object(value):
            out.update(_flatten_fields(value, prefix=full, glue_first=False))
            continue
        if isinstance(value, list):
            # 明细内再嵌套数组不摊；避免把整段 JSON 塞进映射列
            continue
        out[full] = value
    return out


def _find_detail_key(row: Mapping[str, Any]) -> Optional[str]:
    for key in NESTED_DETAIL_KEYS:
        if key in row and isinstance(row.get(key), list):
            return key
    # 大小写不敏感兜底
    lower_map = {str(k).lower(): k for k in row.keys()}
    for key in NESTED_DETAIL_KEYS:
        found = lower_map.get(key.lower())
        if found is not None and isinstance(row.get(found), list):
            return str(found)
    return None


def expand_nested_detail_row(row: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """单行：有明细则一行明细一行输出；空明细数组保留表头行。"""
    if not isinstance(row, Mapping):
        return []
    detail_key = _find_detail_key(row)
    if detail_key is None:
        return [_flatten_fields(row)]

    details = row.get(detail_key)
    header = {k: v for k, v in row.items() if k != detail_key}
    flat_header = _flatten_fields(header)

    if not isinstance(details, list) or not details:
        return [flat_header]

    expanded: List[Dict[str, Any]] = []
    for item in details:
        if not _is_plain_object(item):
            continue
        flat_detail = _flatten_fields(item, prefix=str(detail_key), glue_first=True)
        merged: Dict[str, Any] = {**flat_header, **flat_detail}
        expanded.append(merged)
    return expanded or [flat_header]


def expand_nested_detail_rows(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    """对行列表做明细摊平（幂等：已扁平行原样再摊一层无害）。"""
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        out.extend(expand_nested_detail_row(row))
    return out


def collect_row_column_keys(rows: Sequence[Mapping[str, Any]]) -> List[str]:
    """预览列：取全部行键的并集（保序）。"""
    seen: Dict[str, None] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for key in row.keys():
            text = str(key)
            if text and text not in seen:
                seen[text] = None
    return list(seen.keys())


__all__ = [
    "NESTED_DETAIL_KEYS",
    "expand_nested_detail_row",
    "expand_nested_detail_rows",
    "collect_row_column_keys",
]
