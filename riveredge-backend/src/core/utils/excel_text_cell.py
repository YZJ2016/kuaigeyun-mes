"""
Excel 身份列文本写出（openpyxl）。

编码 / 名称 / 电话等列必须走本工具，禁止 cell.value = raw 让 Excel 推断成数字或公式。
契约见 aoci memory: principles/document-import-export-ssot.md
"""

from __future__ import annotations

from typing import Any


def excel_text_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def write_excel_text_cell(cell: Any, value: Any) -> None:
    """写入文本单元格：显式字符串 + 文本格式 @。"""
    cell.value = excel_text_value(value)
    cell.number_format = "@"
