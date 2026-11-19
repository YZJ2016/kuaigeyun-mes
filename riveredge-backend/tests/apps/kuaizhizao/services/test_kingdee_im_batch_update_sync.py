"""编辑保存后回写金蝶：方法在位，且更新函数在事务外调用。"""

import inspect

from apps.kuaizhizao.services.kingdee_finished_goods_receipt_push_service import (
    KingdeeFinishedGoodsReceiptPushService,
)
from apps.kuaizhizao.services.kingdee_im_batch_update_sync import (
    sync_finished_goods_receipt_kingdee_after_update,
    sync_other_inbound_kingdee_after_update,
    sync_other_outbound_kingdee_after_update,
    sync_production_picking_kingdee_after_update,
    sync_purchase_receipt_kingdee_after_update,
    sync_sales_delivery_kingdee_after_update,
)
from apps.kuaizhizao.services.kingdee_other_inbound_push_service import (
    KingdeeOtherInboundPushService,
)
from apps.kuaizhizao.services.kingdee_other_outbound_push_service import (
    KingdeeOtherOutboundPushService,
)
from apps.kuaizhizao.services.kingdee_production_picking_push_service import (
    KingdeeProductionPickingPushService,
)
from apps.kuaizhizao.services.kingdee_purchase_receipt_push_service import (
    KingdeePurchaseReceiptPushService,
)
from apps.kuaizhizao.services.kingdee_sales_delivery_push_service import (
    KingdeeSalesDeliveryPushService,
)
from apps.kuaizhizao.services.warehouse_service import (
    FinishedGoodsReceiptService,
    OtherInboundService,
    OtherOutboundService,
    ProductionPickingService,
    PurchaseReceiptService,
    SalesDeliveryService,
)


def test_push_services_expose_batch_update():
    for cls in (
        KingdeeOtherInboundPushService,
        KingdeeOtherOutboundPushService,
        KingdeeSalesDeliveryPushService,
        KingdeePurchaseReceiptPushService,
        KingdeeProductionPickingPushService,
        KingdeeFinishedGoodsReceiptPushService,
    ):
        assert callable(cls.batch_update_linked_kingdee_bill)


def test_warehouse_updates_call_sync_after_save():
    pairs = (
        (ProductionPickingService.update_production_picking, sync_production_picking_kingdee_after_update),
        (SalesDeliveryService.update_sales_delivery, sync_sales_delivery_kingdee_after_update),
        (PurchaseReceiptService.update_purchase_receipt, sync_purchase_receipt_kingdee_after_update),
        (OtherInboundService.update_other_inbound, sync_other_inbound_kingdee_after_update),
        (OtherOutboundService.update_other_outbound, sync_other_outbound_kingdee_after_update),
    )
    for method, sync_fn in pairs:
        source = inspect.getsource(method)
        await_lines = [
            line
            for line in source.splitlines()
            if f"await {sync_fn.__name__}" in line
        ]
        assert len(await_lines) == 1
        assert await_lines[0].startswith("        await ")


def test_finished_goods_sync_helper_exists_without_local_update_method():
    assert callable(sync_finished_goods_receipt_kingdee_after_update)
    assert not hasattr(FinishedGoodsReceiptService, "update_finished_goods_receipt")
