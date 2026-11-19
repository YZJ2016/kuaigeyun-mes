"""接口硬删前：同步绑定引用登记（唯一真源）。

新增同步绑表 / push 字段时只改本文件，禁止在 delete_api 旁路堆特例。
"""

from __future__ import annotations

from typing import Any, Iterable, List, Sequence, Tuple, Type

from infra.exceptions.exceptions import ValidationError


def _iter_binding_specs() -> Sequence[Tuple[str, Type[Any], Tuple[str, ...]]]:
    """(展示名, Model, 直接存 api uuid 的列名)。sources / push_targets JSON 统一扫。"""
    from apps.master_data.models.master_data_sync_binding import (
        CustomerSyncBinding,
        EngineeringBomSyncBinding,
        MaterialGroupSyncBinding,
        MaterialSyncBinding,
        MaterialUnitSyncBinding,
        OperationSyncBinding,
        SupplierSyncBinding,
        WarehouseSyncBinding,
    )
    from apps.kuaizhizao.models.finished_goods_receipt_sync_binding import (
        FinishedGoodsReceiptSyncBinding,
    )
    from apps.kuaizhizao.models.inventory_sync_binding import InventorySyncBinding
    from apps.kuaizhizao.models.other_inbound_sync_binding import OtherInboundSyncBinding
    from apps.kuaizhizao.models.other_outbound_sync_binding import OtherOutboundSyncBinding
    from apps.kuaizhizao.models.production_picking_sync_binding import (
        ProductionPickingSyncBinding,
    )
    from apps.kuaizhizao.models.purchase_order_sync_binding import PurchaseOrderSyncBinding
    from apps.kuaizhizao.models.purchase_receipt_sync_binding import PurchaseReceiptSyncBinding
    from apps.kuaizhizao.models.reporting_sync_binding import ReportingSyncBinding
    from apps.kuaizhizao.models.sales_delivery_sync_binding import SalesDeliverySyncBinding
    from apps.kuaizhizao.models.sales_order_sync_binding import SalesOrderSyncBinding
    from apps.kuaizhizao.models.work_order_sync_binding import WorkOrderSyncBinding

    return (
        ("客户同步", CustomerSyncBinding, ("api_uuid",)),
        ("供应商同步", SupplierSyncBinding, ("api_uuid",)),
        ("仓库同步", WarehouseSyncBinding, ("api_uuid",)),
        ("物料同步", MaterialSyncBinding, ("api_uuid",)),
        ("计量单位同步", MaterialUnitSyncBinding, ("api_uuid",)),
        ("物料分组同步", MaterialGroupSyncBinding, ("api_uuid",)),
        ("工程BOM同步", EngineeringBomSyncBinding, ("api_uuid",)),
        ("工序同步", OperationSyncBinding, ("api_uuid",)),
        ("销售订单同步", SalesOrderSyncBinding, ("api_uuid",)),
        ("采购订单同步", PurchaseOrderSyncBinding, ("api_uuid",)),
        ("采购入库同步", PurchaseReceiptSyncBinding, ("api_uuid",)),
        ("销售出库同步", SalesDeliverySyncBinding, ("api_uuid",)),
        ("生产领料同步", ProductionPickingSyncBinding, ("api_uuid",)),
        ("成品入库同步", FinishedGoodsReceiptSyncBinding, ("api_uuid",)),
        ("其他入库同步", OtherInboundSyncBinding, ("api_uuid",)),
        ("其他出库同步", OtherOutboundSyncBinding, ("api_uuid",)),
        ("工单同步", WorkOrderSyncBinding, ("api_uuid", "push_save_api_uuid")),
        ("报工同步", ReportingSyncBinding, ("api_uuid",)),
        ("库存同步", InventorySyncBinding, ("api_uuid",)),
    )


def _uuids_in_sources(sources: Any) -> Iterable[str]:
    if not isinstance(sources, list):
        return
    for item in sources:
        if not isinstance(item, dict):
            continue
        for key in ("api_uuid", "uuid"):
            val = str(item.get(key) or "").strip()
            if val:
                yield val


def _uuids_in_push_targets(targets: Any) -> Iterable[str]:
    if not isinstance(targets, list):
        return
    for item in targets:
        if not isinstance(item, dict):
            continue
        for key in ("save_api_uuid", "api_uuid"):
            val = str(item.get(key) or "").strip()
            if val:
                yield val


async def assert_api_uuid_not_bound_by_sync(tenant_id: int, api_uuid: str) -> None:
    """硬删前：任一同步绑定仍引用该 uuid 则拒绝。"""
    target = str(api_uuid or "").strip()
    if not target:
        return
    hint = "请先在对应业务页的同步配置中删除该来源，再点「保存绑定」"
    for label, model, columns in _iter_binding_specs():
        row = await model.filter(tenant_id=tenant_id).first()
        if not row:
            continue
        for col in columns:
            if str(getattr(row, col, "") or "").strip() == target:
                raise ValidationError(f"接口仍被「{label}」引用，{hint}")
        for found in _uuids_in_sources(getattr(row, "sources", None)):
            if found == target:
                raise ValidationError(f"接口仍被「{label}」多来源配置引用，{hint}")
        for found in _uuids_in_push_targets(getattr(row, "push_targets", None)):
            if found == target:
                raise ValidationError(f"接口仍被「{label}」外推目标引用，{hint}")


def list_binding_registry_labels() -> List[str]:
    return [label for label, _, _ in _iter_binding_specs()]
