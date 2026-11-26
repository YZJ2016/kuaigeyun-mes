"""采购入库红框凭证 HTML 真源（对齐纸质外购入库单样例）。"""

from __future__ import annotations

import re

PURCHASE_RECEIPT_RED_VOUCHER_LAYOUT_VERSION = "purchase_receipt_red_voucher_v10"

PURCHASE_RECEIPT_RED_VOUCHER_HTML = """\
<style>
  @page { size: 210mm 148mm; margin: 0; }
  * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body {
    margin: 0; padding: 0;
    font-family: "SimSun", "Songti SC", "Microsoft YaHei", serif;
    font-size: 10.5pt; color: #000; line-height: 1.25;
  }
  .voucher { width: 100%; max-width: none; margin: 0; padding: 7mm 10mm 6mm 10mm; color: #c00000; }
  .title {
    text-align: center; font-size: 18pt; font-weight: 700;
    letter-spacing: 6px; color: #c00000; margin: 0 0 4px;
  }
  .meta {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px 20px;
    color: #c00000;
    font-size: 10.5pt;
    margin-bottom: 4px;
  }
  .meta .label { color: #c00000; }
  .meta .value { color: #000; border-bottom: 1px solid #c00000; min-height: 1.1em; padding: 0 3px; }
  table.grid {
    width: 100%; border-collapse: collapse; table-layout: fixed;
    border: 1.5px solid #c00000; color: #000; font-size: 10pt;
  }
  table.grid th, table.grid td {
    border: 1px solid #c00000; padding: 2px 2px; vertical-align: middle;
    line-height: 1.2;
    word-break: break-all;
    overflow-wrap: anywhere;
    white-space: normal;
    overflow: hidden;
  }
  table.grid th {
    color: #c00000; font-weight: 700; text-align: center; background: #fff;
    padding: 3px 1px; font-size: 9.5pt;
  }
  table.grid td.wrap-tight {
    word-break: break-all;
    overflow-wrap: anywhere;
    font-size: 9pt;
  }
  table.grid td.num {
    text-align: right;
    word-break: break-all;
    overflow-wrap: anywhere;
    font-size: 9pt;
  }
  table.grid td.center { text-align: center; }
  .total-label { color: #c00000; font-weight: 700; text-align: center; }
  .signs {
    margin-top: 6px;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 6px;
    color: #c00000;
    font-size: 10.5pt;
  }
  .signs .box { min-height: 22px; }
  .signs .name { color: #000; margin-left: 4px; }
</style>
<div class="voucher">
  <h1 class="title">采购入库单</h1>
  <div class="meta">
    <div><span class="label">采购方式：</span><span class="value">{{ bill_type_label or "标准采购入库单" }}</span></div>
    <div><span class="label">编号：</span><span class="value">{{ code or "—" }}</span></div>
    <div><span class="label">供应商：</span><span class="value">{{ supplier_name or "—" }}</span></div>
    <div><span class="label">日期：</span><span class="value">{{ ((receipt_time or created_at) or "")[:10] or "—" }}</span></div>
    <div><span class="label">金蝶单号：</span><span class="value">{{ kingdee_bill_no or "—" }}</span></div>
  </div>
  <table class="grid">
    <colgroup>
      <col style="width:4%" />
      <col style="width:8%" />
      <col style="width:10%" />
      <col style="width:11%" />
      <col style="width:4%" />
      <col style="width:6%" />
      <col style="width:6%" />
      <col style="width:7%" />
      <col style="width:9%" />
      <col style="width:7%" />
      <col style="width:8%" />
      <col style="width:10%" />
      <col style="width:10%" />
    </colgroup>
    <thead>
      <tr>
        <th>行号</th>
        <th>物料编码</th>
        <th>物料名称</th>
        <th>规格型号</th>
        <th>单位</th>
        <th>实收数量</th>
        <th>单价</th>
        <th>金额</th>
        <th>收料仓库</th>
        <th>仓位</th>
        <th>备注</th>
        <th>物资类型</th>
        <th>采购订单</th>
      </tr>
    </thead>
    <tbody>
      {% for item in items %}
      <tr>
        <td class="center">{{ loop.index }}</td>
        <td class="wrap-tight">{{ item.material_code or "" }}</td>
        <td>{{ item.material_name or "" }}</td>
        <td>{{ item.material_spec or "" }}</td>
        <td class="center">{{ item.material_unit or "" }}</td>
        <td class="num">{% if item.receipt_quantity not in [None, ""] %}{{ "%.2f"|format(item.receipt_quantity|float) }}{% endif %}</td>
        <td class="num">{{ item.unit_price or "" }}</td>
        <td class="num">{{ item.total_amount or "" }}</td>
        <td class="wrap-tight">{{ item.warehouse_name or warehouse_name or "" }}</td>
        <td>{{ item.location_name or item.location_code or "" }}</td>
        <td>{{ item.notes or "" }}</td>
        <td class="center">{{ item.material_inventory_category or "" }}</td>
        <td class="wrap-tight">{{ purchase_order_code or "" }}</td>
      </tr>
      {% endfor %}
      <tr>
        <td colspan="5" class="total-label">合计</td>
        <td class="num">{% if total_quantity not in [None, ""] %}{{ "%.2f"|format(total_quantity|float) }}{% endif %}</td>
        <td></td>
        <td class="num">{{ total_amount if total_amount and total_amount not in ['0', '0.0', '0.00', '0.000000'] else "" }}</td>
        <td colspan="5"></td>
      </tr>
    </tbody>
  </table>
  <div class="signs">
    <div class="box">审核：<span class="name">{{ reviewer_name or "" }}</span></div>
    <div class="box">记账：<span class="name">{{ reviewer_name or "" }}</span></div>
    <div class="box">收货：<span class="name">{{ receiver_name or "" }}</span></div>
    <div class="box">采购：<span class="name">{{ buyer_name or "" }}</span></div>
    <div class="box">制单：<span class="name">{{ created_by_name or "" }}</span></div>
  </div>
</div>
"""


def _preserve_purchase_receipt_red_voucher_title(old_html: str, new_html: str) -> str:
    """库内已写死的公司简称标题（h1）在版式升级时保留。"""
    match = re.search(r'<h1 class="title">([^<]+)</h1>', str(old_html or ""))
    if not match:
        return new_html
    title = match.group(1).strip()
    if title and title != "采购入库单" and "采购入库单" in title:
        return new_html.replace(
            '<h1 class="title">采购入库单</h1>',
            f'<h1 class="title">{title}</h1>',
        )
    return new_html


def purchase_receipt_red_voucher_html_needs_v4(html: str) -> bool:
    text = str(html or "")
    if not text or "采购入库单" not in text:
        return False
    # v6 及更早：12 列宽合计 106%，末列「物资类型」会被裁切
    if "purchase_receipt_red_voucher_v6" in text and "width:7%" in text and "width:5%" in text:
        return True
    # v7：列宽已 100%，但单元格未强制换行，金额等会溢出邻列
    if "purchase_receipt_red_voucher_v7" in text and "overflow-wrap: anywhere" not in text:
        return True
    if "<th>采购订单</th>" not in text and (
        "purchase_receipt_red_voucher_v9" in text
        or "purchase_receipt_red_voucher_v10" in text
    ):
        return True
    if "purchase_receipt_red_voucher_v10" in text:
        return False
    if "purchase_receipt_red_voucher_v9" in text:
        return False
    if PURCHASE_RECEIPT_RED_VOUCHER_LAYOUT_VERSION in text:
        if "margin: 7mm 10mm 6mm 10mm" in text:
            return True
        if "page-break-inside: avoid" in text and ".signs" in text:
            return True
        return False
    if "blank_n" in text and "items|length" in text:
        return True
    if "purchase_receipt_red_voucher_v4" in text:
        return True
    if "采购方式：" in text:
        return True
    if "单据类型：" in text:
        return True
    if "<th>收货仓库</th>" in text and "<th>收料仓库</th>" not in text:
        return True
    if "<th>库位</th>" in text and "<th>仓位</th>" not in text:
        return True
    if "item.total_amount" in text and "<th>金额</th>" in text:
        wh_pos = text.find("warehouse_name")
        amt_pos = text.find("item.total_amount")
        loc_pos = text.find("location_name")
        if wh_pos > 0 and amt_pos > wh_pos and loc_pos > amt_pos:
            th_amt = text.find("<th>金额</th>")
            th_loc = text.find("<th>库位</th>")
            if th_loc > 0 and th_amt > 0 and th_loc < th_amt:
                return True
    return False


def apply_purchase_receipt_red_voucher_v4(html: str) -> tuple[str, bool]:
    if not purchase_receipt_red_voucher_html_needs_v4(html):
        return html, False
    out = _preserve_purchase_receipt_red_voucher_title(html, PURCHASE_RECEIPT_RED_VOUCHER_HTML)
    marker = "<!--" + PURCHASE_RECEIPT_RED_VOUCHER_LAYOUT_VERSION + "-->"
    if marker not in out:
        out = out + "\n" + marker
    return out, True
