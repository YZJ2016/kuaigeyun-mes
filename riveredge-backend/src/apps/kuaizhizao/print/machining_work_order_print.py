"""工单机加工版打印（格线表样，与工单默认可视化模板并列可选）。"""

from __future__ import annotations

MACHINING_WORK_ORDER_PRINT_CODE = "WORK_ORDER_MACHINING_PRINT"
MACHINING_WORK_ORDER_PRINT_NAME = "工单（机加工）"

MACHINING_WORK_ORDER_PRINT_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<style>
  @page { size: A4; margin: 14mm 12mm; }
  body {
    font-family: "Microsoft YaHei", "SimSun", sans-serif;
    font-size: 12px;
    color: #000;
    margin: 0;
    padding: 0;
  }
  .mo-company {
    text-align: center;
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 10px;
  }
  .mo-head {
    margin-bottom: 8px;
    line-height: 1.6;
  }
  table.mo-grid {
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
  }
  table.mo-grid th,
  table.mo-grid td {
    border: 1px solid #000;
    padding: 5px 4px;
    vertical-align: top;
    word-wrap: break-word;
  }
  table.mo-grid th {
    text-align: center;
    font-weight: 700;
  }
  .mo-center { text-align: center; }
  .mo-meta {
    margin-top: 14px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 16px;
    line-height: 1.8;
  }
</style>
</head>
<body>
  <div class="mo-company">{{ site_name or '' }}</div>
  <div class="mo-head">
    工单号：{{ code or '' }}　车间：{{ workshop_name or '' }}　计划完工：{{ planned_end_date or '' }}
  </div>
  <table class="mo-grid">
    <thead>
      <tr>
        <th style="width:5%">序号</th>
        <th style="width:10%">客户名称</th>
        <th style="width:12%">图号名称</th>
        <th style="width:8%">材料</th>
        <th style="width:10%">规格</th>
        <th style="width:26%">工艺要求</th>
        <th style="width:8%">数量(件)</th>
        <th style="width:10%">交货期</th>
        <th style="width:11%">备注</th>
      </tr>
    </thead>
    <tbody>
      {% for row in items %}
      <tr>
        <td class="mo-center">{{ row.line_no or loop.index }}</td>
        <td>{{ row.customer_name or '' }}</td>
        <td>{{ row.drawing_name or row.product_name or '' }}</td>
        <td class="mo-center">{{ row.material_grade or row.material_model or '' }}</td>
        <td class="mo-center">{{ row.material_spec or '' }}</td>
        <td>{{ row.process_requirements or '' }}</td>
        <td class="mo-center">{{ row.quantity or '' }}</td>
        <td class="mo-center">{{ row.required_date or row.delivery_date or '' }}</td>
        <td>{{ row.notes or row.remarks or '' }}</td>
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
        "description": "机加工工单格线表样（客户/图号/材料/工艺要求）",
        "content": MACHINING_WORK_ORDER_PRINT_HTML,
        "config": {
            "document_type": "work_order",
            "engine": "jinja2",
            "strict_variables": False,
            "page": {"size": "A4", "orientation": "portrait", "margin": "14mm 12mm"},
        },
        "is_active": True,
        "is_default": False,
    }