"""各仓储单据编辑保存后 batchUpdate 金蝶（替代 sync_*_kingdee_after_delete）。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.services.kingdee_im_batch_update_service import (
    KINGDEE_IM_WAREHOUSE_EDIT_SYNC_STATUSES,
    kingdee_im_batch_update_linked_bill,
)
from apps.kuaizhizao.services.kingdee_im_warehouse_revoke_service import (
    KingdeeImWarehouseRevokeSpec,
)
from infra.services.business_config_service import BusinessConfigService

TDoc = TypeVar("TDoc")
TItem = TypeVar("TItem")

PushSvc = Any


async def _run_im_batch_update_sync(
    *,
    tenant_id: int,
    source_id: int,
    acting_user_id: int,
    spec: KingdeeImWarehouseRevokeSpec,
    source_type: str,
    target_type: str,
    doc_model: type,
    item_model: type,
    item_fk: str,
    push_enabled: Callable[[Dict[str, Any]], bool],
    resolve_push_config: Callable[..., Awaitable[Dict[str, Any]]],
    push_service: PushSvc,
    doc_kw: str,
    load_items_kwargs: Optional[Dict[str, Any]] = None,
) -> None:
    # 撤销规格由各推送服务的 batch_update_linked_kingdee_bill 持有。
    del spec
    doc = await doc_model.get_or_none(
        tenant_id=tenant_id,
        id=source_id,
        deleted_at__isnull=True,
    )
    if not doc:
        return
    status = str(getattr(doc, "status", None) or "").strip()
    if status not in KINGDEE_IM_WAREHOUSE_EDIT_SYNC_STATUSES:
        return

    relation = await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
        target_type=target_type,
    ).first()
    if not relation:
        return

    biz_config = await BusinessConfigService().get_business_config(tenant_id)
    warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
    item_filter = {item_fk: source_id, "tenant_id": tenant_id}
    if load_items_kwargs:
        item_filter.update(load_items_kwargs)
    items: List[Any] = await item_model.filter(**item_filter).order_by("id")
    config = await resolve_push_config(tenant_id, warehouse, doc, items)
    if not push_enabled(config):
        return

    await push_service.batch_update_linked_kingdee_bill(
        tenant_id=tenant_id,
        **{doc_kw: doc},
        items=list(items),
        acting_user_id=acting_user_id,
        relation=relation,
        config=config,
        dry_run=False,
    )


async def sync_other_inbound_kingdee_after_update(
    tenant_id: int, inbound_id: int, *, acting_user_id: int
) -> None:
    from apps.kuaizhizao.models.other_inbound import OtherInbound
    from apps.kuaizhizao.models.other_inbound_item import OtherInboundItem
    from apps.kuaizhizao.services.kingdee_im_warehouse_revoke_service import (
        OTHER_INBOUND_REVOKE_SPEC,
    )
    from apps.kuaizhizao.services.kingdee_other_inbound_push_service import (
        SOURCE_TYPE as ST,
    )
    from apps.kuaizhizao.services.kingdee_other_inbound_push_service import (
        TARGET_TYPE as TT,
    )
    from apps.kuaizhizao.services.kingdee_other_inbound_push_service import (
        KingdeeOtherInboundPushService,
    )

    svc = KingdeeOtherInboundPushService()

    async def _cfg(tid: int, _wh: Dict[str, Any], _doc: OtherInbound, _items: List[Any]) -> Dict[str, Any]:
        return await svc.get_push_config(tid)

    await _run_im_batch_update_sync(
        tenant_id=tenant_id,
        source_id=inbound_id,
        acting_user_id=acting_user_id,
        spec=OTHER_INBOUND_REVOKE_SPEC,
        source_type=ST,
        target_type=TT,
        doc_model=OtherInbound,
        item_model=OtherInboundItem,
        item_fk="inbound_id",
        push_enabled=lambda c: bool(c.get("enabled", False)),
        resolve_push_config=_cfg,
        push_service=svc,
        doc_kw="inbound",
    )


async def sync_other_outbound_kingdee_after_update(
    tenant_id: int, outbound_id: int, *, acting_user_id: int
) -> None:
    from apps.kuaizhizao.models.other_outbound import OtherOutbound
    from apps.kuaizhizao.models.other_outbound_item import OtherOutboundItem
    from apps.kuaizhizao.services.kingdee_im_warehouse_revoke_service import (
        OTHER_OUTBOUND_REVOKE_SPEC,
    )
    from apps.kuaizhizao.services.kingdee_other_outbound_push_service import (
        SOURCE_TYPE as ST,
    )
    from apps.kuaizhizao.services.kingdee_other_outbound_push_service import (
        TARGET_TYPE as TT,
    )
    from apps.kuaizhizao.services.kingdee_other_outbound_push_service import (
        KingdeeOtherOutboundPushService,
    )
    from core.services.integration.kingdee_warehouse_push_routing import (
        resolve_other_outbound_push_config,
    )

    svc = KingdeeOtherOutboundPushService()

    async def _cfg(tid: int, wh: Dict[str, Any], doc: OtherOutbound, items: List[Any]) -> Dict[str, Any]:
        mids = [int(it.material_id) for it in items if getattr(it, "material_id", None)]
        return await resolve_other_outbound_push_config(tid, wh, material_ids=mids)

    await _run_im_batch_update_sync(
        tenant_id=tenant_id,
        source_id=outbound_id,
        acting_user_id=acting_user_id,
        spec=OTHER_OUTBOUND_REVOKE_SPEC,
        source_type=ST,
        target_type=TT,
        doc_model=OtherOutbound,
        item_model=OtherOutboundItem,
        item_fk="outbound_id",
        push_enabled=lambda c: bool(c.get("enabled", False)),
        resolve_push_config=_cfg,
        push_service=svc,
        doc_kw="outbound",
    )


async def sync_sales_delivery_kingdee_after_update(
    tenant_id: int, delivery_id: int, *, acting_user_id: int
) -> None:
    from apps.kuaizhizao.models.sales_delivery import SalesDelivery
    from apps.kuaizhizao.models.sales_delivery_item import SalesDeliveryItem
    from apps.kuaizhizao.services.kingdee_im_warehouse_revoke_service import (
        SALES_DELIVERY_REVOKE_SPEC,
    )
    from apps.kuaizhizao.services.kingdee_sales_delivery_push_service import (
        SOURCE_TYPE as ST,
    )
    from apps.kuaizhizao.services.kingdee_sales_delivery_push_service import (
        TARGET_TYPE as TT,
    )
    from apps.kuaizhizao.services.kingdee_sales_delivery_push_service import (
        KingdeeSalesDeliveryPushService,
    )

    svc = KingdeeSalesDeliveryPushService()

    async def _cfg(tid: int, _wh: Dict[str, Any], _doc: SalesDelivery, _items: List[Any]) -> Dict[str, Any]:
        return await svc.get_push_config(tid)

    await _run_im_batch_update_sync(
        tenant_id=tenant_id,
        source_id=delivery_id,
        acting_user_id=acting_user_id,
        spec=SALES_DELIVERY_REVOKE_SPEC,
        source_type=ST,
        target_type=TT,
        doc_model=SalesDelivery,
        item_model=SalesDeliveryItem,
        item_fk="delivery_id",
        push_enabled=lambda c: bool(c.get("enabled", False)),
        resolve_push_config=_cfg,
        push_service=svc,
        load_items_kwargs={"deleted_at__isnull": True},
        doc_kw="delivery",
    )


async def sync_production_picking_kingdee_after_update(
    tenant_id: int, picking_id: int, *, acting_user_id: int
) -> None:
    from apps.kuaizhizao.models.production_picking import ProductionPicking
    from apps.kuaizhizao.models.production_picking_item import ProductionPickingItem
    from apps.kuaizhizao.services.kingdee_im_warehouse_revoke_service import (
        PRODUCTION_PICKING_REVOKE_SPEC,
    )
    from apps.kuaizhizao.services.kingdee_production_picking_push_service import (
        SOURCE_TYPE as ST,
    )
    from apps.kuaizhizao.services.kingdee_production_picking_push_service import (
        TARGET_TYPE as TT,
    )
    from apps.kuaizhizao.services.kingdee_production_picking_push_service import (
        KingdeeProductionPickingPushService,
    )
    from core.services.integration.kingdee_warehouse_push_routing import (
        resolve_production_picking_push_config,
    )

    svc = KingdeeProductionPickingPushService()

    async def _cfg(tid: int, wh: Dict[str, Any], _doc: ProductionPicking, _items: List[Any]) -> Dict[str, Any]:
        return resolve_production_picking_push_config(wh)

    await _run_im_batch_update_sync(
        tenant_id=tenant_id,
        source_id=picking_id,
        acting_user_id=acting_user_id,
        spec=PRODUCTION_PICKING_REVOKE_SPEC,
        source_type=ST,
        target_type=TT,
        doc_model=ProductionPicking,
        item_model=ProductionPickingItem,
        item_fk="picking_id",
        push_enabled=lambda c: bool(c.get("enabled", False)),
        resolve_push_config=_cfg,
        push_service=svc,
        doc_kw="picking",
    )


async def sync_finished_goods_receipt_kingdee_after_update(
    tenant_id: int, receipt_id: int, *, acting_user_id: int
) -> None:
    from apps.kuaizhizao.models.finished_goods_receipt import FinishedGoodsReceipt
    from apps.kuaizhizao.models.finished_goods_receipt_item import FinishedGoodsReceiptItem
    from apps.kuaizhizao.services.kingdee_finished_goods_receipt_push_service import (
        SOURCE_TYPE as ST,
    )
    from apps.kuaizhizao.services.kingdee_finished_goods_receipt_push_service import (
        TARGET_TYPE as TT,
    )
    from apps.kuaizhizao.services.kingdee_finished_goods_receipt_push_service import (
        KingdeeFinishedGoodsReceiptPushService,
    )
    from apps.kuaizhizao.services.kingdee_im_warehouse_revoke_service import (
        FINISHED_GOODS_RECEIPT_REVOKE_SPEC,
    )
    from core.services.integration.kingdee_warehouse_push_routing import (
        resolve_finished_goods_push_config,
    )

    svc = KingdeeFinishedGoodsReceiptPushService()

    async def _cfg(tid: int, wh: Dict[str, Any], _doc: FinishedGoodsReceipt, _items: List[Any]) -> Dict[str, Any]:
        return resolve_finished_goods_push_config(wh)

    await _run_im_batch_update_sync(
        tenant_id=tenant_id,
        source_id=receipt_id,
        acting_user_id=acting_user_id,
        spec=FINISHED_GOODS_RECEIPT_REVOKE_SPEC,
        source_type=ST,
        target_type=TT,
        doc_model=FinishedGoodsReceipt,
        item_model=FinishedGoodsReceiptItem,
        item_fk="receipt_id",
        push_enabled=lambda c: bool(c.get("enabled", False)),
        resolve_push_config=_cfg,
        push_service=svc,
        doc_kw="receipt",
    )


async def sync_purchase_receipt_kingdee_after_update(
    tenant_id: int, receipt_id: int, *, acting_user_id: int
) -> None:
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
    from apps.kuaizhizao.services.kingdee_purchase_receipt_push_service import (
        SOURCE_TYPE as ST,
    )
    from apps.kuaizhizao.services.kingdee_purchase_receipt_push_service import (
        TARGET_TYPE as TT,
    )
    from apps.kuaizhizao.services.kingdee_purchase_receipt_push_service import (
        KingdeePurchaseReceiptPushService,
    )
    from core.services.integration.kingdee_warehouse_push_routing import (
        resolve_purchase_receipt_push_config,
    )

    doc = await PurchaseReceipt.get_or_none(
        tenant_id=tenant_id,
        id=receipt_id,
        deleted_at__isnull=True,
    )
    if not doc:
        return
    status = str(getattr(doc, "status", None) or "").strip()
    if status not in KINGDEE_IM_WAREHOUSE_EDIT_SYNC_STATUSES:
        return
    relation = await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type=ST,
        source_id=receipt_id,
        target_type=TT,
    ).first()
    if not relation:
        return
    items = await PurchaseReceiptItem.filter(
        tenant_id=tenant_id,
        receipt_id=receipt_id,
        deleted_at__isnull=True,
    ).order_by("id")
    biz_config = await BusinessConfigService().get_business_config(tenant_id)
    warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
    config = await resolve_purchase_receipt_push_config(
        tenant_id,
        warehouse,
        material_ids=[int(it.material_id) for it in items if getattr(it, "material_id", None)],
        order_type=getattr(doc, "order_type", None),
    )
    if not bool(config.get("enabled", False)):
        return
    svc = KingdeePurchaseReceiptPushService()
    await svc.batch_update_linked_kingdee_bill(
        tenant_id=tenant_id,
        receipt=doc,
        items=list(items),
        acting_user_id=acting_user_id,
        relation=relation,
        config=config,
        dry_run=False,
    )
