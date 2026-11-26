"""仓储单据与金蝶关联的本地红灯。

即时库存入站会按金蝶账面覆盖本地批次。本地已过账而金蝶未审核、或本地已撤回而金蝶仍审核时，禁止覆盖。
红灯只看本地状态、金蝶关联和最近一次外推日志，不在拉库存时再打金蝶。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from infra.services.business_config_service import BusinessConfigService

# source_type, 已过账状态, 金蝶 target_type, 业务配置键, 展示名
_TRACKED: Tuple[Tuple[str, Tuple[str, ...], str, str, str], ...] = (
    ("purchase_receipt", ("已入库",), "kingdee_im_purinbill", "kingdee_purchase_receipt_push", "采购入库"),
    ("sales_delivery", ("已出库",), "kingdee_im_saloutbill", "kingdee_sales_delivery_push", "销售出库"),
    ("other_outbound", ("已出库",), "kingdee_im_otheroutbill", "kingdee_other_outbound_push", "其他出库"),
    ("other_inbound", ("已入库",), "kingdee_im_otherinbill", "kingdee_other_inbound_push", "其他入库"),
    (
        "production_picking",
        ("已领料", "已确认"),
        "kingdee_im_otheroutbill",
        "kingdee_production_picking_push",
        "生产领料",
    ),
    (
        "finished_goods_receipt",
        ("已入库",),
        "kingdee_im_otherinbill",
        "kingdee_finished_goods_receipt_push",
        "成品入库",
    ),
)


def classify_push_log(summary: str) -> str:
    """把同步日志摘要分成 push / withdraw / other。"""
    text = str(summary or "")
    if "action=withdraw" in text or "action=unsubmit" in text:
        return "withdraw"
    if "action=submit" in text or "action=submit_audit" in text:
        return "push"
    if "→ kingdee_" in text and "action=" not in text:
        return "push"
    return "other"


def inventory_pull_block_reason(
    *,
    label: str,
    code: str,
    posted: bool,
    has_relation: bool,
    push_enabled: bool,
    last_kind: Optional[str],
    last_status: Optional[str],
) -> Optional[str]:
    """返回阻断原因；无红灯则 None。"""
    if not push_enabled:
        return None
    if posted and not has_relation:
        return f"{label} {code} 已过账，尚未关联金蝶单"
    if posted and has_relation and last_kind == "withdraw" and last_status == "success":
        return f"{label} {code} 本地仍已过账，金蝶最近一次撤回已成功"
    if (not posted) and has_relation and last_kind == "withdraw" and last_status == "failed":
        return f"{label} {code} 本地已撤回，金蝶撤回失败"
    if (not posted) and has_relation and last_kind == "push" and last_status == "success":
        return f"{label} {code} 本地未过账，金蝶仍保留已推送单据"
    return None


def _summary_mentions_document(summary: str, source_type: str, source_id: int) -> bool:
    """sales_delivery/3 不得命中 sales_delivery/33。"""
    token = f"{source_type}/{source_id}"
    start = 0
    while True:
        idx = summary.find(token, start)
        if idx < 0:
            return False
        end = idx + len(token)
        if end >= len(summary) or not summary[end].isdigit():
            return True
        start = idx + 1


async def _latest_push_log(
    tenant_id: int,
    source_type: str,
    source_id: int,
) -> Tuple[Optional[str], Optional[str]]:
    from core.models.sync_run_log import SyncRunLog

    needle = f"{source_type}/{source_id}"
    rows = (
        await SyncRunLog.filter(tenant_id=tenant_id, entity_type="document_push")
        .filter(error_summary__contains=needle)
        .order_by("-id")
        .limit(20)
    )
    for row in rows:
        summary = str(getattr(row, "error_summary", None) or "")
        if not _summary_mentions_document(summary, source_type, source_id):
            continue
        return classify_push_log(summary), str(getattr(row, "status", None) or "")
    return None, None


async def list_inventory_pull_blocker_records(tenant_id: int) -> List[Dict[str, Any]]:
    """列出禁止灌库存的单据（结构化，供强一致编排与运维脚本使用）。"""
    from apps.kuaizhizao.models.document_relation import DocumentRelation
    from apps.kuaizhizao.models.finished_goods_receipt import FinishedGoodsReceipt
    from apps.kuaizhizao.models.other_inbound import OtherInbound
    from apps.kuaizhizao.models.other_outbound import OtherOutbound
    from apps.kuaizhizao.models.production_picking import ProductionPicking
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt
    from apps.kuaizhizao.models.sales_delivery import SalesDelivery

    models: Dict[str, Any] = {
        "purchase_receipt": (PurchaseReceipt, "receipt_code"),
        "sales_delivery": (SalesDelivery, "delivery_code"),
        "other_outbound": (OtherOutbound, "outbound_code"),
        "other_inbound": (OtherInbound, "inbound_code"),
        "production_picking": (ProductionPicking, "picking_code"),
        "finished_goods_receipt": (FinishedGoodsReceipt, "receipt_code"),
    }
    biz = await BusinessConfigService().get_business_config(tenant_id)
    warehouse = (biz.get("parameters") or {}).get("warehouse") or {}
    records: List[Dict[str, Any]] = []
    for source_type, posted_statuses, target_type, config_key, label in _TRACKED:
        raw = warehouse.get(config_key)
        enabled = bool(raw.get("enabled")) if isinstance(raw, dict) else False
        if not enabled:
            continue
        model, code_attr = models[source_type]
        rows: Sequence[Any] = await model.filter(
            tenant_id=tenant_id, deleted_at__isnull=True
        ).all()
        if not rows:
            continue
        ids = [int(row.id) for row in rows]
        rels = await DocumentRelation.filter(
            tenant_id=tenant_id,
            source_type=source_type,
            source_id__in=ids,
            target_type=target_type,
        ).all()
        related_ids = {int(rel.source_id) for rel in rels}
        fg_billtype_ready: Optional[bool] = None
        if source_type == "finished_goods_receipt":
            from apps.kuaiconnect.services.document_push.kingdee_finished_goods_receipt_push_service import (
                resolve_finished_goods_push_config,
            )
            from apps.kuaiconnect.services.document_push.kingdee_warehouse_push_config_enrich import (
                enrich_kingdee_warehouse_push_config,
            )

            fgcfg = await enrich_kingdee_warehouse_push_config(
                tenant_id,
                resolve_finished_goods_push_config(warehouse),
                expected_related_document="finished_goods_receipt",
            )
            billtype = str(
                fgcfg.get("billtype_number") or fgcfg.get("bill_type_number") or ""
            ).strip()
            fg_billtype_ready = bool(billtype) and not billtype.startswith("REPLACE")
        for row in rows:
            code = str(getattr(row, code_attr, None) or row.id)
            posted = str(getattr(row, "status", None) or "") in posted_statuses
            has_relation = int(row.id) in related_ids
            if source_type == "purchase_receipt":
                from apps.kuaiconnect.services.document_push.kingdee_purchase_receipt_push_service import (
                    purchase_receipt_push_skip_reason,
                )

                pr_skip = purchase_receipt_push_skip_reason(
                    row,
                    already_pushed=has_relation,
                )
                if pr_skip == "服务采购入库单不外推金蝶":
                    continue
            if source_type == "finished_goods_receipt" and not fg_billtype_ready:
                # 未配置「生产完工入库」单据类型时无法外推，不应拦全租户即时库存入站
                continue
            last_kind, last_status = await _latest_push_log(tenant_id, source_type, int(row.id))
            reason = inventory_pull_block_reason(
                label=label,
                code=code,
                posted=posted,
                has_relation=has_relation,
                push_enabled=True,
                last_kind=last_kind,
                last_status=last_status,
            )
            if reason:
                records.append(
                    {
                        "reason": reason,
                        "label": label,
                        "code": code,
                        "source_type": source_type,
                        "source_id": int(row.id),
                        "target_type": target_type,
                        "config_key": config_key,
                        "posted": posted,
                        "has_relation": has_relation,
                        "last_push_kind": last_kind,
                        "last_push_status": last_status,
                    }
                )
    return records


async def list_inventory_pull_blockers(tenant_id: int) -> List[str]:
    """列出禁止用金蝶即时库存覆盖本地批次的单据。"""
    records = await list_inventory_pull_blocker_records(tenant_id)
    return [str(r.get("reason") or "") for r in records]
