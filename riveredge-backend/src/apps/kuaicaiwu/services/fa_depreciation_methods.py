"""固定资产折旧方法码表（前后端导入/展示对齐）。"""

from __future__ import annotations

from typing import Dict

DEPRECIATION_METHOD_LABELS: Dict[str, str] = {
    "straight_line": "年限平均法",
    "double_declining": "双倍余额递减法",
    "sum_of_years": "年数总和法",
    "units_of_production": "工作量法",
    "none": "不折旧",
}

DEPRECIATION_LABEL_TO_CODE: Dict[str, str] = {
    "年限平均法": "straight_line",
    "直线法": "straight_line",
    "straight_line": "straight_line",
    "双倍余额递减法": "double_declining",
    "double_declining": "double_declining",
    "年数总和法": "sum_of_years",
    "sum_of_years": "sum_of_years",
    "工作量法": "units_of_production",
    "units_of_production": "units_of_production",
    "不折旧": "none",
    "none": "none",
}


def normalize_depreciation_method(raw: str | None, *, default: str = "straight_line") -> str:
    text = str(raw or "").strip()
    if not text:
        return default
    return DEPRECIATION_LABEL_TO_CODE.get(text, text)


def depreciation_method_label(code: str | None) -> str:
    normalized = normalize_depreciation_method(code, default="")
    return DEPRECIATION_METHOD_LABELS.get(normalized, str(code or ""))


def is_valid_depreciation_method(code: str | None) -> bool:
    normalized = normalize_depreciation_method(code, default="")
    return normalized in DEPRECIATION_METHOD_LABELS
