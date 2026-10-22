"""场景 ship：发货通知 / 出库。"""

SHIP_STEPS = (
    {
        "key": "shipment_delivery",
        "service": "ShipmentNoticeService|SalesDeliveryService",
        "label": "发货出库",
    },
)
