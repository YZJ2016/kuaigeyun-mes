"""采购入库单撤回/删除时同步金蝶苍穹反审核、撤销提交、删除。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from apps.kuaizhizao.services.kingdee_purchase_receipt_push_service import (
    DEFAULT_AUDIT_PATH,
    DEFAULT_FORM_ID,
    DEFAULT_SUBMIT_PATH,
    KingdeePurchaseReceiptPushService,
    TARGET_TYPE,
)
from apps.kuaizhizao.models.document_relation import DocumentRelation
from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
from apps.kuaizhizao.models.purchase_receipt_sync_binding import PurchaseReceiptSyncBinding
from infra.services.business_config_service import BusinessConfigService
from core.services.integration.document_push_pipeline import DocumentPushPipeline
from core.services.integration.kingdee_cosmic_api_presets import (
    IM_PURINBILL_BATCH_DELETE_PATH,
    IM_PURINBILL_BATCH_UNAUDIT_PATH,
    IM_PURINBILL_BATCH_UNSUBMIT_PATH,
)
from core.services.integration.kingdee_warehouse_document_push_config import (
    attach_im_operate_apis_from_save_binding,
    enrich_kingdee_warehouse_push_config,
    finalize_kingdee_warehouse_im_push_config,
    validate_im_operate_api_path,
)
from core.services.integration.kingdee_warehouse_push_routing import (
    resolve_purchase_receipt_push_config,
)
from infra.exceptions.exceptions import BusinessLogicError

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


async def _load_binding_context(
    tenant_id: int,
    *,
    receipt_id: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    push_svc = KingdeePurchaseReceiptPushService()
    receipt = await PurchaseReceipt.filter(
        tenant_id=tenant_id,
        id=receipt_id,
        deleted_at__isnull=True,
    ).first()
    if not receipt:
        config = await push_svc.get_push_config(tenant_id)
    else:
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
            material_ids=[
                int(it.material_id) for it in items if getattr(it, "material_id", None)
            ],
            order_type=getattr(receipt, "order_type", None),
        )
    config = await enrich_kingdee_warehouse_push_config(tenant_id, config)
    config = await attach_im_operate_apis_from_save_binding(
        tenant_id, config, im_bill=DEFAULT_FORM_ID
    )
    row = await PurchaseReceiptSyncBinding.filter(tenant_id=tenant_id).first()
    targets: List[Dict[str, Any]] = []
    if row and isinstance(getattr(row, "push_targets", None), list):
        from core.services.data.sync_binding_sources import (
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
        default_submit_path=DEFAULT_SUBMIT_PATH,
        default_audit_path=DEFAULT_AUDIT_PATH,
    )
    return targets, action_apis, config


def _explicit_operate_api_bound(
    action_apis: Dict[str, str],
    config: Dict[str, Any],
    slot: str,
) -> bool:
    """接口库已绑定 uuid（数据互通或 Save 同连接器 attach），非仅业务配置默认 path。"""
    _, uuid_key = _OPERATE_SLOTS[slot]
    if str(action_apis.get(slot) or "").strip():
        return True
    return bool(str(config.get(uuid_key) or "").strip())


async def _resolve_operate(
    tenant_id: int,
    *,
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
                f"金蝶采购入库{slot} 绑定的接口不存在: {api_uuid}"
            )
        path = str(api.path).strip()
        validate_im_operate_api_path(path, slot, doc_label="采购入库")
        return path, api_uuid
    default_paths = {
        "withdraw": IM_PURINBILL_BATCH_UNAUDIT_PATH,
        "unsubmit": IM_PURINBILL_BATCH_UNSUBMIT_PATH,
        "delete": IM_PURINBILL_BATCH_DELETE_PATH,
    }
    path = str(config.get(path_key) or default_paths.get(slot) or "").strip()
    if not path:
        raise BusinessLogicError(f"金蝶采购入库缺少 {slot} 接口配置")
    validate_im_operate_api_path(path, slot, doc_label="采购入库")
    return path, api_uuid


async def _operate_chain(
    *,
    tenant_id: int,
    config: Dict[str, Any],
    action_apis: Dict[str, str],
    form_id: str,
    bill_id: int,
    bill_no: str,
    slots: List[str],
    source_id: int = 0,
) -> None:
    pipeline = DocumentPushPipeline()
    anchor = str(config.get("save_api_uuid") or "").strip() or None
    for slot in slots:
        label = _OPERATE_SLOT_LABELS.get(slot, slot)
        path, api_uuid = await _resolve_operate(
            tenant_id, config=config, action_apis=action_apis, slot=slot
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
                source_type="purchase_receipt",
                source_id=int(source_id or 0),
                target_profile=TARGET_TYPE,
            )
        except BusinessLogicError as exc:
            wrapped = f"金蝶采购入库{label}失败：{exc}"
            from core.services.integration.kingdee_cosmic_response_status import (
                is_cosmic_batch_unsubmit_http_404,
            )

            detail_text = str(exc)
            if slot == "unsubmit" and is_cosmic_batch_unsubmit_http_404(exc):
                logger.warning(
                    "采购入库撤回跳过苍穹 batchUnsubmit（网关 HTTP 404，"
                    "开放平台未发布或未授权时常见）：tenant 继续本地撤回 bill_no={} detail={}",
                    bill_no,
                    wrapped,
                )
                continue
            # 反审后常已是暂存/已删，再调撤销提交会报「必须是已提交」或未找到——跳过继续删单
            if slot == "unsubmit" and (
                "必须是已提交" in detail_text
                or "已提交才能撤销" in detail_text
                or "未查找" in detail_text
                or "未找到" in detail_text
                or "不存在" in detail_text
            ):
                logger.warning(
                    "采购入库撤回跳过苍穹 batchUnsubmit：bill_no={} detail={}",
                    bill_no,
                    wrapped,
                )
                continue
            # 已反审/已删除时允许继续后续步骤
            if slot == "withdraw" and (
                "必须是已审核" in detail_text
                or "已审核才能" in detail_text
                or "不存在" in detail_text
                or "未查找" in detail_text
                or "unaudit" in detail_text.lower()
            ):
                logger.warning(
                    "采购入库撤回跳过苍穹 batchUnaudit：bill_no={} detail={}",
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
                    "采购入库撤回跳过苍穹 batchDelete（远程已无单）：bill_no={} detail={}",
                    bill_no,
                    wrapped,
                )
                continue
            raise BusinessLogicError(wrapped) from exc


async def _relation_for_receipt(
    tenant_id: int, receipt_id: int
) -> Optional[DocumentRelation]:
    return await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type="purchase_receipt",
        source_id=receipt_id,
        target_type=TARGET_TYPE,
    ).first()


async def sync_purchase_receipt_kingdee_after_withdraw(
    tenant_id: int,
    receipt_id: int,
    *,
    acting_user_id: int,
) -> Optional[str]:
    _ = acting_user_id
    from apps.kuaizhizao.constants.purchase_order_type import is_service_purchase_order_type

    receipt = await PurchaseReceipt.get_or_none(
        tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
    )
    if receipt and is_service_purchase_order_type(getattr(receipt, "order_type", None)):
        return None
    relation = await _relation_for_receipt(tenant_id, receipt_id)
    if not relation:
        return None
    _, action_apis, config = await _load_binding_context(tenant_id, receipt_id=receipt_id)
    bill_id = int(relation.target_id or 0)
    bill_no = str(relation.target_code or "").strip()
    form_id = str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID
    # 反审核 → 撤销提交 → 删除远程单并清关联，便于本地改单后重确认重新 add（价税以新单据为准）。
    # 仅反审核/撤销提交会留下同 billno 暂存单，重推会报候选键已存在且金额无法更新。
    withdraw_slots: List[str] = ["withdraw"]
    if _explicit_operate_api_bound(action_apis, config, "unsubmit"):
        withdraw_slots.append("unsubmit")
    else:
        logger.info(
            "采购入库撤回未绑定 batchUnsubmit 接口库条目，仍尝试默认路径 bill_no={}",
            bill_no,
        )
        withdraw_slots.append("unsubmit")
    withdraw_slots.append("delete")
    from core.services.integration.kingdee_warehouse_document_push_config import (
        read_kingdee_push_workflow_bool,
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
                config=config,
                action_apis=action_apis,
                form_id=form_id,
                bill_id=bill_id,
                bill_no=bill_no,
                slots=withdraw_slots,
                source_id=receipt_id,
            )
        await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type="purchase_receipt",
            source_id=receipt_id,
            target_type=TARGET_TYPE,
        ).delete()
    except Exception as exc:
        detail = str(exc).strip() or "金蝶苍穹撤回同步失败"
        logger.warning(
            "采购入库撤回同步苍穹失败 tenant_id={} receipt_id={} blocks_local={} err={}",
            tenant_id,
            receipt_id,
            blocks_local,
            detail,
        )
        if blocks_local:
            raise BusinessLogicError(detail) from exc
        return f"金蝶撤回未完全成功（本地将继续撤回）：{detail}"
    return None


async def sync_purchase_receipt_kingdee_after_delete(
    tenant_id: int,
    receipt_id: int,
    *,
    acting_user_id: int,
) -> None:
    _ = acting_user_id
    from apps.kuaizhizao.constants.purchase_order_type import is_service_purchase_order_type

    receipt = await PurchaseReceipt.get_or_none(
        tenant_id=tenant_id, id=receipt_id, deleted_at__isnull=True
    )
    if receipt and is_service_purchase_order_type(getattr(receipt, "order_type", None)):
        return
    relation = await _relation_for_receipt(tenant_id, receipt_id)
    if not relation:
        return
    _, action_apis, config = await _load_binding_context(tenant_id, receipt_id=receipt_id)
    bill_id = int(relation.target_id or 0)
    bill_no = str(relation.target_code or "").strip()
    form_id = str(config.get("form_id") or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID
    from core.services.data.sync_trigger_kind import (
        SYNC_TRIGGER_KIND_TRIGGER,
        sync_run_trigger_kind,
    )

    try:
        with sync_run_trigger_kind(SYNC_TRIGGER_KIND_TRIGGER):
            await _operate_chain(
                tenant_id=tenant_id,
                config=config,
                action_apis=action_apis,
                form_id=form_id,
                bill_id=bill_id,
                bill_no=bill_no,
                slots=["withdraw", "unsubmit", "delete"],
                source_id=receipt_id,
            )
    except Exception as exc:
        logger.warning(
            "采购入库删除同步苍穹失败 tenant_id={} receipt_id={} err={}",
            tenant_id,
            receipt_id,
            exc,
        )
        raise BusinessLogicError(f"金蝶采购入库删除失败：{exc}") from exc
    await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type="purchase_receipt",
        source_id=receipt_id,
        target_type=TARGET_TYPE,
    ).delete()
