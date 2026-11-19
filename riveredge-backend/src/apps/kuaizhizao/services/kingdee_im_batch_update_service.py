"""金蝶 im_* 仓储单 batchUpdate：编辑保存与外推复用（须出站绑定 update 接口）。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from apps.kuaizhizao.services.kingdee_im_warehouse_revoke_service import (
    KingdeeImWarehouseRevokeSpec,
    _load_binding_context,
    _operate_chain,
)
from apps.kuaizhizao.models.document_relation import DocumentRelation
from core.services.integration.document_push_pipeline import DocumentPushPipeline
from core.services.integration.kingdee_cosmic_push_adapter import (
    KingdeeCosmicPushAdapter,
    _IM_BILL_QUERY_PATH,
    _first_query_row,
    normalize_kingdee_im_billstatus,
    query_kingdee_cosmic_bill_by_billno,
)
from infra.exceptions.exceptions import BusinessLogicError

PrepareModelFn = Callable[
    [Dict[str, Any]],
    Awaitable[Tuple[Dict[str, Any], str, Dict[str, Any]]],
]

KINGDEE_IM_WAREHOUSE_EDIT_SYNC_STATUSES = frozenset(
    {
        "待出库",
        "待入库",
        "待审核",
        "待领料",
        "待借出",
        "草稿",
        "draft",
        "pending",
    }
)


def attach_kingdee_entry_ids_for_batch_update(
    model: Dict[str, Any],
    *,
    bill_id: int,
    kd_row: Dict[str, Any],
) -> None:
    """batchUpdate 头/分录须带金蝶 id；分录按序或物料编码对齐。"""
    model["id"] = str(int(bill_id))
    bill_no = str(kd_row.get("billno") or model.get("billno") or "").strip()
    if bill_no:
        model["billno"] = bill_no
    kd_entries = kd_row.get("billentry")
    if not isinstance(kd_entries, list):
        kd_entries = []
    local_entries = model.get("billentry")
    if not isinstance(local_entries, list) or not local_entries:
        raise BusinessLogicError("单据无有效明细，无法 batchUpdate 金蝶")
    if len(local_entries) == len(kd_entries):
        for loc, kd in zip(local_entries, kd_entries):
            if not isinstance(kd, dict):
                raise BusinessLogicError("金蝶明细结构异常，无法 batchUpdate")
            raw_eid = kd.get("id")
            if raw_eid is None or str(raw_eid).strip() == "":
                raise BusinessLogicError("金蝶明细缺少 id，无法 batchUpdate")
            loc["id"] = str(raw_eid).strip()
        return
    by_material: Dict[str, list] = {}
    for kd in kd_entries:
        if not isinstance(kd, dict):
            continue
        mat = str(
            kd.get("material_number")
            or kd.get("material_masterid_number")
            or kd.get("materialmasterid_number")
            or ""
        ).strip()
        if not mat:
            continue
        by_material.setdefault(mat, []).append(kd)
    for loc in local_entries:
        if not isinstance(loc, dict):
            continue
        mat = str(loc.get("material_number") or "").strip()
        bucket = by_material.get(mat) or []
        if not bucket:
            raise BusinessLogicError(
                f"金蝶无物料 {mat or '-'} 对应分录，本地与苍穹行不一致，无法 batchUpdate"
            )
        kd = bucket.pop(0)
        raw_eid = kd.get("id")
        if raw_eid is None or str(raw_eid).strip() == "":
            raise BusinessLogicError(f"金蝶物料 {mat} 分录缺少 id，无法 batchUpdate")
        loc["id"] = str(raw_eid).strip()


async def load_im_warehouse_kingdee_binding_context(
    tenant_id: int,
    spec: KingdeeImWarehouseRevokeSpec,
    source_id: int,
) -> Tuple[list, Dict[str, str], Dict[str, Any]]:
    return await _load_binding_context(
        tenant_id, spec, source_id=int(source_id)
    )


async def _query_kingdee_im_row_with_entries(
    connection: Any,
    *,
    form_id: str,
    bill_no: str,
    bill_id: int,
    timeout: float,
) -> Dict[str, Any]:
    kd_row = await query_kingdee_cosmic_bill_by_billno(
        connection,
        form_id=form_id,
        bill_no=bill_no,
        timeout=timeout,
    )
    if not kd_row:
        raise BusinessLogicError(f"金蝶未找到单据 {bill_no or bill_id}，无法 batchUpdate")
    if bill_id <= 0:
        try:
            bill_id = int(str(kd_row.get("id")).strip())
        except (TypeError, ValueError) as exc:
            raise BusinessLogicError("金蝶单据缺少 id，无法 batchUpdate") from exc
    probe = kd_row.get("billentry")
    if not (isinstance(probe, list) and probe):
        query_path = _IM_BILL_QUERY_PATH.get(str(form_id or "").strip())
        if query_path and bill_id > 0:
            adapter = KingdeeCosmicPushAdapter()
            detail_resp = await adapter.call_direct(
                connection,
                query_path,
                {"data": {"id": str(bill_id)}},
                timeout=timeout,
            )
            ok_det, _ = adapter.parse_status(detail_resp)
            if ok_det:
                detail_row = _first_query_row(detail_resp)
                if isinstance(detail_row, dict) and detail_row:
                    kd_row = detail_row
    return kd_row


async def kingdee_im_batch_update_linked_bill(
    *,
    tenant_id: int,
    spec: KingdeeImWarehouseRevokeSpec,
    source_id: int,
    source_type: str,
    relation: DocumentRelation,
    base_config: Dict[str, Any],
    prepare_model: PrepareModelFn,
    dry_run: bool = False,
    action_apis: Optional[Dict[str, str]] = None,
    binding_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """已关联且可编辑：batchUpdate（非删单重建）。"""
    if action_apis is None or binding_config is None:
        _, action_apis, binding_config = await load_im_warehouse_kingdee_binding_context(
            tenant_id, spec, int(source_id)
        )
    merged = {**base_config, **binding_config}
    update_uuid = str((action_apis or {}).get("update") or "").strip()
    if not update_uuid:
        raise BusinessLogicError(
            f"已关联金蝶{spec.doc_label}，编辑同步须在出站绑定配置「更新」接口（苍穹 batchUpdate）"
        )

    config, form_id, model = await prepare_model(merged)
    bill_no = str(relation.target_code or "").strip()
    bill_id = int(relation.target_id or 0)
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "message": f"将 batchUpdate 金蝶{spec.doc_label} bill_no={bill_no or bill_id}",
            "bill_no": bill_no,
            "bill_id": bill_id,
            "action": "update",
            "source_type": source_type,
            "source_id": int(source_id),
        }

    pipeline = DocumentPushPipeline()
    connection = await pipeline._resolve_connection(
        tenant_id,
        connector_type="kingdee_cosmic",
        config=config,
    )
    timeout = float(config.get("timeout") or 30.0)
    timeout = max(1.0, min(timeout, 120.0))

    kd_row = await _query_kingdee_im_row_with_entries(
        connection,
        form_id=form_id,
        bill_no=bill_no,
        bill_id=bill_id,
        timeout=timeout,
    )
    if bill_id <= 0:
        try:
            bill_id = int(str(kd_row.get("id")).strip())
        except (TypeError, ValueError) as exc:
            raise BusinessLogicError("金蝶单据缺少 id，无法 batchUpdate") from exc

    billstatus = normalize_kingdee_im_billstatus(kd_row.get("billstatus"))
    if billstatus == "C":
        raise BusinessLogicError(
            f"金蝶{spec.doc_label}已审核，无法 batchUpdate；请先撤回本地过账或对金蝶反审后再改"
        )
    if billstatus == "B":
        await _operate_chain(
            tenant_id=tenant_id,
            spec=spec,
            config=config,
            action_apis=action_apis or {},
            bill_id=bill_id,
            bill_no=bill_no,
            slots=["unsubmit"],
            source_id=int(source_id),
        )

    attach_kingdee_entry_ids_for_batch_update(
        model, bill_id=bill_id, kd_row=kd_row
    )
    body = {"data": [model]}
    adapter = KingdeeCosmicPushAdapter()
    response = await adapter.call_via_api_library(
        tenant_id=tenant_id,
        api_uuid=update_uuid,
        body=body,
        timeout=timeout,
    )
    ok, message = adapter.parse_status(response)
    if not ok:
        raise BusinessLogicError(message or f"金蝶{spec.doc_label} batchUpdate 失败")

    if int(relation.target_id or 0) != bill_id:
        await DocumentRelation.filter(
            tenant_id=tenant_id,
            id=relation.id,
        ).update(target_id=bill_id)

    return {
        "success": True,
        "source_type": source_type,
        "source_id": int(source_id),
        "bill_id": bill_id,
        "bill_no": bill_no,
        "message": message or "batchUpdate",
        "action": "update",
    }


def relation_branch_should_batch_update(doc_status: str) -> bool:
    return str(doc_status or "").strip() in KINGDEE_IM_WAREHOUSE_EDIT_SYNC_STATUSES


async def kingdee_purchase_receipt_batch_update_linked_bill(
    *,
    tenant_id: int,
    receipt_id: int,
    source_type: str,
    relation: DocumentRelation,
    base_config: Dict[str, Any],
    prepare_model: PrepareModelFn,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """采购入库：binding 与 operate 链独立于 im revoke spec。"""
    from apps.kuaizhizao.services.kingdee_purchase_receipt_push_service import (
        DEFAULT_FORM_ID,
    )
    from apps.kuaizhizao.services.kingdee_purchase_receipt_revoke_service import (
        _load_binding_context,
        _operate_chain,
    )

    _, action_apis, binding_config = await _load_binding_context(
        tenant_id, receipt_id=int(receipt_id)
    )
    merged = {**base_config, **binding_config}
    update_uuid = str((action_apis or {}).get("update") or "").strip()
    if not update_uuid:
        raise BusinessLogicError(
            "已关联金蝶采购入库，编辑同步须在出站绑定配置「更新」接口（苍穹 batchUpdate）"
        )

    config, form_id, model = await prepare_model(merged)
    bill_no = str(relation.target_code or "").strip()
    bill_id = int(relation.target_id or 0)
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "message": f"将 batchUpdate 金蝶采购入库 bill_no={bill_no or bill_id}",
            "bill_no": bill_no,
            "bill_id": bill_id,
            "action": "update",
            "source_type": source_type,
            "source_id": int(receipt_id),
        }

    pipeline = DocumentPushPipeline()
    connection = await pipeline._resolve_connection(
        tenant_id,
        connector_type="kingdee_cosmic",
        config=config,
    )
    timeout = float(config.get("timeout") or 30.0)
    timeout = max(1.0, min(timeout, 120.0))

    kd_row = await _query_kingdee_im_row_with_entries(
        connection,
        form_id=form_id,
        bill_no=bill_no,
        bill_id=bill_id,
        timeout=timeout,
    )
    if bill_id <= 0:
        try:
            bill_id = int(str(kd_row.get("id")).strip())
        except (TypeError, ValueError) as exc:
            raise BusinessLogicError("金蝶采购入库单缺少 id，无法 batchUpdate") from exc

    billstatus = normalize_kingdee_im_billstatus(kd_row.get("billstatus"))
    if billstatus == "C":
        raise BusinessLogicError(
            "金蝶采购入库已审核，无法 batchUpdate；请先撤回本地过账或对金蝶反审后再改"
        )
    if billstatus == "B":
        await _operate_chain(
            tenant_id=tenant_id,
            config=config,
            action_apis=action_apis or {},
            form_id=str(form_id or DEFAULT_FORM_ID).strip() or DEFAULT_FORM_ID,
            bill_id=bill_id,
            bill_no=bill_no,
            slots=["unsubmit"],
            source_id=int(receipt_id),
        )

    attach_kingdee_entry_ids_for_batch_update(
        model, bill_id=bill_id, kd_row=kd_row
    )
    body = {"data": [model]}
    adapter = KingdeeCosmicPushAdapter()
    response = await adapter.call_via_api_library(
        tenant_id=tenant_id,
        api_uuid=update_uuid,
        body=body,
        timeout=timeout,
    )
    ok, message = adapter.parse_status(response)
    if not ok:
        raise BusinessLogicError(message or "金蝶采购入库 batchUpdate 失败")

    if int(relation.target_id or 0) != bill_id:
        await DocumentRelation.filter(
            tenant_id=tenant_id,
            id=relation.id,
        ).update(target_id=bill_id)

    return {
        "success": True,
        "source_type": source_type,
        "source_id": int(receipt_id),
        "bill_id": bill_id,
        "bill_no": bill_no,
        "message": message or "batchUpdate",
        "action": "update",
    }
