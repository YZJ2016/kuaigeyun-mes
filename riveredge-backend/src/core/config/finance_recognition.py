"""应收/应付确认时点（组织参数与客商覆盖）唯一码表。"""

REVENUE_RECOGNITION_VALUES = frozenset(
    {
        "on_shipment",
        "on_invoice",
        "on_milestone",
        "mixed",
        "manual",
        "on_partner_statement",
    }
)

PAYABLE_RECOGNITION_VALUES = frozenset(
    {
        "on_receipt",
        "on_purchase_invoice",
        "manual",
        "on_partner_statement",
    }
)

PARTNER_STATEMENT_LEDGER_MODES = frozenset({"immediate", "by_invoice"})
