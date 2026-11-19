"""成品入库单出站绑定服务（本阶段仅 push-binding，无入站同步）。"""

from __future__ import annotations

from typing import Optional

from apps.kuaizhizao.models.finished_goods_receipt_sync_binding import (
    FinishedGoodsReceiptSyncBinding,
)
from apps.kuaizhizao.schemas.finished_goods_receipt_sync import (
    FinishedGoodsReceiptPushBindingOut,
    FinishedGoodsReceiptPushBindingUpsert,
)


class FinishedGoodsReceiptSyncService:
    def serialize_push_binding(
        self, row: Optional[FinishedGoodsReceiptSyncBinding]
    ) -> FinishedGoodsReceiptPushBindingOut:
        from core.schemas.sync_binding_contract import DocumentPushTargetItem
        from core.services.data.sync_binding_sources import (
            push_targets_from_row,
            trigger_actions_from_row,
        )

        if not row or not isinstance(getattr(row, "push_targets", None), list):
            return FinishedGoodsReceiptPushBindingOut()
        stored = [DocumentPushTargetItem.model_validate(item) for item in push_targets_from_row(row)]
        targets = [item for item in stored if item.user_saved]
        first = targets[0] if targets else None
        return FinishedGoodsReceiptPushBindingOut(
            targets=targets,
            trigger_actions=trigger_actions_from_row(row) if targets else [],
            connection_code=first.connection_code if first else None,
            save_api_uuid=first.save_api_uuid if first else None,
            sync_mode=str(getattr(row, "sync_mode", None) or "manual_full"),
            schedule_interval_minutes=int(getattr(row, "schedule_interval_minutes", None) or 15),
            targets_configured=True,
        )

    async def get_push_binding(self, tenant_id: int) -> FinishedGoodsReceiptPushBindingOut:
        row = await FinishedGoodsReceiptSyncBinding.filter(tenant_id=tenant_id).first()
        out = self.serialize_push_binding(row)
        if (
            row
            and isinstance(getattr(row, "push_targets", None), list)
            and out.targets_configured
            and not out.targets
            and getattr(row, "push_targets", None)
        ):
            await FinishedGoodsReceiptSyncBinding.filter(id=row.id).update(
                push_targets=[], trigger_actions=[]
            )
        return out

    async def upsert_push_binding(
        self,
        tenant_id: int,
        body: FinishedGoodsReceiptPushBindingUpsert,
    ) -> FinishedGoodsReceiptPushBindingOut:
        from core.services.data.sync_binding_sources import (
            normalize_push_targets_json,
        )

        row = await FinishedGoodsReceiptSyncBinding.filter(tenant_id=tenant_id).first()
        if not row:
            row = await FinishedGoodsReceiptSyncBinding.create(tenant_id=tenant_id)
        targets = normalize_push_targets_json(
            [item.model_dump(mode="json") for item in body.targets]
        )
        triggers = [
            str(action).strip().lower() for action in body.trigger_actions if str(action).strip()
        ]
        await FinishedGoodsReceiptSyncBinding.filter(id=row.id).update(
            push_targets=targets,
            trigger_actions=triggers,
        )
        fresh = await FinishedGoodsReceiptSyncBinding.get(id=row.id)
        return self.serialize_push_binding(fresh)


finished_goods_receipt_sync_service = FinishedGoodsReceiptSyncService()
