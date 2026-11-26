from apps.kuaizhizao.print.purchase_receipt_red_voucher_template import (
    PURCHASE_RECEIPT_RED_VOUCHER_HTML,
    PURCHASE_RECEIPT_RED_VOUCHER_LAYOUT_VERSION,
    apply_purchase_receipt_red_voucher_v4,
)
from apps.kuaizhizao.print.red_voucher_presets import (
    PURCHASE_RECEIPT_RED_VOUCHER_PRESET_VERSION,
    patch_kuaizhizao_red_voucher_kingdee_bill_no_html,
    patch_print_kingdee_bill_no_html,
    patch_purchase_receipt_red_voucher_html,
    patch_purchase_receipt_red_voucher_schema,
)
from apps.kuaizhizao.services.print_template_presets import (
    patch_kingdee_bill_no_print_schema,
)


def test_patch_inserts_location_after_warehouse_column():
    schema = {
        "blocks": [
            {
                "type": "detail_table",
                "collection": "items",
                "columns": [
                    {"key": "material_code", "label": "物料编码"},
                    {"key": "warehouse_name", "label": "收货仓库"},
                    {"key": "total_amount", "label": "金额"},
                ],
            }
        ]
    }
    assert patch_purchase_receipt_red_voucher_schema(schema) is True
    cols = schema["blocks"][0]["columns"]
    assert cols[3]["key"] == "location_name"
    assert cols[3]["label"] == "库位"
    assert schema["preset_version"] == PURCHASE_RECEIPT_RED_VOUCHER_PRESET_VERSION


def test_patch_idempotent_when_location_exists():
    schema = {
        "blocks": [
            {
                "type": "detail_table",
                "collection": "items",
                "columns": [
                    {"key": "warehouse_name", "label": "收货仓库"},
                    {"key": "location_code", "label": "库位"},
                ],
            }
        ]
    }
    assert patch_purchase_receipt_red_voucher_schema(schema) is False


def test_patch_monolithic_html_inserts_location_after_amount():
    snippet = (
        '<h1 class="title">采购入库单</h1>'
        "<th>收货仓库</th><th>金额</th><th>备注</th>"
        '<td>{{ item.warehouse_name or warehouse_name or "" }}</td>'
        '<td class="num">{{ item.total_amount or "" }}</td>'
        '<td>{{ item.notes or "" }}</td>'
    )
    patched, changed = patch_purchase_receipt_red_voucher_html(snippet)
    assert changed is True
    assert patched.index("金额") < patched.index("仓位") < patched.index("备注")
    assert "location_name" in patched


def test_v9_html_upgrades_to_po_column():
    v9_html = PURCHASE_RECEIPT_RED_VOUCHER_HTML.replace(
        "purchase_receipt_red_voucher_v10",
        "purchase_receipt_red_voucher_v9",
    ).replace("<th>采购订单</th>\n      </tr>", "</tr>").replace(
        '<td class="wrap-tight">{{ purchase_order_code or "" }}</td>\n      </tr>',
        "      </tr>",
    )
    patched, changed = apply_purchase_receipt_red_voucher_v4(v9_html)
    assert changed is True
    assert "<th>采购订单</th>" in patched
    assert "purchase_order_code" in patched
    assert "purchase_receipt_red_voucher_v10" in patched


def test_patch_swaps_v2_location_before_amount():
    v2 = (
        "采购入库单<th>收货仓库</th>\n        <th>库位</th>\n        <th>金额</th>"
        '<td>{{ item.warehouse_name or warehouse_name or "" }}</td>\n'
        '        <td>{{ item.location_name or item.location_code or "" }}</td>\n'
        '        <td class="num">{{ item.total_amount or "" }}</td>'
        '<td class="num">{{ item.receipt_quantity or "" }}</td>'
    )
    patched, changed = patch_purchase_receipt_red_voucher_html(v2)
    assert changed is True
    assert patched.index("金额") < patched.index("仓位")
    assert '%.2f"|format(item.receipt_quantity|float)' in patched


def test_patch_text_block_in_schema():
    schema = {
        "blocks": [
            {
                "type": "text",
                "content": (
                    "采购入库单<th>收货仓库</th><th>金额</th>"
                    '{{ item.warehouse_name or warehouse_name or "" }}'
                    '{{ item.total_amount or "" }}'
                ),
            }
        ]
    }
    assert patch_purchase_receipt_red_voucher_schema(schema) is True
    assert "仓位" in schema["blocks"][0]["content"]


def test_patch_applies_sample_layout_v4():
    legacy = (
        "采购入库单<h1></h1>"
        '<div><span class="label">单据类型：</span></div>'
        "<th>收货仓库</th><th>库位</th><th>金额</th>"
    )
    patched, changed = patch_purchase_receipt_red_voucher_html(legacy)
    assert changed is True
    assert "采购方式：" in patched
    assert patched.index("编号：") < patched.index("供应商：")
    assert "<th>金额</th>" in patched and "<th>仓位</th>" in patched
    assert patched.index("<th>金额</th>") < patched.index("<th>收料仓库</th>")
    assert patched.index("item.total_amount") < patched.index("item.location_name")


def test_v10_marker_without_po_column_still_needs_upgrade():
    v10_stub = (
        PURCHASE_RECEIPT_RED_VOUCHER_HTML.replace("<th>采购订单</th>\n      </tr>", "</tr>")
        .replace(
            '<td class="wrap-tight">{{ purchase_order_code or "" }}</td>\n      </tr>',
            "      </tr>",
        )
    )
    assert "purchase_receipt_red_voucher_v10" in v10_stub
    assert "<th>采购订单</th>" not in v10_stub
    patched, changed = apply_purchase_receipt_red_voucher_v4(v10_stub)
    assert changed is True
    assert "<th>采购订单</th>" in patched


def test_canonical_red_voucher_has_no_blank_fill_rows():
    assert "blank_n" not in PURCHASE_RECEIPT_RED_VOUCHER_HTML
    assert PURCHASE_RECEIPT_RED_VOUCHER_LAYOUT_VERSION.endswith("_v10")
    assert "金蝶单号" in PURCHASE_RECEIPT_RED_VOUCHER_HTML
    assert "kingdee_bill_no" in PURCHASE_RECEIPT_RED_VOUCHER_HTML


def test_patch_kingdee_bill_no_meta_idempotent():
    snippet = (
        "<h1 class=\"title\">生产领料单</h1>"
        '  <div class="meta">\n'
        "    <div>编号</div>\n"
        '  </div>\n'
        '  <table class="grid">'
    )
    patched, changed = patch_kuaizhizao_red_voucher_kingdee_bill_no_html(snippet)
    assert changed is True
    assert "金蝶单号" in patched
    assert patch_kuaizhizao_red_voucher_kingdee_bill_no_html(patched)[1] is False


def test_v5_blank_rows_upgrade_preserves_tenant_title():
    v5 = (
        PURCHASE_RECEIPT_RED_VOUCHER_HTML.replace(
            PURCHASE_RECEIPT_RED_VOUCHER_LAYOUT_VERSION,
            "purchase_receipt_red_voucher_v5",
        )
        + "\n      {% set blank_n = 5 - (items|length) %}\n"
    )
    v5 = v5.replace(
        '<h1 class="title">采购入库单</h1>',
        '<h1 class="title">采购入库单（启恒）</h1>',
    )
    patched, changed = apply_purchase_receipt_red_voucher_v4(v5)
    assert changed is True
    assert "blank_n" not in patched
    assert "采购入库单（启恒）" in patched
    assert PURCHASE_RECEIPT_RED_VOUCHER_LAYOUT_VERSION in patched


def test_print_html_inserts_kingdee_bill_before_grid():
    slip = (
        '<div><span class="lab">备注：</span><span class="val">{{ notes or "" }}</span></div>\n'
        "  </div>\n"
        '  <table class="grid">'
    )
    patched, changed = patch_print_kingdee_bill_no_html(slip)
    assert changed is True
    assert 'class="lab">金蝶单号' in patched
    assert patched.index("金蝶单号") < patched.index('<table class="grid">')
    assert patch_print_kingdee_bill_no_html(patched)[1] is False


def test_designer_schema_adds_kingdee_bill_field_once():
    schema = {
        "blocks": [
            {"type": "text", "content": "基本信息"},
            {
                "type": "columns",
                "cols": [
                    {"blocks": [{"type": "field", "key": "code", "label": "单号"}]},
                    {"blocks": []},
                ],
            },
        ]
    }
    assert patch_kingdee_bill_no_print_schema(schema) is True
    keys = [
        blk.get("key")
        for col in schema["blocks"][1]["cols"]
        for blk in col["blocks"]
    ]
    assert "kingdee_bill_no" in keys
    assert patch_kingdee_bill_no_print_schema(schema) is False

