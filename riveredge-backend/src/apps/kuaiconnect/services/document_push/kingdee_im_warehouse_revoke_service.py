"""仓储 im_* 外推单：撤回/删除时苍穹 batchUnaudit / batchUnsubmit / batchDelete（与采购入库同一套逻辑）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Type

from loguru import logger
from tortoise import Model

from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.finished_goods_receipt_sync_binding import (
    FinishedGoodsReceiptSyncBinding,
)
from apps.kuaizhizao.models.other_inbound_sync_binding import OtherInboundSyncBinding
from apps.kuaizhizao.models.other_outbound_sync_binding import OtherOutboundSyncBinding
from apps.kuaizhizao.models.production_picking_sync_binding import ProductionPickingSyncBinding
from apps.kuaizhizao.models.sales_delivery_sync_binding import SalesDeliverySyncBinding
from core.services.integration.document_push_pipeline import DocumentPushPipeline
from core.services.integration.kingdee_cosmic_api_presets import (
    BIZ_IM_OTHERINBILL,
    BIZ_IM_OTHEROUTBILL,
    BIZ_IM_SALOUTBILL,
    IM_OTHERINBILL_BATCH_DELETE_PATH,
    IM_OTHERINBILL_BATCH_UNAUDIT_PATH,
    IM_OTHERINBILL_BATCH_UNSUBMIT_PATH,
    IM_OTHEROUTBILL_BATCH_DELETE_PATH,
    IM_OTHEROUTBILL_BATCH_UNAUDIT_PATH,
    IM_OTHEROUTBILL_BATCH_UNSUBMIT_PATH,
    IM_SALOUTBILL_BATCH_AUDIT_PATH,
    IM_SALOUTBILL_BATCH_DELETE_PATH,
    IM_SALOUTBILL_BATCH_SUBMIT_PATH,
    IM_SALOUTBILL_BATCH_UNAUDIT_PATH,
    IM_SALOUTBILL_BATCH_UNSUBMIT_PATH,
)
from core.services.integration.kingdee_warehouse_document_push_config import (
    attach_im_operate_apis_from_save_binding,
    enrich_kingdee_warehouse_push_config,
    finalize_kingdee_warehouse_im_push_config,
    merge_warehouse_kingdee_push_config,
    read_kingdee_push_workflow_bool,
    validate_im_operate_api_path,
)
from core.services.integration.kingdee_cosmic_response_status import (
    is_cosmic_batch_unsubmit_http_404,
)
from infra.exceptions.exceptions import BusinessLogicError
from infra.services.business_config_service import BusinessConfigService

ConfigLoader = Callable[[int, int], Awaitable[Dict[str, Any]]]

_OPERATE_SLOTS: Dict[str, Tuple[str, str]] = {
    "withdraw": ("unaudit_path", "unaudit_api_uuid"),
    "unsubmit": ("unsubmit_path", "unsubmit_api_uuid"),
    "delete": ("delete_path", "delete_api_uuid"),
}

_OPERATE_SLOT_LABELS: Dict[str, str] = {
    "withdraw": "反审核",
    "unsubmit": "撤销提交",
    "delete": "删除",
}


@dataclass(frozen=True)
class KingdeeImWarehouseRevokeSpec:
    doc_label: str
    source_type: str
    target_type: str
    form_id: str
    warehouse_config_key: str
    binding_model: Type[Model]
    default_unaudit_path: str
    default_unsubmit_path: str
    default_delete_path: str
    default_submit_path: str
    default_audit_path: str
    config_loader: Optional[ConfigLoader] = None


def _action_apis_from_targets(targets: List[Dict[str, Any]]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for row in targets:
        if not isinstance(row, dict):
            continue
        raw = row.get("action_apis")
        if not isinstance(raw, dict):
            continue
        for key, val in raw.items():
            slot = str(key or "").strip()
            uuid = str(val or "").strip()
            if slot and uuid:
                merged[slot] = uuid
    return merged


async def _default_warehouse_config(tenant_id: int, config_key: str) -> Dict[str, Any]:
    biz_config = await BusinessConfigService().get_business_config(tenant_id)
    warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
    return merge_warehouse_kingdee_push_config(warehouse, config_key)


async def _load_binding_context(
    tenant_id: int,
    spec: KingdeeImWarehouseRevokeSpec,
    *,
    source_id: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    if spec.config_loader:
        config = await spec.config_loader(tenant_id, source_id)
    else:
        config = await _default_warehouse_config(tenant_id, spec.warehouse_config_key)
    config = await enrich_kingdee_warehouse_push_config(tenant_id, config)
    config = await attach_im_operate_apis_from_save_binding(
        tenant_id, config, im_bill=spec.form_id
    )
    row = await spec.binding_model.filter(tenant_id=tenant_id).first()
    targets: List[Dict[str, Any]] = []
    if row and isinstance(getattr(row, "push_targets", None), list):
        from apps.kuaiconnect.services.inbound_sync.sync_binding_sources import (
            push_targets_from_row,
        )

        targets = [
            item
            for item in push_targets_from_row(row)
            if isinstance(item, dict) and item.get("user_saved") is True
        ]
        for item in targets:
            if str(item.get("connection_code") or "").strip():
                config["connection_code"] = str(item.get("connection_code")).strip()
    action_apis = _action_apis_from_targets(targets)
    confirm_uuid = str(action_apis.get("confirm") or "").strip()
    if confirm_uuid:
        config["save_api_uuid"] = confirm_uuid
    else:
        for item in targets:
            row_apis = item.get("action_apis") if isinstance(item.get("action_apis"), dict) else {}
            row_confirm = str((row_apis or {}).get("confirm") or "").strip()
            if row_confirm:
                config["save_api_uuid"] = row_confirm
                break
            if row_apis:
                continue
            legacy_save = str(item.get("save_api_uuid") or "").strip()
            if legacy_save:
                config["save_api_uuid"] = legacy_save
                break
    config = finalize_kingdee_warehouse_im_push_config(
        config,
        default_submit_path=spec.default_submit_path,
        default_audit_path=spec.default_audit_path,
    )
    if spec.warehouse_config_key == "kingdee_sales_delivery_push":
        config.setdefault("body_wrap", "data_list")
    elif spec.warehouse_config_key in (
        "kingdee_other_outbound_push",
        "kingdee_other_inbound_push",
        "kingdee_production_picking_push",
        "kingdee_finished_goods_receipt_push",
    ):
        config.setdefault("body_wrap", "data_list")
    return targets, action_apis, config


def _explicit_operate_api_bound(
    action_apis: Dict[str, str],
    config: Dict[str, Any],
    slot: str,
) -> bool:
    _, uuid_key = _OPERATE_SLOTS[slot]
    if str(action_apis.get(slot) or "").strip():
        return True
    return bool(str(config.get(uuid_key) or "").strip())


async def _resolve_operate(
    tenant_id: int,
    *,
    spec: KingdeeImWarehouseRevokeSpec,
    config: Dict[str, Any],
    action_apis: Dict[str, str],
    slot: str,
) -> Tuple[str, Optional[str]]:
    path_key, uuid_key = _OPERATE_SLOTS[slot]
    api_uuid = str(action_apis.get(slot) or config.get(uuid_key) or "").strip() or None
    if api_uuid:
        from core.models.api import API

        api = await API.filter(tenant_id=tenant_id, uuid=api_uuid, deleted_at=None).first()
        if not api or not str(api.path or "").strip():
            raise BusinessLogicError(
                f"金蝶{spec.doc_label}{slot} 绑定的接口不存在: {api_uuid}"
            )
        path = str(api.path).strip()
        validate_im_operate_api_path(path, slot, doc_label=spec.doc_label)
        return path, api_uuid
    default_paths = {
        "withdraw": spec.default_unaudit_path,
        "unsubmit": spec.default_unsubmit_path,
        "delete": spec.default_delete_path,
    }
    path = str(config.get(path_key) or default_paths.get(slot) or "").strip()
    if not path:
        raise BusinessLogicError(f"金蝶{spec.doc_label}缺少 {slot} 接口配置")
    validate_im_operate_api_path(path, slot, doc_label=spec.doc_label)
    return path, api_uuid


async def _operate_chain(
    *,
    tenant_id: int,
    spec: KingdeeImWarehouseRevokeSpec,
    config: Dict[str, Any],
    action_apis: Dict[str, str],
    bill_id: int,
    bill_no: str,
    slots: List[str],
    source_id: int = 0,
) -> None:
    pipeline = DocumentPushPipeline()
    anchor = str(config.get("save_api_uuid") or "").strip() or None
    form_id = str(config.get("form_id") or spec.form_id).strip() or spec.form_id
    for slot in slots:
        label = _OPERATE_SLOT_LABELS.get(slot, slot)
        path, api_uuid = await _resolve_operate(
            tenant_id,
            spec=spec,
            config=config,
            action_apis=action_apis,
            slot=slot,
        )
        try:
            await pipeline.cosmic_im_operate_only(
                tenant_id=tenant_id,
                connector_type="kingdee_cosmic",
                config=config,
                form_id=form_id,
                path=path,
                bill_id=bill_id,
                bill_no=bill_no,
                operate_api_uuid=api_uuid,
                anchor_save_api_uuid=anchor,
                operate_slot=slot,
                source_type=spec.source_type,
                source_id=int(source_id or 0),
                target_profile=spec.target_type,
            )
        except BusinessLogicError as exc:
            wrapped = f"金蝶{spec.doc_label}{label}失败：{exc}"
            detail_text = str(exc)
            if slot == "unsubmit" and is_cosmic_batch_unsubmit_http_404(exc):
                logger.warning(
                    "{}撤回跳过苍穹 batchUnsubmit（HTTP 404）：bill_no={} detail={}",
                    spec.doc_label,
                    bill_no,
                    wrapped,
                )
                continue
            # 暂存/已删时撤销提交会报「必须是已提交」或未找到——跳过继续删单
            if slot == "unsubmit" and (
                "必须是已提交" in detail_text
                or "已提交才能撤销" in detail_text
                or "未查找" in detail_text
                or "未找到" in detail_text
                or "不存在" in detail_text
            ):
                logger.warning(
                    "{}撤回跳过苍穹 batchUnsubmit：bill_no={} detail={}",
                    spec.doc_label,
                    bill_no,
                    wrapped,
                )
                continue
            if slot == "withdraw" and (
                "必须是已审核" in detail_text
                or "已审核才能" in detail_text
                or "不存在" in detail_text
                or "未查找" in detail_text
                or "unaudit" in detail_text.lower()
            ):
                logger.warning(
                    "{}撤回跳过苍穹 batchUnaudit：bill_no={} detail={}",
                    spec.doc_label,
                    bill_no,
                    wrapped,
                )
                continue
            if slot == "delete" and (
                "不存在" in detail_text
                or "未找到" in detail_text
                or "未查找" in detail_text
                or "已删除" in detail_text
            ):
                logger.warning(
                    "{}撤回跳过苍穹 batchDelete（远程已无单）：bill_no={} detail={}",
                    spec.doc_label,
                    bill_no,
                    wrapped,
                )
                continue
            raise BusinessLogicError(wrapped) from exc


async def _relation(
    tenant_id: int, spec: KingdeeImWarehouseRevokeSpec, source_id: int
) -> Optional[DocumentRelation]:
    return await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type=spec.source_type,
        source_id=source_id,
        target_type=spec.target_type,
    ).first()


async def _resolve_revoke_slots(
    *,
    tenant_id: int,
    spec: KingdeeImWarehouseRevokeSpec,
    config: Dict[str, Any],
    bill_id: int,
    bill_no: str,
) -> Tuple[List[str], int]:
    """按金蝶 billstatus 编排撤回/删除链；查不到状态时走全链。成功时也可回填 bill_id。"""
    form_id = str(config.get("form_id") or spec.form_id).strip() or spec.form_id
    resolved_id = int(bill_id or 0)
    billstatus = ""
    if bill_no:
        try:
            from core.services.integration.kingdee_cosmic_push_adapter import (
                kingdee_im_revoke_slots_for_billstatus,
                normalize_kingdee_im_billstatus,
                query_kingdee_cosmic_bill_by_billno,
            )

            connection = await DocumentPushPipeline()._resolve_connection(
                tenant_id,
                connector_type="kingdee_cosmic",
                config=config,
            )
            row = await query_kingdee_cosmic_bill_by_billno(
                connection, form_id=form_id, bill_no=bill_no
            )
            if row is None:
                # 远程已无单：仅走 delete（软跳过）以便清关联
                return (["delete"], resolved_id)
            billstatus = normalize_kingdee_im_billstatus(row.get("billstatus"))
            raw_id = row.get("id")
            try:
                queried_id = int(str(raw_id).strip())
            except (TypeError, ValueError):
                queried_id = 0
            if queried_id > 0:
                resolved_id = queried_id
            return (
                kingdee_im_revoke_slots_for_billstatus(
                    billstatus, include_delete=True
                ),
                resolved_id,
            )
        except Exception as exc:
            logger.warning(
                "{}撤回前 query 状态失败，回退全链 bill_no={} err={}",
                spec.doc_label,
                bill_no,
                exc,
            )
    return (["withdraw", "unsubmit", "delete"], resolved_id)


async def sync_im_warehouse_kingdee_after_withdraw(
    spec: KingdeeImWarehouseRevokeSpec,
    tenant_id: int,
    source_id: int,
    *,
    acting_user_id: int,
) -> Optional[str]:
    """撤回过账：反审→撤销提交→删除远程并清关联（与采购入库强一致）。"""
    _ = acting_user_id
    relation = await _relation(tenant_id, spec, source_id)
    if not relation:
        return None
    _, action_apis, config = await _load_binding_context(
        tenant_id, spec, source_id=source_id
    )
    bill_id = int(relation.target_id or 0)
    bill_no = str(relation.target_code or "").strip()
    withdraw_slots, bill_id = await _resolve_revoke_slots(
        tenant_id=tenant_id,
        spec=spec,
        config=config,
        bill_id=bill_id,
        bill_no=bill_no,
    )
    if not _explicit_operate_api_bound(action_apis, config, "unsubmit"):
        logger.info(
            "{}撤回未绑定 batchUnsubmit，将使用默认路径 bill_no={}",
            spec.doc_label,
            bill_no,
        )
    blocks_local = read_kingdee_push_workflow_bool(
        config, "remote_withdraw_blocks_local", default=True
    )
    from core.services.data.sync_trigger_kind import (
        SYNC_TRIGGER_KIND_TRIGGER,
        sync_run_trigger_kind,
    )

    try:
        with sync_run_trigger_kind(SYNC_TRIGGER_KIND_TRIGGER):
            await _operate_chain(
                tenant_id=tenant_id,
                spec=spec,
                config=config,
                action_apis=action_apis,
                bill_id=bill_id,
                bill_no=bill_no,
                slots=withdraw_slots,
                source_id=source_id,
            )
        await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=spec.source_type,
            source_id=source_id,
            target_type=spec.target_type,
        ).delete()
    except Exception as exc:
        detail = str(exc).strip() or "金蝶苍穹撤回同步失败"
        logger.warning(
            "{}撤回同步苍穹失败 tenant_id={} source_id={} blocks_local={} err={}",
            spec.doc_label,
            tenant_id,
            source_id,
            blocks_local,
            detail,
        )
        if blocks_local:
            raise BusinessLogicError(detail) from exc
        return f"金蝶撤回未完全成功（本地将继续撤回）：{detail}"
    return None


async def sync_im_warehouse_kingdee_after_delete(
    spec: KingdeeImWarehouseRevokeSpec,
    tenant_id: int,
    source_id: int,
    *,
    acting_user_id: int,
) -> None:
    _ = acting_user_id
    relation = await _relation(tenant_id, spec, source_id)
    if not relation:
        return
    _, action_apis, config = await _load_binding_context(
        tenant_id, spec, source_id=source_id
    )
    bill_id = int(relation.target_id or 0)
    bill_no = str(relation.target_code or "").strip()
    delete_slots, bill_id = await _resolve_revoke_slots(
        tenant_id=tenant_id,
        spec=spec,
        config=config,
        bill_id=bill_id,
        bill_no=bill_no,
    )
    from core.services.data.sync_trigger_kind import (
        SYNC_TRIGGER_KIND_TRIGGER,
        sync_run_trigger_kind,
    )

    try:
        with sync_run_trigger_kind(SYNC_TRIGGER_KIND_TRIGGER):
            await _operate_chain(
                tenant_id=tenant_id,
                spec=spec,
                config=config,
                action_apis=action_apis,
                bill_id=bill_id,
                bill_no=bill_no,
                slots=delete_slots,
                source_id=source_id,
            )
    except Exception as exc:
        logger.warning(
            "{}删除同步苍穹失败 tenant_id={} source_id={} err={}",
            spec.doc_label,
            tenant_id,
            source_id,
            exc,
        )
        raise BusinessLogicError(f"金蝶{spec.doc_label}删除失败：{exc}") from exc
    await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type=spec.source_type,
        source_id=source_id,
        target_type=spec.target_type,
    ).delete()


async def _config_production_picking(tenant_id: int, _source_id: int) -> Dict[str, Any]:
    from core.services.integration.kingdee_warehouse_push_routing import (
        resolve_production_picking_push_config,
    )

    biz_config = await BusinessConfigService().get_business_config(tenant_id)
    warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
    return resolve_production_picking_push_config(warehouse)


async def _config_other_outbound(tenant_id: int, source_id: int) -> Dict[str, Any]:
    from apps.kuaizhizao.models.other_outbound_item import OtherOutboundItem
    from core.services.integration.kingdee_warehouse_push_routing import (
        resolve_other_outbound_push_config,
    )

    from apps.kuaizhizao.models.other_outbound import OtherOutbound

    biz_config = await BusinessConfigService().get_business_config(tenant_id)
    warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
    material_ids: List[int] = []
    outbound_type: Optional[str] = None
    if source_id > 0:
        outbound = await OtherOutbound.get_or_none(
            tenant_id=tenant_id, id=source_id, deleted_at__isnull=True
        )
        if outbound is not None:
            outbound_type = getattr(outbound, "outbound_type", None)
        items = await OtherOutboundItem.filter(
            tenant_id=tenant_id, outbound_id=source_id
        ).all()
        material_ids = [
            int(it.material_id) for it in items if getattr(it, "material_id", None)
        ]
    return await resolve_other_outbound_push_config(
        tenant_id,
        warehouse,
        material_ids=material_ids,
        outbound_type=outbound_type,
    )


async def _config_finished_goods(tenant_id: int, _source_id: int) -> Dict[str, Any]:
    from core.services.integration.kingdee_warehouse_push_routing import (
        resolve_finished_goods_push_config,
    )

    biz_config = await BusinessConfigService().get_business_config(tenant_id)
    warehouse = (biz_config.get("parameters", {}) or {}).get("warehouse", {}) or {}
    return resolve_finished_goods_push_config(warehouse)


SALES_DELIVERY_REVOKE_SPEC = KingdeeImWarehouseRevokeSpec(
    doc_label="销售出库",
    source_type="sales_delivery",
    target_type="kingdee_im_saloutbill",
    form_id=BIZ_IM_SALOUTBILL,
    warehouse_config_key="kingdee_sales_delivery_push",
    binding_model=SalesDeliverySyncBinding,
    default_unaudit_path=IM_SALOUTBILL_BATCH_UNAUDIT_PATH,
    default_unsubmit_path=IM_SALOUTBILL_BATCH_UNSUBMIT_PATH,
    default_delete_path=IM_SALOUTBILL_BATCH_DELETE_PATH,
    default_submit_path=IM_SALOUTBILL_BATCH_SUBMIT_PATH,
    default_audit_path=IM_SALOUTBILL_BATCH_AUDIT_PATH,
)

OTHER_OUTBOUND_REVOKE_SPEC = KingdeeImWarehouseRevokeSpec(
    doc_label="其他出库",
    source_type="other_outbound",
    target_type="kingdee_im_otheroutbill",
    form_id=BIZ_IM_OTHEROUTBILL,
    warehouse_config_key="kingdee_other_outbound_push",
    binding_model=OtherOutboundSyncBinding,
    default_unaudit_path=IM_OTHEROUTBILL_BATCH_UNAUDIT_PATH,
    default_unsubmit_path=IM_OTHEROUTBILL_BATCH_UNSUBMIT_PATH,
    default_delete_path=IM_OTHEROUTBILL_BATCH_DELETE_PATH,
    default_submit_path="kapi/v2/im/im_otheroutbill/batchSubmit",
    default_audit_path="kapi/v2/im/im_otheroutbill/billbatchAudit",
    config_loader=_config_other_outbound,
)

OTHER_INBOUND_REVOKE_SPEC = KingdeeImWarehouseRevokeSpec(
    doc_label="其他入库",
    source_type="other_inbound",
    target_type="kingdee_im_otherinbill",
    form_id=BIZ_IM_OTHERINBILL,
    warehouse_config_key="kingdee_other_inbound_push",
    binding_model=OtherInboundSyncBinding,
    default_unaudit_path=IM_OTHERINBILL_BATCH_UNAUDIT_PATH,
    default_unsubmit_path=IM_OTHERINBILL_BATCH_UNSUBMIT_PATH,
    default_delete_path=IM_OTHERINBILL_BATCH_DELETE_PATH,
    default_submit_path="kapi/v2/im/im_otherinbill/batchSubmit",
    default_audit_path="kapi/v2/im/im_otherinbill/billbatchAudit",
)

PRODUCTION_PICKING_REVOKE_SPEC = KingdeeImWarehouseRevokeSpec(
    doc_label="生产领料",
    source_type="production_picking",
    target_type="kingdee_im_otheroutbill",
    form_id=BIZ_IM_OTHEROUTBILL,
    warehouse_config_key="kingdee_production_picking_push",
    binding_model=ProductionPickingSyncBinding,
    default_unaudit_path=IM_OTHEROUTBILL_BATCH_UNAUDIT_PATH,
    default_unsubmit_path=IM_OTHEROUTBILL_BATCH_UNSUBMIT_PATH,
    default_delete_path=IM_OTHEROUTBILL_BATCH_DELETE_PATH,
    default_submit_path="kapi/v2/im/im_otheroutbill/batchSubmit",
    default_audit_path="kapi/v2/im/im_otheroutbill/billbatchAudit",
    config_loader=_config_production_picking,
)

FINISHED_GOODS_RECEIPT_REVOKE_SPEC = KingdeeImWarehouseRevokeSpec(
    doc_label="成品入库",
    source_type="finished_goods_receipt",
    target_type="kingdee_im_otherinbill",
    form_id=BIZ_IM_OTHERINBILL,
    warehouse_config_key="kingdee_finished_goods_receipt_push",
    binding_model=FinishedGoodsReceiptSyncBinding,
    default_unaudit_path=IM_OTHERINBILL_BATCH_UNAUDIT_PATH,
    default_unsubmit_path=IM_OTHERINBILL_BATCH_UNSUBMIT_PATH,
    default_delete_path=IM_OTHERINBILL_BATCH_DELETE_PATH,
    default_submit_path="kapi/v2/im/im_otherinbill/batchSubmit",
    default_audit_path="kapi/v2/im/im_otherinbill/billbatchAudit",
    config_loader=_config_finished_goods,
)


async def sync_sales_delivery_kingdee_after_withdraw(
    tenant_id: int, delivery_id: int, *, acting_user_id: int
) -> Optional[str]:
    return await sync_im_warehouse_kingdee_after_withdraw(
        SALES_DELIVERY_REVOKE_SPEC, tenant_id, delivery_id, acting_user_id=acting_user_id
    )


async def sync_sales_delivery_kingdee_after_delete(
    tenant_id: int, delivery_id: int, *, acting_user_id: int
) -> None:
    await sync_im_warehouse_kingdee_after_delete(
        SALES_DELIVERY_REVOKE_SPEC, tenant_id, delivery_id, acting_user_id=acting_user_id
    )


async def sync_other_outbound_kingdee_after_withdraw(
    tenant_id: int, outbound_id: int, *, acting_user_id: int
) -> Optional[str]:
    return await sync_im_warehouse_kingdee_after_withdraw(
        OTHER_OUTBOUND_REVOKE_SPEC, tenant_id, outbound_id, acting_user_id=acting_user_id
    )


async def sync_other_outbound_kingdee_after_delete(
    tenant_id: int, outbound_id: int, *, acting_user_id: int
) -> None:
    await sync_im_warehouse_kingdee_after_delete(
        OTHER_OUTBOUND_REVOKE_SPEC, tenant_id, outbound_id, acting_user_id=acting_user_id
    )


async def sync_other_inbound_kingdee_after_withdraw(
    tenant_id: int, inbound_id: int, *, acting_user_id: int
) -> Optional[str]:
    return await sync_im_warehouse_kingdee_after_withdraw(
        OTHER_INBOUND_REVOKE_SPEC, tenant_id, inbound_id, acting_user_id=acting_user_id
    )


async def sync_other_inbound_kingdee_after_delete(
    tenant_id: int, inbound_id: int, *, acting_user_id: int
) -> None:
    await sync_im_warehouse_kingdee_after_delete(
        OTHER_INBOUND_REVOKE_SPEC, tenant_id, inbound_id, acting_user_id=acting_user_id
    )


async def sync_production_picking_kingdee_after_withdraw(
    tenant_id: int, picking_id: int, *, acting_user_id: int
) -> Optional[str]:
    return await sync_im_warehouse_kingdee_after_withdraw(
        PRODUCTION_PICKING_REVOKE_SPEC, tenant_id, picking_id, acting_user_id=acting_user_id
    )


async def sync_production_picking_kingdee_after_delete(
    tenant_id: int, picking_id: int, *, acting_user_id: int
) -> None:
    await sync_im_warehouse_kingdee_after_delete(
        PRODUCTION_PICKING_REVOKE_SPEC, tenant_id, picking_id, acting_user_id=acting_user_id
    )


async def sync_finished_goods_receipt_kingdee_after_withdraw(
    tenant_id: int, receipt_id: int, *, acting_user_id: int
) -> Optional[str]:
    return await sync_im_warehouse_kingdee_after_withdraw(
        FINISHED_GOODS_RECEIPT_REVOKE_SPEC,
        tenant_id,
        receipt_id,
        acting_user_id=acting_user_id,
    )


async def sync_finished_goods_receipt_kingdee_after_delete(
    tenant_id: int, receipt_id: int, *, acting_user_id: int
) -> None:
    await sync_im_warehouse_kingdee_after_delete(
        FINISHED_GOODS_RECEIPT_REVOKE_SPEC,
        tenant_id,
        receipt_id,
        acting_user_id=acting_user_id,
    )
