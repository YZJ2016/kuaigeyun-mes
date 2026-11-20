"""审核动作成功后的无感外推（读绑定 push_targets + trigger_actions）。"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_ENTITY_SOURCE_TYPE: Dict[str, str] = {
    "sales_order": "sales_order",
    "purchase_order": "purchase_order",
    "purchase_receipt": "purchase_receipt",
    "sales_delivery": "sales_delivery",
    "finished_goods_receipt": "finished_goods_receipt",
    "production_picking": "production_picking",
    "other_outbound": "other_outbound",
    "other_inbound": "other_inbound",
    "work_order": "work_order",
    "reporting_record": "reporting_record",
    "material_batch": "material_batch",
}


async def _load_binding_row(entity_type: str, tenant_id: int) -> Optional[Any]:
    source_type = _ENTITY_SOURCE_TYPE.get(entity_type)
    if not source_type:
        return None
    if source_type == "sales_order":
        from apps.kuaizhizao.models.sales_order_sync_binding import SalesOrderSyncBinding

        return await SalesOrderSyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "purchase_order":
        from apps.kuaizhizao.models.purchase_order_sync_binding import PurchaseOrderSyncBinding

        return await PurchaseOrderSyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "purchase_receipt":
        from apps.kuaizhizao.models.purchase_receipt_sync_binding import PurchaseReceiptSyncBinding

        return await PurchaseReceiptSyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "sales_delivery":
        from apps.kuaizhizao.models.sales_delivery_sync_binding import SalesDeliverySyncBinding

        return await SalesDeliverySyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "finished_goods_receipt":
        from apps.kuaizhizao.models.finished_goods_receipt_sync_binding import (
            FinishedGoodsReceiptSyncBinding,
        )

        return await FinishedGoodsReceiptSyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "production_picking":
        from apps.kuaizhizao.models.production_picking_sync_binding import (
            ProductionPickingSyncBinding,
        )

        return await ProductionPickingSyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "other_outbound":
        from apps.kuaizhizao.models.other_outbound_sync_binding import OtherOutboundSyncBinding

        return await OtherOutboundSyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "other_inbound":
        from apps.kuaizhizao.models.other_inbound_sync_binding import OtherInboundSyncBinding

        return await OtherInboundSyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "work_order":
        from apps.kuaizhizao.models.work_order_sync_binding import WorkOrderSyncBinding

        return await WorkOrderSyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "reporting_record":
        from apps.kuaizhizao.models.reporting_sync_binding import ReportingSyncBinding

        return await ReportingSyncBinding.filter(tenant_id=tenant_id).first()
    if source_type == "material_batch":
        from apps.kuaizhizao.models.inventory_sync_binding import InventorySyncBinding

        return await InventorySyncBinding.filter(tenant_id=tenant_id).first()
    return None


def _push_failure_text(result: Any) -> Optional[str]:
    if not isinstance(result, dict) or result.get("success") is not False:
        return None
    parts: List[str] = []
    details = result.get("results")
    if isinstance(details, list):
        for one in details:
            if isinstance(one, dict) and one.get("success") is False:
                msg = str(one.get("message") or "").strip()
                if msg:
                    parts.append(msg)
    if not parts:
        msg = str(result.get("message") or "").strip()
        if msg:
            parts.append(msg)
    text = "；".join(parts).strip()
    return text or None


def _normalize_push_targets_readonly(
    entity_type: str,
    row: Any,
) -> tuple[List[str], List[Dict[str, Any]]]:
    from core.services.data.sync_binding_sources import (
        normalize_push_targets_json,
        push_targets_from_row,
        trigger_actions_from_row,
    )

    triggers = trigger_actions_from_row(row)
    raw_targets = getattr(row, "push_targets", None)
    if entity_type in (
        "purchase_order",
        "purchase_receipt",
        "sales_delivery",
        "finished_goods_receipt",
        "production_picking",
        "other_outbound",
        "other_inbound",
    ) and isinstance(raw_targets, list):
        kept = [item for item in raw_targets if isinstance(item, dict) and item.get("user_saved") is True]
        targets = normalize_push_targets_json(kept)
    else:
        targets = push_targets_from_row(row)
    return triggers, targets


def _target_would_auto_push_on_action(
    target: Dict[str, Any],
    *,
    act: str,
    binding_triggers: List[str],
) -> bool:
    profile = str(target.get("target_profile") or "").strip()
    if not profile:
        return False
    if target.get("push_enabled") is False:
        return False
    mode = str(target.get("push_mode") or "auto").strip()
    if mode == "manual":
        return False
    owned = target.get("trigger_actions")
    if isinstance(owned, list) and owned:
        owned_actions = [str(item).strip().lower() for item in owned if str(item or "").strip()]
        return act in owned_actions
    return bool(binding_triggers and act in binding_triggers)


async def silent_push_would_run_on_confirm(tenant_id: int, entity_type: str) -> bool:
    """只读：确认动作是否会触发至少一次自动无感外推（与 maybe_silent_push 门禁一致，不写库）。"""
    act = "confirm"
    if not _ENTITY_SOURCE_TYPE.get(entity_type):
        return False
    row = await _load_binding_row(entity_type, tenant_id)
    if not row:
        return False
    triggers, targets = _normalize_push_targets_readonly(entity_type, row)
    if act not in triggers or not targets:
        return False
    from apps.common.optional_pro import pro_orm_ready

    if not pro_orm_ready("kuaiconnect"):
        return False
    for target in targets:
        if _target_would_auto_push_on_action(target, act=act, binding_triggers=triggers):
            return True
    return False


async def maybe_silent_push_after_audit(
    *,
    tenant_id: int,
    user_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
) -> Optional[str]:
    act = str(action or "").strip().lower()
    source_type = _ENTITY_SOURCE_TYPE.get(entity_type)
    if not source_type or int(entity_id or 0) <= 0:
        return

    row = await _load_binding_row(entity_type, tenant_id)
    if not row:
        return
    triggers, targets = _normalize_push_targets_readonly(entity_type, row)
    if act not in triggers:
        return
    raw_targets = getattr(row, "push_targets", None)
    if entity_type in (
        "purchase_order",
        "purchase_receipt",
        "sales_delivery",
        "finished_goods_receipt",
        "production_picking",
        "other_outbound",
        "other_inbound",
    ) and isinstance(
        raw_targets, list
    ):
        kept = [item for item in raw_targets if isinstance(item, dict) and item.get("user_saved") is True]
        if len(kept) != len(raw_targets):
            if entity_type == "purchase_order":
                from apps.kuaizhizao.models.purchase_order_sync_binding import PurchaseOrderSyncBinding

                await PurchaseOrderSyncBinding.filter(id=row.id).update(
                    push_targets=kept,
                    trigger_actions=triggers if kept else [],
                )
            elif entity_type == "purchase_receipt":
                from apps.kuaizhizao.models.purchase_receipt_sync_binding import (
                    PurchaseReceiptSyncBinding,
                )

                await PurchaseReceiptSyncBinding.filter(id=row.id).update(
                    push_targets=kept,
                    trigger_actions=triggers if kept else [],
                )
            elif entity_type == "sales_delivery":
                from apps.kuaizhizao.models.sales_delivery_sync_binding import (
                    SalesDeliverySyncBinding,
                )

                await SalesDeliverySyncBinding.filter(id=row.id).update(
                    push_targets=kept,
                    trigger_actions=triggers if kept else [],
                )
            elif entity_type == "finished_goods_receipt":
                from apps.kuaizhizao.models.finished_goods_receipt_sync_binding import (
                    FinishedGoodsReceiptSyncBinding,
                )

                await FinishedGoodsReceiptSyncBinding.filter(id=row.id).update(
                    push_targets=kept,
                    trigger_actions=triggers if kept else [],
                )
            elif entity_type == "production_picking":
                from apps.kuaizhizao.models.production_picking_sync_binding import (
                    ProductionPickingSyncBinding,
                )

                await ProductionPickingSyncBinding.filter(id=row.id).update(
                    push_targets=kept,
                    trigger_actions=triggers if kept else [],
                )
            elif entity_type == "other_outbound":
                from apps.kuaizhizao.models.other_outbound_sync_binding import (
                    OtherOutboundSyncBinding,
                )

                await OtherOutboundSyncBinding.filter(id=row.id).update(
                    push_targets=kept,
                    trigger_actions=triggers if kept else [],
                )
            elif entity_type == "other_inbound":
                from apps.kuaizhizao.models.other_inbound_sync_binding import (
                    OtherInboundSyncBinding,
                )

                await OtherInboundSyncBinding.filter(id=row.id).update(
                    push_targets=kept,
                    trigger_actions=triggers if kept else [],
                )
        triggers, targets = _normalize_push_targets_readonly(entity_type, row)
    if not targets:
        return

    from apps.common.optional_pro import pro_orm_ready

    if not pro_orm_ready("kuaiconnect"):
        logger.info(
            "无感外推跳过：快连接未就绪 tenant_id={} entity_type={} entity_id={}",
            tenant_id,
            entity_type,
            entity_id,
        )
        return

    from apps.common.document_push_gate import document_push_service
    from core.services.data.sync_trigger_kind import (
        SYNC_TRIGGER_KIND_TRIGGER,
        sync_run_trigger_kind,
    )

    svc = document_push_service()
    failures: List[str] = []
    with sync_run_trigger_kind(SYNC_TRIGGER_KIND_TRIGGER):
        for target in targets:
            if not _target_would_auto_push_on_action(target, act=act, binding_triggers=triggers):
                continue
            profile = str(target.get("target_profile") or "").strip()
            try:
                result = await svc.push(
                    tenant_id=tenant_id,
                    acting_user_id=int(user_id),
                    source_type=source_type,
                    source_id=int(entity_id),
                    targets=[target],
                    dry_run=False,
                )
                failure = _push_failure_text(result)
                if failure:
                    logger.warning(
                        "无感外推失败 tenant_id={} entity_type={} entity_id={} profile={} err={}",
                        tenant_id,
                        entity_type,
                        entity_id,
                        profile,
                        failure,
                    )
                    failures.append(failure)
            except Exception as exc:
                logger.warning(
                    "无感外推失败 tenant_id={} entity_type={} entity_id={} profile={} err={}",
                    tenant_id,
                    entity_type,
                    entity_id,
                    profile,
                    exc,
                )
                failures.append(str(exc))
    if not failures:
        return None
    return "；".join(failures)


async def require_silent_push_after_confirm_or_rollback(
    *,
    tenant_id: int,
    user_id: int,
    entity_type: str,
    entity_id: int,
    withdraw_local: Callable[[], Awaitable[None]],
    rollback_action_label: str,
) -> None:
    """有绑定且 confirm 触发外推时：推送失败则撤回本地过账并抛错（无绑定/未触发外推则无操作）。"""
    from infra.exceptions.exceptions import BusinessLogicError

    try:
        push_error = await maybe_silent_push_after_audit(
            tenant_id=tenant_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action="confirm",
        )
    except Exception as push_exc:
        logger.warning(
            "确认后无感外推异常 entity_type=%s entity_id=%s: %s",
            entity_type,
            entity_id,
            push_exc,
        )
        push_error = str(push_exc).strip() or push_exc.__class__.__name__
    if not push_error:
        return
    label = str(rollback_action_label or "").strip() or "过账"
    try:
        await withdraw_local()
    except Exception as compensate_exc:
        raise BusinessLogicError(
            f"推送金蝶失败：{push_error}；撤回本地{label}亦失败：{compensate_exc}"
        ) from compensate_exc
    raise BusinessLogicError(f"推送金蝶失败，已撤回本地{label}：{push_error}")
