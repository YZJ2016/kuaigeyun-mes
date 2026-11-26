"""工单机加工版打印（格线表样，与工单默认可视化模板并列可选）。"""

from __future__ import annotations

from apps.kuaizhizao.print.document_qrcode import DOCUMENT_PRINT_QRCODE_SIZE

MACHINING_WORK_ORDER_PRINT_CODE = "WORK_ORDER_MACHINING_PRINT"
MACHINING_WORK_ORDER_PRINT_NAME = "工单（机加工）"

# 纸张与连枝横送货单一致：A5 横向（210mm x 148mm）
MACHINING_WORK_ORDER_PAGE_SIZE = "210mm 148mm"
MACHINING_WORK_ORDER_PAGE_MARGIN = "6mm 10mm 6mm 8mm"

MACHINING_WORK_ORDER_PRINT_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<style>
  @page { size: """ + MACHINING_WORK_ORDER_PAGE_SIZE + """; margin: """ + MACHINING_WORK_ORDER_PAGE_MARGIN + """; }
  body {
    font-family: "Microsoft YaHei", "SimSun", sans-serif;
    font-size: 11px;
    color: #000;
    margin: 0;
    padding: 0;
  }
  .mo-top {
    position: relative;
    margin-bottom: 6px;
    min-height: 76px;
  }
  .mo-company {
    text-align: center;
    font-size: 15px;
    font-weight: 700;
    padding: 0 80px 4px;
  }
  .mo-qr {
    position: absolute;
    right: 0;
    top: 0;
    width: 72px;
    text-align: center;
  }
  .mo-qr img {
    width: """ + str(DOCUMENT_PRINT_QRCODE_SIZE) + """px;
    height: """ + str(DOCUMENT_PRINT_QRCODE_SIZE) + """px;
    display: block;
    margin: 0 auto;
  }
  .mo-head {
    margin-bottom: 6px;
    line-height: 1.5;
    font-size: 11px;
    padding-right: 4px;
  }
  table.mo-grid {
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
  }
  table.mo-grid th,
  table.mo-grid td {
    border: 1px solid #000;
    padding: 4px 3px;
    vertical-align: top;
    word-wrap: break-word;
    line-height: 1.25;
  }
  table.mo-grid th {
    text-align: center;
    font-weight: 700;
  }
  .mo-center { text-align: center; }
  .mo-meta {
    margin-top: 10px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px 12px;
    line-height: 1.6;
    font-size: 11px;
  }
</style>
</head>
<body>
  <div class="mo-top">
    <div class="mo-company">{{ site_name or '' }}</div>
    {% if work_order_qrcode %}
    <div class="mo-qr">
      <img src="{{ work_order_qrcode | qrcode(size=""" + str(DOCUMENT_PRINT_QRCODE_SIZE) + """) }}" alt="" />
    </div>
    {% endif %}
  </div>
  <div class="mo-head">
    工单号：{{ code or '' }}　车间：{{ workshop_name or '' }}　计划完工：{{ planned_end_date or '' }}
  </div>
  <table class="mo-grid">
    <thead>
      <tr>
        <th style="width:6%">序号</th>
        <th style="width:18%">图号名称</th>
        <th style="width:10%">材料</th>
        <th style="width:12%">规格</th>
        <th style="width:36%">工艺要求</th>
        <th style="width:10%">数量(件)</th>
      </tr>
    </thead>
    <tbody>
      {% for row in items %}
      <tr>
        <td class="mo-center">{{ row.line_no or loop.index }}</td>
        <td>{{ row.drawing_name or row.product_name or '' }}</td>
        <td class="mo-center">{{ row.material_grade or row.material_model or '' }}</td>
        <td class="mo-center">{{ row.material_spec or '' }}</td>
        <td>{{ row.process_requirements or '' }}</td>
        <td class="mo-center">{{ row.quantity or '' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <div class="mo-meta">
    <div>制表人：{{ created_by_name or '' }}</div>
    <div>审核人：{{ reviewer_name or '' }}</div>
    <div>确认人：</div>
    <div>供应商确认人：</div>
    <div>制表时间：{{ print_time or '' }}</div>
  </div>
</body>
</html>
"""


def machining_work_order_print_preset() -> dict:
    return {
        "name": MACHINING_WORK_ORDER_PRINT_NAME,
        "code": MACHINING_WORK_ORDER_PRINT_CODE,
        "type": "html",
        "description": "机加工工单格线表样（A5 横，图号/材料/工艺要求）",
        "content": MACHINING_WORK_ORDER_PRINT_HTML,
        "config": {
            "document_type": "work_order",
            "engine": "jinja2",
            "strict_variables": False,
            "default_for_document_types": ["work_order"],
            "page": {
                "size": MACHINING_WORK_ORDER_PAGE_SIZE,
                "orientation": "landscape",
                "margin": MACHINING_WORK_ORDER_PAGE_MARGIN,
            },
        },
        "is_active": True,
        "is_default": True,
    }