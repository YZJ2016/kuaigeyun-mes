"""场景 purchase_inbound：审 PO → IQC（策略）→ 确认入库。"""

PURCHASE_INBOUND_STEPS = (
    {"key": "purchase", "service": "PurchaseOrderService", "label": "采购审核"},
    {
        "key": "incoming_inspection",
        "service": "IncomingInspectionService",
        "label": "来料检",
    },
    {
        "key": "purchase_inbound",
        "service": "PurchaseReceiptService",
        "label": "采购入库确认",
    },
)
