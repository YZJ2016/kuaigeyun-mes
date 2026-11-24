"""工序委外单格线表打印（与默认可视化模板并列可选）。"""

from __future__ import annotations

GRID_OUTSOURCE_ORDER_PRINT_CODE = "OUTSOURCE_ORDER_GRID_PRINT"
GRID_OUTSOURCE_ORDER_PRINT_NAME = "工序委外单（格线表）"

GRID_OUTSOURCE_ORDER_PRINT_HTML = """<!DOCTYPE html>
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
  .oo-title {
    text-align: center;
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 12px;
  }
  table.oo-grid {
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
  }
  table.oo-grid th,
  table.oo-grid td {
    border: 1px solid #000;
    padding: 6px 4px;
    vertical-align: middle;
    text-align: center;
    word-wrap: break-word;
  }
  table.oo-grid th {
    font-weight: 700;
  }
  .oo-left { text-align: left; }
</style>
</head>
<body>
  <div class="oo-title">委外单</div>
  <table class="oo-grid">
    <thead>
      <tr>
        <th style="width:6%">序号</th>
        <th style="width:22%">产品名称</th>
        <th style="width:12%">规格</th>
        <th style="width:14%">工序</th>
        <th style="width:8%">单位</th>
        <th style="width:10%">数量</th>
        <th style="width:14%">交期</th>
        <th style="width:14%">备注</th>
      </tr>
    </thead>
    <tbody>
      {% for row in items %}
      <tr>
        <td>{{ row.line_no or loop.index }}</td>
        <td class="oo-left">{{ row.product_name or '' }}</td>
        <td>{{ row.material_spec or '' }}</td>
        <td>{{ row.operation_name or '' }}</td>
        <td>{{ row.unit or '' }}</td>
        <td>{{ row.quantity or '' }}</td>
        <td>{{ row.delivery_date or '' }}</td>
        <td class="oo-left">{{ row.notes or '' }}</td>
      </tr>
      {% endfor %}
      <tr>
        <td></td>
        <td class="oo-left">合计</td>
        <td></td>
        <td></td>
        <td></td>
        <td>{{ total_quantity or '' }}</td>
        <td></td>
        <td></td>
      </tr>
    </tbody>
  </table>
</body>
</html>
"""


def grid_outsource_order_print_preset() -> dict:
    return {
        "name": GRID_OUTSOURCE_ORDER_PRINT_NAME,
        "code": GRID_OUTSOURCE_ORDER_PRINT_CODE,
        "type": "html",
        "description": "工序委外单格线表（产品/工序/数量/交期/合计行）",
        "content": GRID_OUTSOURCE_ORDER_PRINT_HTML,
        "config": {
            "document_type": "outsource_order",
            "engine": "jinja2",
            "strict_variables": False,
            "page": {"size": "A4", "orientation": "portrait", "margin": "14mm 12mm"},
        },
        "is_active": True,
        "is_default": False,
    }