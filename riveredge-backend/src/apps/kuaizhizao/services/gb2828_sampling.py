"""
GB/T 2828.1-2012 一次正常/加严/放宽抽样（字码表 + Ac/Re）

仅服务端查表；前端只存 level/aql/strictness/transfer_enabled。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from infra.exceptions.exceptions import ValidationError

GB2828_MODES = ("gb2828_single",)

INSPECTION_LEVELS = ("S-1", "S-2", "S-3", "S-4", "I", "II", "III")
STRICTNESS_VALUES = ("normal", "tightened", "reduced")
COMMON_AQL_VALUES = (0.65, 1.0, 1.5, 2.5, 4.0, 6.5, 10.0)

SAMPLE_SIZE_BY_LETTER: Dict[str, int] = {
    "A": 2,
    "B": 3,
    "C": 5,
    "D": 8,
    "E": 13,
    "F": 20,
    "G": 32,
    "H": 50,
    "J": 80,
    "K": 125,
    "L": 200,
    "M": 315,
    "N": 500,
    "P": 800,
    "Q": 1250,
    "R": 2000,
}

# 表 1 批量区间 → 字码（GB/T 2828.1-2012）
_LOT_BANDS: List[Tuple[int, int, Dict[str, str]]] = [
    (1, 1, {"S-1": "A", "S-2": "A", "S-3": "A", "S-4": "A", "I": "A", "II": "A", "III": "A"}),
    (2, 8, {"S-1": "A", "S-2": "A", "S-3": "A", "S-4": "A", "I": "A", "II": "A", "III": "A"}),
    (9, 15, {"S-1": "A", "S-2": "A", "S-3": "A", "S-4": "A", "I": "A", "II": "B", "III": "B"}),
    (16, 25, {"S-1": "A", "S-2": "A", "S-3": "B", "S-4": "B", "I": "B", "II": "C", "III": "C"}),
    (26, 50, {"S-1": "B", "S-2": "B", "S-3": "B", "S-4": "C", "I": "C", "II": "D", "III": "D"}),
    (51, 90, {"S-1": "B", "S-2": "C", "S-3": "C", "S-4": "C", "I": "C", "II": "E", "III": "E"}),
    (91, 150, {"S-1": "B", "S-2": "C", "S-3": "D", "S-4": "D", "I": "D", "II": "F", "III": "G"}),
    (151, 280, {"S-1": "C", "S-2": "D", "S-3": "E", "S-4": "E", "I": "E", "II": "G", "III": "H"}),
    (281, 500, {"S-1": "C", "S-2": "D", "S-3": "E", "S-4": "F", "I": "F", "II": "H", "III": "J"}),
    (501, 1200, {"S-1": "D", "S-2": "E", "S-3": "F", "S-4": "G", "I": "G", "II": "J", "III": "K"}),
    (1201, 3200, {"S-1": "E", "S-2": "F", "S-3": "G", "S-4": "H", "I": "H", "II": "K", "III": "L"}),
    (3201, 10000, {"S-1": "E", "S-2": "G", "S-3": "H", "S-4": "J", "I": "J", "II": "L", "III": "M"}),
    (10001, 35000, {"S-1": "F", "S-2": "G", "S-3": "J", "S-4": "K", "I": "K", "II": "M", "III": "N"}),
    (35001, 150000, {"S-1": "G", "S-2": "H", "S-3": "K", "S-4": "L", "I": "L", "II": "N", "III": "P"}),
    (150001, 500000, {"S-1": "G", "S-2": "J", "S-3": "L", "S-4": "M", "I": "M", "II": "P", "III": "Q"}),
    (500001, 10_000_000_000, {"S-1": "H", "S-2": "J", "S-3": "M", "S-4": "N", "I": "N", "II": "Q", "III": "R"}),
]

# 表 10 一次抽样 Ac/Re：strictness → aql_key → letter → (Ac, Re)
_AC_RE_TABLE: Dict[str, Dict[str, Dict[str, Tuple[int, int]]]] = {
    "normal": {
        "1.0": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (0, 1), "F": (1, 2),
            "G": (1, 2), "H": (2, 3), "J": (3, 4), "K": (5, 6), "L": (7, 8), "M": (10, 11),
            "N": (14, 15), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "2.5": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (1, 2), "F": (1, 2),
            "G": (2, 3), "H": (3, 4), "J": (5, 6), "K": (7, 8), "L": (10, 11), "M": (14, 15),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "4.0": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (1, 2), "E": (2, 3), "F": (3, 4),
            "G": (5, 6), "H": (7, 8), "J": (10, 11), "K": (14, 15), "L": (21, 22), "M": (21, 22),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "6.5": {
            "A": (0, 1), "B": (0, 1), "C": (1, 2), "D": (2, 3), "E": (3, 4), "F": (5, 6),
            "G": (7, 8), "H": (10, 11), "J": (14, 15), "K": (21, 22), "L": (21, 22), "M": (21, 22),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "10.0": {
            "A": (0, 1), "B": (1, 2), "C": (2, 3), "D": (3, 4), "E": (5, 6), "F": (7, 8),
            "G": (10, 11), "H": (14, 15), "J": (21, 22), "K": (21, 22), "L": (21, 22), "M": (21, 22),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "0.65": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (0, 1), "F": (0, 1),
            "G": (1, 2), "H": (1, 2), "J": (2, 3), "K": (3, 4), "L": (5, 6), "M": (7, 8),
            "N": (10, 11), "P": (14, 15), "Q": (21, 22), "R": (21, 22),
        },
        "1.5": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (1, 2), "F": (1, 2),
            "G": (2, 3), "H": (3, 4), "J": (5, 6), "K": (7, 8), "L": (10, 11), "M": (14, 15),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
    },
    "tightened": {
        "2.5": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (0, 1), "F": (1, 2),
            "G": (1, 2), "H": (2, 3), "J": (3, 4), "K": (5, 6), "L": (7, 8), "M": (10, 11),
            "N": (14, 15), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "1.0": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (0, 1), "F": (0, 1),
            "G": (1, 2), "H": (1, 2), "J": (2, 3), "K": (3, 4), "L": (5, 6), "M": (7, 8),
            "N": (10, 11), "P": (14, 15), "Q": (21, 22), "R": (21, 22),
        },
        "4.0": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (1, 2), "E": (1, 2), "F": (2, 3),
            "G": (3, 4), "H": (5, 6), "J": (7, 8), "K": (10, 11), "L": (14, 15), "M": (21, 22),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "6.5": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (1, 2), "E": (2, 3), "F": (3, 4),
            "G": (5, 6), "H": (7, 8), "J": (10, 11), "K": (14, 15), "L": (21, 22), "M": (21, 22),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "10.0": {
            "A": (0, 1), "B": (0, 1), "C": (1, 2), "D": (2, 3), "E": (3, 4), "F": (5, 6),
            "G": (7, 8), "H": (10, 11), "J": (14, 15), "K": (21, 22), "L": (21, 22), "M": (21, 22),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "0.65": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (0, 1), "F": (0, 1),
            "G": (0, 1), "H": (1, 2), "J": (1, 2), "K": (2, 3), "L": (3, 4), "M": (5, 6),
            "N": (7, 8), "P": (10, 11), "Q": (14, 15), "R": (21, 22),
        },
        "1.5": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (0, 1), "F": (1, 2),
            "G": (1, 2), "H": (2, 3), "J": (3, 4), "K": (5, 6), "L": (7, 8), "M": (10, 11),
            "N": (14, 15), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
    },
    "reduced": {
        "2.5": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (1, 2), "F": (1, 2),
            "G": (2, 3), "H": (3, 4), "J": (5, 6), "K": (7, 8), "L": (10, 11), "M": (14, 15),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "1.0": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (1, 2), "F": (1, 2),
            "G": (2, 3), "H": (3, 4), "J": (5, 6), "K": (7, 8), "L": (10, 11), "M": (14, 15),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "4.0": {
            "A": (0, 1), "B": (0, 1), "C": (1, 2), "D": (2, 3), "E": (3, 4), "F": (5, 6),
            "G": (7, 8), "H": (10, 11), "J": (14, 15), "K": (21, 22), "L": (21, 22), "M": (21, 22),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "6.5": {
            "A": (0, 1), "B": (0, 1), "C": (1, 2), "D": (2, 3), "E": (3, 4), "F": (5, 6),
            "G": (7, 8), "H": (10, 11), "J": (14, 15), "K": (21, 22), "L": (21, 22), "M": (21, 22),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "10.0": {
            "A": (0, 1), "B": (1, 2), "C": (2, 3), "D": (3, 4), "E": (5, 6), "F": (7, 8),
            "G": (10, 11), "H": (14, 15), "J": (21, 22), "K": (21, 22), "L": (21, 22), "M": (21, 22),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "0.65": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (0, 1), "F": (1, 2),
            "G": (1, 2), "H": (2, 3), "J": (3, 4), "K": (5, 6), "L": (7, 8), "M": (10, 11),
            "N": (14, 15), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
        "1.5": {
            "A": (0, 1), "B": (0, 1), "C": (0, 1), "D": (0, 1), "E": (1, 2), "F": (1, 2),
            "G": (2, 3), "H": (3, 4), "J": (5, 6), "K": (7, 8), "L": (10, 11), "M": (14, 15),
            "N": (21, 22), "P": (21, 22), "Q": (21, 22), "R": (21, 22),
        },
    },
}


_AQL_KEY_BY_VALUE = {float(v): str(v) if v != 10.0 else "10.0" for v in COMMON_AQL_VALUES}
_AQL_KEY_BY_VALUE[10.0] = "10.0"
_AQL_KEY_BY_VALUE[1.0] = "1.0"
_AQL_KEY_BY_VALUE[0.65] = "0.65"


def _normalize_aql_key(raw: Any) -> str:
    try:
        val = float(raw)
    except (TypeError, ValueError):
        raise ValidationError("国标抽检 AQL 无效")
    for candidate, key in _AQL_KEY_BY_VALUE.items():
        if math.isclose(val, candidate, rel_tol=0, abs_tol=1e-9):
            return key
    raise ValidationError(
        f"不支持的 AQL 值: {val:g}（常用：{', '.join(str(x) for x in COMMON_AQL_VALUES)}）"
    )


def _normalize_level(raw: Any) -> str:
    level = str(raw or "II").strip().upper()
    if level in ("S1", "S-1"):
        return "S-1"
    if level in ("S2", "S-2"):
        return "S-2"
    if level in ("S3", "S-3"):
        return "S-3"
    if level in ("S4", "S-4"):
        return "S-4"
    if level in INSPECTION_LEVELS:
        return level if level.startswith("S") else level
    raise ValidationError(f"无效的检验水平: {raw}")


def _normalize_strictness(raw: Any) -> str:
    s = str(raw or "normal").strip().lower()
    if s in STRICTNESS_VALUES:
        return s
    if s in ("加严", "tight"):
        return "tightened"
    if s in ("放宽", "reduce"):
        return "reduced"
    if s in ("正常",):
        return "normal"
    raise ValidationError(f"无效的严格度: {raw}")


def lot_size_to_code_letter(lot_size: int, level: str) -> str:
    if lot_size < 1:
        raise ValidationError("批量须大于 0")
    lvl = _normalize_level(level)
    for lo, hi, mapping in _LOT_BANDS:
        if lo <= lot_size <= hi:
            letter = mapping.get(lvl)
            if not letter:
                raise ValidationError(f"检验水平 {lvl} 无对应字码")
            return letter
    raise ValidationError("批量超出字码表范围")


def resolve_single_sampling_plan(
    *,
    lot_size: int,
    level: str,
    aql: Any,
    strictness: str,
) -> Dict[str, Any]:
    letter = lot_size_to_code_letter(lot_size, level)
    n = SAMPLE_SIZE_BY_LETTER[letter]
    aql_key = _normalize_aql_key(aql)
    strict = _normalize_strictness(strictness)
    table = _AC_RE_TABLE.get(strict, {}).get(aql_key)
    if not table:
        raise ValidationError(f"严格度 {strict} 下无 AQL {aql_key} 抽样表")
    ac_re = table.get(letter)
    if not ac_re:
        raise ValidationError(f"字码 {letter} 在 AQL {aql_key}（{strict}）下无 Ac/Re")
    ac, re = ac_re
    return {
        "code_letter": letter,
        "sample_size": n,
        "accept_num": ac,
        "reject_num": re,
        "level": _normalize_level(level),
        "aql": float(aql_key) if aql_key != "10.0" else 10.0,
        "strictness": strict,
    }


def normalize_gb2828_sampling_fields(raw: Any) -> Dict[str, Any]:
    base = {
        "level": "II",
        "aql": 2.5,
        "strictness": "normal",
        "transfer_enabled": False,
    }
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    if raw.get("level") is not None:
        out["level"] = _normalize_level(raw.get("level"))
    if raw.get("aql") is not None:
        out["aql"] = float(_normalize_aql_key(raw.get("aql")))
    if raw.get("strictness") is not None:
        out["strictness"] = _normalize_strictness(raw.get("strictness"))
    if raw.get("transfer_enabled") is not None:
        out["transfer_enabled"] = bool(raw.get("transfer_enabled"))
    return out


def format_gb2828_sampling_label(resolved: Dict[str, Any], lot_size: Optional[int] = None) -> str:
    lot_part = f"，批量 {lot_size}" if lot_size and lot_size > 0 else ""
    return (
        f"GB/T 2828.1 一次抽样{lot_part}，水平 {resolved.get('level')}，"
        f"{resolved.get('strictness')}，AQL {resolved.get('aql')}，"
        f"字码 {resolved.get('code_letter')}，n={resolved.get('sample_size')}，"
        f"Ac={resolved.get('accept_num')}，Re={resolved.get('reject_num')}"
    )
