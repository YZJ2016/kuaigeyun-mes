"""生产领料单出站绑定服务（本阶段仅 push-binding，无入站同步）。"""

from __future__ import annotations

from typing import Optional

from apps.kuaizhizao.models.production_picking_sync_binding import ProductionPickingSyncBinding
from apps.kuaizhizao.schemas.production_picking_sync import (
    ProductionPickingPushBindingOut,
    ProductionPickingPushBindingUpsert,
)


class ProductionPickingSyncService:
    def serialize_push_binding(
        self, row: Optional[ProductionPickingSyncBinding]
    ) -> ProductionPickingPushBindingOut:
        from core.schemas.sync_binding_contract import DocumentPushTargetItem
        from apps.kuaiconnect.services.inbound_sync.sync_binding_sources import (
            push_targets_from_row,
            trigger_actions_from_row,
        )

        if not row or not isinstance(getattr(row, "push_targets", None), list):
            return ProductionPickingPushBindingOut()
        stored = [DocumentPushTargetItem.model_validate(item) for item in push_targets_from_row(row)]
        targets = [item for item in stored if item.user_saved]
        first = targets[0] if targets else None
        return ProductionPickingPushBindingOut(
            targets=targets,
            trigger_actions=trigger_actions_from_row(row) if targets else [],
            connection_code=first.connection_code if first else None,
            save_api_uuid=first.save_api_uuid if first else None,
            sync_mode=str(getattr(row, "sync_mode", None) or "manual_full"),
            schedule_interval_minutes=int(getattr(row, "schedule_interval_minutes", None) or 15),
            targets_configured=True,
        )

    async def get_push_binding(self, tenant_id: int) -> ProductionPickingPushBindingOut:
        row = await ProductionPickingSyncBinding.filter(tenant_id=tenant_id).first()
        out = self.serialize_push_binding(row)
        if (
            row
            and isinstance(getattr(row, "push_targets", None), list)
            and out.targets_configured
            and not out.targets
            and getattr(row, "push_targets", None)
        ):
            await ProductionPickingSyncBinding.filter(id=row.id).update(
                push_targets=[], trigger_actions=[]
            )
        return out

    async def upsert_push_binding(
        self,
        tenant_id: int,
        body: ProductionPickingPushBindingUpsert,
    ) -> ProductionPickingPushBindingOut:
        from apps.kuaiconnect.services.inbound_sync.sync_binding_sources import (
            normalize_push_targets_json,
        )

        row = await ProductionPickingSyncBinding.filter(tenant_id=tenant_id).first()
        if not row:
            row = await ProductionPickingSyncBinding.create(tenant_id=tenant_id)
        targets = normalize_push_targets_json(
            [item.model_dump(mode="json") for item in body.targets]
        )
        triggers = [
            str(action).strip().lower() for action in body.trigger_actions if str(action).strip()
        ]
        await ProductionPickingSyncBinding.filter(id=row.id).update(
            push_targets=targets,
            trigger_actions=triggers,
        )
        fresh = await ProductionPickingSyncBinding.get(id=row.id)
        return self.serialize_push_binding(fresh)


production_picking_sync_service = ProductionPickingSyncService()
