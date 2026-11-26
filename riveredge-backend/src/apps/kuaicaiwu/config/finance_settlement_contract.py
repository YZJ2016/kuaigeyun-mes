"""发票/对账结算粒度契约（唯一常量真源）。"""

SETTLEMENT_MODE_SUMMARY = "summary"
SETTLEMENT_MODE_DETAIL = "detail"
SETTLEMENT_MODES = frozenset({SETTLEMENT_MODE_SUMMARY, SETTLEMENT_MODE_DETAIL})

STATEMENT_LINE_GRANULARITY_MATERIAL = "material_line"
STATEMENT_LINE_GRANULARITIES = frozenset({STATEMENT_LINE_GRANULARITY_MATERIAL})

DETAIL_INVOICE_LINE_MAPPING_STRICT_1_1 = "strict_1_1"

PARTNER_STATEMENT_LINE_KIND_MATERIAL = "material"
PARTNER_STATEMENT_LINE_KIND_FINANCE = "finance"

# 对账预览中可展开为物料行的 doc_type（中文或规范名）
PARTNER_STATEMENT_EXPANDABLE_DOC_TYPES = frozenset(
    {
        "销售出库",
        "sales_delivery",
        "采购入库",
        "purchase_receipt",
        "委外收货",
        "outsource_material_receipt",
        "工序委外收货",
    }
)