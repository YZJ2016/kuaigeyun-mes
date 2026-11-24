"""红框凭证类打印模板：schema 修补与版本标记。"""

from __future__ import annotations

from typing import Any

from apps.kuaizhizao.print.purchase_receipt_red_voucher_template import (
    PURCHASE_RECEIPT_RED_VOUCHER_LAYOUT_VERSION,
    apply_purchase_receipt_red_voucher_v4,
)

PURCHASE_RECEIPT_RED_VOUCHER_PRESET_VERSION = PURCHASE_RECEIPT_RED_VOUCHER_LAYOUT_VERSION
KUAIZHIZAO_RED_VOUCHER_TITLE_BASES = ("采购入库单", "其他出库单", "生产领料单")

KUAIZHIZAO_RED_VOUCHER_PRINT_CODES = frozenset(
    {
        "PURCHASE_RECEIPT_PRINT_002",
        "OTHER_OUTBOUND_PRINT_002",
        "PRODUCTION_PICKING_PRINT_002",
    }
)

LOCATION_COLUMN_KEYS = frozenset({"location_code", "location_name"})

PURCHASE_RECEIPT_RED_VOUCHER_LOCATION_COLUMN: dict[str, str] = {
    "key": "location_name",
    "label": "库位",
    "type": "text",
}


def _detail_table_has_location(columns: list[Any]) -> bool:
    for col in columns:
        if not isinstance(col, dict):
            continue
        key = str(col.get("key") or "").strip()
        if key in LOCATION_COLUMN_KEYS:
            return True
    return False


def _insert_location_column(columns: list[Any]) -> list[Any]:
    out = list(columns)
    insert_at = len(out)
    for i, col in enumerate(out):
        if not isinstance(col, dict):
            continue
        key = str(col.get("key") or "").strip()
        label = str(col.get("label") or "").strip()
        if key == "total_amount" or label == "金额":
            insert_at = i + 1
            break
        if key == "warehouse_name" or label in ("收货仓库", "收料仓库"):
            insert_at = i + 1
    out.insert(insert_at, dict(PURCHASE_RECEIPT_RED_VOUCHER_LOCATION_COLUMN))
    return out


_HTML_QTY_CELL = '<td class="num">{{ item.receipt_quantity or "" }}</td>'
_HTML_QTY_CELL_2 = (
    '<td class="num">{% if item.receipt_quantity not in [None, ""] %}'
    '{{ "%.2f"|format(item.receipt_quantity|float) }}{% endif %}</td>'
)
_HTML_TOTAL_QTY = '<td class="num">{{ total_quantity or "" }}</td>'
_HTML_TOTAL_QTY_2 = (
    '<td class="num">{% if total_quantity not in [None, ""] %}'
    '{{ "%.2f"|format(total_quantity|float) }}{% endif %}</td>'
)


_RED_VOUCHER_KINGDEE_BILL_SNIPPET = (
    '    <div><span class="label">金蝶单号：</span>'
    '<span class="value">{{ kingdee_bill_no or "—" }}</span></div>\n'
)


_PRINT_KINGDEE_TABLE_MARKERS = (
    '  </div>\n  <table class="grid">',
    '  </div>\r\n  <table class="grid">',
)


def patch_print_kingdee_bill_no_html(html: str) -> tuple[str, bool]:
    """整页 HTML 打印在明细表前补金蝶单号。已有则不动。"""
    text = str(html or "")
    if "kingdee_bill_no" in text or "金蝶单号" in text:
        return text, False
    if 'class="lab"' in text:
        snippet = (
            '    <div><span class="lab">金蝶单号：</span>'
            '<span class="val">{{ kingdee_bill_no or "" }}</span></div>\n'
        )
    else:
        snippet = (
            '    <div><span class="label">金蝶单号：</span>'
            '<span class="value">{{ kingdee_bill_no or "" }}</span></div>\n'
        )
    for marker in _PRINT_KINGDEE_TABLE_MARKERS:
        if marker in text:
            return text.replace(marker, snippet + marker, 1), True
    return text, False


def patch_kuaizhizao_red_voucher_kingdee_bill_no_html(html: str) -> tuple[str, bool]:
    """红框凭证表头补金蝶单号（幂等）。"""
    text = str(html or "")
    if "金蝶单号" in text:
        return text, False
    if not any(title in text for title in KUAIZHIZAO_RED_VOUCHER_TITLE_BASES):
        return text, False
    for marker in (
        '  </div>\n  <table class="grid">',
        '  </div>\r\n  <table class="grid">',
    ):
        if marker in text:
            return text.replace(marker, _RED_VOUCHER_KINGDEE_BILL_SNIPPET + marker, 1), True
    return text, False


def _apply_literal_replacements(text: str, pairs: list[tuple[str, str]]) -> tuple[str, bool]:
    out = text
    changed = False
    for old, new in pairs:
        if old in out:
            out = out.replace(old, new)
            changed = True
    return out, changed


def patch_purchase_receipt_red_voucher_html(html: str) -> tuple[str, bool]:
    """整块 HTML 红框采购入库单：对齐纸质样例（表头四字段与明细列序）。"""
    text = str(html or "")
    if not text or "采购入库单" not in text:
        return text, False

    v4, v4_changed = apply_purchase_receipt_red_voucher_v4(text)
    if v4_changed:
        return v4, True

    changed = False
    out = text
    if "收货仓库" not in text:
        return text, False

    header_pairs = [
        (
            "<th>收货仓库</th>\n        <th>库位</th>\n        <th>金额</th>",
            "<th>收货仓库</th>\n        <th>金额</th>\n        <th>库位</th>",
        ),
        (
            "<th>收货仓库</th>\r\n        <th>库位</th>\r\n        <th>金额</th>",
            "<th>收货仓库</th>\r\n        <th>金额</th>\r\n        <th>库位</th>",
        ),
    ]
    out, head_changed = _apply_literal_replacements(out, header_pairs)
    changed = changed or head_changed

    v2_row = (
        '<td>{{ item.warehouse_name or warehouse_name or "" }}</td>\n'
        '        <td>{{ item.location_name or item.location_code or "" }}</td>\n'
        '        <td class="num">{{ item.total_amount or "" }}</td>'
    )
    v3_row = (
        '<td>{{ item.warehouse_name or warehouse_name or "" }}</td>\n'
        '        <td class="num">{{ item.total_amount or "" }}</td>\n'
        '        <td>{{ item.location_name or item.location_code or "" }}</td>'
    )
    if v2_row in out:
        out = out.replace(v2_row, v3_row)
        changed = True

    # 表头含库位但明细未绑定 location：金额落在库位列
    missing_location_rows = [
        (
            '<td>{{ item.warehouse_name or warehouse_name or "" }}</td>\n'
            '        <td class="num">{{ item.total_amount or "" }}</td>\n'
            '        <td>{{ item.notes or "" }}</td>',
            '<td>{{ item.warehouse_name or warehouse_name or "" }}</td>\n'
            '        <td class="num">{{ item.total_amount or "" }}</td>\n'
            '        <td>{{ item.location_name or item.location_code or "" }}</td>\n'
            '        <td>{{ item.notes or "" }}</td>',
        ),
        (
            '<td>{{ item.warehouse_name or warehouse_name or "" }}</td>\r\n'
            '        <td class="num">{{ item.total_amount or "" }}</td>\r\n'
            '        <td>{{ item.notes or "" }}</td>',
            '<td>{{ item.warehouse_name or warehouse_name or "" }}</td>\r\n'
            '        <td class="num">{{ item.total_amount or "" }}</td>\r\n'
            '        <td>{{ item.location_name or item.location_code or "" }}</td>\r\n'
            '        <td>{{ item.notes or "" }}</td>',
        ),
    ]
    if "item.location_name" not in out and "<th>库位</th>" in out:
        out, row_changed = _apply_literal_replacements(out, missing_location_rows)
        if row_changed:
            changed = True
            out, head_changed2 = _apply_literal_replacements(out, header_pairs)
            changed = changed or head_changed2

    if "<th>库位</th>" not in out:
        for amount_notes in (
            "        <th>金额</th>\n        <th>备注</th>",
            "        <th>金额</th>\r\n        <th>备注</th>",
        ):
            if amount_notes in out:
                out = out.replace(
                    amount_notes,
                    "        <th>金额</th>\n        <th>库位</th>\n        <th>备注</th>",
                    1,
                )
                changed = True
                break

        row_amount_notes = (
            '<td class="num">{{ item.total_amount or "" }}</td>\n'
            '        <td>{{ item.notes or "" }}</td>'
        )
        row_v3 = (
            '<td class="num">{{ item.total_amount or "" }}</td>\n'
            '        <td>{{ item.location_name or item.location_code or "" }}</td>\n'
            '        <td>{{ item.notes or "" }}</td>'
        )
        if row_amount_notes in out:
            out = out.replace(row_amount_notes, row_v3)
            changed = True

        col_old = '<col style="width:8%" />\r\n      <col style="width:12%" />'
        col_new = '<col style="width:8%" />\r\n      <col style="width:10%" />\r\n      <col style="width:12%" />'
        if col_old in out:
            out = out.replace(col_old, col_new, 1)
            changed = True
        else:
            col_old_lf = '<col style="width:8%" />\n      <col style="width:12%" />'
            col_new_lf = '<col style="width:8%" />\n      <col style="width:10%" />\n      <col style="width:12%" />'
            if col_old_lf in out:
                out = out.replace(col_old_lf, col_new_lf, 1)
                changed = True

        blank_old = (
            "<td>&nbsp;</td><td></td><td></td><td></td><td></td>"
            "<td></td><td></td><td></td><td></td>"
        )
        blank_new = blank_old + "<td></td>"
        if blank_old in out and blank_new not in out:
            out = out.replace(blank_old, blank_new)
            changed = True

    total_v2_extra = (
        '<td class="num">{{ total_quantity or "" }}</td>\n'
        "        <td></td>\n"
        "        <td></td>\n"
        "        <td></td>\n"
        '        <td class="num">{{ total_amount'
    )
    total_v3 = (
        '<td class="num">{{ total_quantity or "" }}</td>\n'
        "        <td></td>\n"
        "        <td></td>\n"
        '        <td class="num">{{ total_amount'
    )
    if total_v2_extra in out:
        out = out.replace(total_v2_extra, total_v3, 1)
        changed = True

    if _HTML_QTY_CELL in out:
        out = out.replace(_HTML_QTY_CELL, _HTML_QTY_CELL_2)
        changed = True
    if _HTML_TOTAL_QTY in out:
        out = out.replace(_HTML_TOTAL_QTY, _HTML_TOTAL_QTY_2)
        changed = True

    return out, changed


def patch_purchase_receipt_red_voucher_schema(schema: dict[str, Any]) -> bool:
    """detail_table 或整块 HTML 文本块：在「收货仓库」后插入库位；已存在则不改。"""
    blocks = schema.get("blocks")
    if not isinstance(blocks, list):
        return False
    changed = False
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        if blk.get("type") == "detail_table":
            collection = str(blk.get("collection") or "items").strip()
            if collection != "items":
                continue
            columns = blk.get("columns")
            if not isinstance(columns, list) or _detail_table_has_location(columns):
                continue
            blk["columns"] = _insert_location_column(columns)
            changed = True
        elif blk.get("type") == "text":
            content = blk.get("content")
            if not isinstance(content, str):
                continue
            patched, html_changed = patch_purchase_receipt_red_voucher_html(content)
            if html_changed:
                blk["content"] = patched
                changed = True
    if changed:
        schema["preset_version"] = PURCHASE_RECEIPT_RED_VOUCHER_PRESET_VERSION
    return changed


def is_kuaizhizao_red_voucher_print_template(
    *,
    name: str | None,
    code: str | None,
    config: dict[str, Any] | None,
) -> bool:
    """三份红框凭证（不含送货单）。"""
    if "红框" not in str(name or ""):
        return False
    if "送货" in str(name or ""):
        return False
    if not isinstance(config, dict):
        return False
    doc = str(config.get("document_type") or "").strip()
    if doc in ("purchase_receipt", "other_outbound", "production_picking"):
        return True
    code_u = str(code or "").strip().upper()
    return code_u in KUAIZHIZAO_RED_VOUCHER_PRINT_CODES


def is_purchase_receipt_red_voucher_template(
    *,
    name: str | None,
    code: str | None,
    config: dict[str, Any] | None,
) -> bool:
    if not isinstance(config, dict):
        return False
    if str(config.get("document_type") or "").strip() != "purchase_receipt":
        return False
    if "红框" in str(name or ""):
        return True
    code_u = str(code or "").strip().upper()
    if "RED" in code_u and "RECEIPT" in code_u:
        return True
    schema = config.get("designer_schema")
    if isinstance(schema, dict) and str(schema.get("preset_kind") or "") == "purchase_receipt_red_voucher":
        return True
    if isinstance(schema, dict):
        for blk in schema.get("blocks") or []:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "detail_table":
                for col in blk.get("columns") or []:
                    if not isinstance(col, dict):
                        continue
                    if str(col.get("label") or "") in ("收货仓库", "收料仓库"):
                        return True
            if blk.get("type") == "text":
                content = blk.get("content")
                if isinstance(content, str) and "采购入库单" in content and "收货仓库" in content:
                    return True
    return False


def recompile_designer_schema(schema: dict[str, Any]) -> str:
    from core.schemas.print_template import PrintTemplateCompileRequest
    from core.services.print.print_template_service import PrintTemplateService

    result = PrintTemplateService.compile_designer_schema(
        PrintTemplateCompileRequest(source_type="designer_json", source=schema)
    )
    return str(result.get("compiled_template") or "")
