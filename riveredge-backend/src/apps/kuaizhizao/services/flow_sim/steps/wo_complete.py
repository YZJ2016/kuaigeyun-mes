"""场景 wo_complete：补库 → 领料 → 报工 → IPQC → FQC → 成品入。"""

WO_COMPLETE_STEPS = (
    {"key": "inventory_topup", "service": "InventoryAdjustmentService", "label": "补库"},
    {
        "key": "production_picking",
        "service": "ProductionPickingService",
        "label": "生产领料",
    },
    {"key": "reporting", "service": "ProductionReportingService", "label": "工序报工"},
    {
        "key": "process_inspection",
        "service": "ProcessInspectionService",
        "label": "过程检",
    },
    {
        "key": "finished_goods_inspection",
        "service": "FinishedGoodsInspectionService",
        "label": "成品检",
    },
    {
        "key": "finished_goods_receipt",
        "service": "FinishedGoodsReceiptService",
        "label": "成品入库",
    },
)
