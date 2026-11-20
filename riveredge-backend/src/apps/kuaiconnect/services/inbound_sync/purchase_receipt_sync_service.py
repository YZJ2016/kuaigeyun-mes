"""采购入库单出站绑定服务（本阶段仅 push-binding，无入站同步）。"""

from __future__ import annotations

from typing import Optional

from apps.kuaizhizao.models.purchase_receipt_sync_binding import PurchaseReceiptSyncBinding
from apps.kuaizhizao.schemas.purchase_receipt_sync import (
    PurchaseReceiptPushBindingOut,
    PurchaseReceiptPushBindingUpsert,
)


class PurchaseReceiptSyncService:
    async def filter_purchase_receipt_ids_for_outbound_sync(
        self, tenant_id: int, receipt_ids: list[int]
    ) -> list[int]:
        """出站外推/同步候选：排除服务采购入库单。"""
        from apps.kuaizhizao.constants.purchase_order_type import is_service_purchase_order_type
        from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

        ids = sorted({int(rid) for rid in receipt_ids if int(rid or 0) > 0})
        if not ids:
            return []
        rows = await PurchaseReceipt.filter(
            tenant_id=tenant_id,
            id__in=ids,
            deleted_at__isnull=True,
        ).values("id", "order_type")
        return [
            int(row["id"])
            for row in rows
            if not is_service_purchase_order_type(row.get("order_type"))
        ]

    def serialize_push_binding(
        self, row: Optional[PurchaseReceiptSyncBinding]
    ) -> PurchaseReceiptPushBindingOut:
        from core.schemas.sync_binding_contract import DocumentPushTargetItem
        from apps.kuaiconnect.services.inbound_sync.sync_binding_sources import (
            push_targets_from_row,
            trigger_actions_from_row,
        )

        if not row or not isinstance(getattr(row, "push_targets", None), list):
            return PurchaseReceiptPushBindingOut()
        stored = [DocumentPushTargetItem.model_validate(item) for item in push_targets_from_row(row)]
        targets = [item for item in stored if item.user_saved]
        first = targets[0] if targets else None
        return PurchaseReceiptPushBindingOut(
            targets=targets,
            trigger_actions=trigger_actions_from_row(row) if targets else [],
            connection_code=first.connection_code if first else None,
            save_api_uuid=first.save_api_uuid if first else None,
            sync_mode=str(getattr(row, "sync_mode", None) or "manual_full"),
            schedule_interval_minutes=int(getattr(row, "schedule_interval_minutes", None) or 15),
            targets_configured=True,
        )

    async def get_push_binding(self, tenant_id: int) -> PurchaseReceiptPushBindingOut:
        row = await PurchaseReceiptSyncBinding.filter(tenant_id=tenant_id).first()
        out = self.serialize_push_binding(row)
        if (
            row
            and isinstance(getattr(row, "push_targets", None), list)
            and out.targets_configured
            and not out.targets
            and getattr(row, "push_targets", None)
        ):
            await PurchaseReceiptSyncBinding.filter(id=row.id).update(
                push_targets=[], trigger_actions=[]
            )
        return out

    async def upsert_push_binding(
        self,
        tenant_id: int,
        body: PurchaseReceiptPushBindingUpsert,
    ) -> PurchaseReceiptPushBindingOut:
        from apps.kuaiconnect.services.inbound_sync.sync_binding_sources import (
            normalize_push_targets_json,
        )

        row = await PurchaseReceiptSyncBinding.filter(tenant_id=tenant_id).first()
        if not row:
            row = await PurchaseReceiptSyncBinding.create(tenant_id=tenant_id)
        targets = normalize_push_targets_json(
            [item.model_dump(mode="json") for item in body.targets]
        )
        triggers = [
            str(action).strip().lower() for action in body.trigger_actions if str(action).strip()
        ]
        await PurchaseReceiptSyncBinding.filter(id=row.id).update(
            push_targets=targets,
            trigger_actions=triggers,
        )
        fresh = await PurchaseReceiptSyncBinding.get(id=row.id)
        return self.serialize_push_binding(fresh)


purchase_receipt_sync_service = PurchaseReceiptSyncService()
