"""SyncPushHub 组件级同步对账：本地单据 vs 金蝶仓穹 IM 单（按 DocumentRelation.billno 查询）。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from loguru import logger

from core.models.integration_config import IntegrationConfig
from core.services.integration.document_push_pipeline import DocumentPushPipeline
from core.services.integration.kingdee_cosmic_api_presets import (
    BIZ_IM_OTHERINBILL,
    BIZ_IM_OTHEROUTBILL,
    BIZ_IM_PURINBILL,
    BIZ_IM_SALOUTBILL,
)
from core.services.integration.kingdee_cosmic_push_adapter import (
    normalize_kingdee_im_billstatus,
    query_kingdee_cosmic_bill_by_billno,
)
from infra.exceptions.exceptions import BusinessLogicError, ValidationError

MAX_RECONCILE_IDS = 50
_QTY_EPS = Decimal("0.0001")

_POSTED_LOCAL_STATUSES = frozenset(
    {
        "已入库",
        "已出库",
        "已领料",
        "COMPLETED",
        "POSTED",
        "CONFIRMED",
    }
)


@dataclass(frozen=True)
class _LocalDoc:
    source_id: int
    local_code: str
    local_status: str
    local_qty: Decimal


ConfigResolver = Callable[[int, int], Awaitable[Dict[str, Any]]]
LocalLoader = Callable[[int, Sequence[int]], Awaitable[Dict[int, _LocalDoc]]]


@dataclass(frozen=True)
class ReconcileSpec:
    source_type: str
    target_type: str
    form_id: str
    doc_label: str
    resolve_config: ConfigResolver
    load_locals: LocalLoader


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except Exception:
        return Decimal("0")


def _qty_equal(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= _QTY_EPS


def _sum_remote_qty(row: Dict[str, Any]) -> Decimal:
    entries = row.get("billentry")
    if not isinstance(entries, list):
        return Decimal("0")
    total = Decimal("0")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("qty")
        if raw is None:
            raw = entry.get("qtyunit")
        total += _dec(raw)
    return total


def _billstatus_label(raw: Any) -> str:
    code = normalize_kingdee_im_billstatus(raw)
    return {
        "A": "A暂存",
        "B": "B已提交",
        "C": "C已审核",
    }.get(code, str(raw or "").strip() or "-")


async def _load_purchase_receipts(
    tenant_id: int, ids: Sequence[int]
) -> Dict[int, _LocalDoc]:
    from apps.kuaizhizao.models.purchase_receipt import PurchaseReceipt

    rows = await PurchaseReceipt.filter(
        tenant_id=tenant_id, id__in=list(ids), deleted_at__isnull=True
    ).all()
    return {
        int(r.id): _LocalDoc(
            source_id=int(r.id),
            local_code=str(r.receipt_code or ""),
            local_status=str(r.status or ""),
            local_qty=_dec(r.total_quantity),
        )
        for r in rows
    }


async def _config_purchase_receipt(tenant_id: int, source_id: int) -> Dict[str, Any]:
    from apps.kuaiconnect.services.document_push.kingdee_purchase_receipt_revoke_service import (
        _load_binding_context,
    )

    _, _, config = await _load_binding_context(tenant_id, receipt_id=int(source_id or 0))
    return config


async def _load_finished_goods(
    tenant_id: int, ids: Sequence[int]
) -> Dict[int, _LocalDoc]:
    from apps.kuaizhizao.models.finished_goods_receipt import FinishedGoodsReceipt

    rows = await FinishedGoodsReceipt.filter(
        tenant_id=tenant_id, id__in=list(ids), deleted_at__isnull=True
    ).all()
    return {
        int(r.id): _LocalDoc(
            source_id=int(r.id),
            local_code=str(r.receipt_code or ""),
            local_status=str(r.status or ""),
            local_qty=_dec(r.total_quantity),
        )
        for r in rows
    }


async def _config_im_warehouse(
    tenant_id: int, source_id: int, *, source_type: str
) -> Dict[str, Any]:
    from apps.kuaiconnect.services.document_push.kingdee_im_warehouse_revoke_service import (
        FINISHED_GOODS_RECEIPT_REVOKE_SPEC,
        OTHER_INBOUND_REVOKE_SPEC,
        OTHER_OUTBOUND_REVOKE_SPEC,
        PRODUCTION_PICKING_REVOKE_SPEC,
        SALES_DELIVERY_REVOKE_SPEC,
        _load_binding_context,
    )

    by_source = {
        "sales_delivery": SALES_DELIVERY_REVOKE_SPEC,
        "other_outbound": OTHER_OUTBOUND_REVOKE_SPEC,
        "other_inbound": OTHER_INBOUND_REVOKE_SPEC,
        "production_picking": PRODUCTION_PICKING_REVOKE_SPEC,
        "finished_goods_receipt": FINISHED_GOODS_RECEIPT_REVOKE_SPEC,
    }
    spec = by_source.get(source_type)
    if not spec:
        raise ValidationError(f"不支持的对比源类型: {source_type}")
    _, _, config = await _load_binding_context(
        tenant_id, spec, source_id=int(source_id or 0)
    )
    return config


async def _load_sales_delivery(
    tenant_id: int, ids: Sequence[int]
) -> Dict[int, _LocalDoc]:
    from apps.kuaizhizao.models.sales_delivery import SalesDelivery

    rows = await SalesDelivery.filter(
        tenant_id=tenant_id, id__in=list(ids), deleted_at__isnull=True
    ).all()
    return {
        int(r.id): _LocalDoc(
            source_id=int(r.id),
            local_code=str(getattr(r, "delivery_code", None) or ""),
            local_status=str(r.status or ""),
            local_qty=_dec(getattr(r, "total_quantity", 0)),
        )
        for r in rows
    }


async def _load_other_outbound(
    tenant_id: int, ids: Sequence[int]
) -> Dict[int, _LocalDoc]:
    from apps.kuaizhizao.models.other_outbound import OtherOutbound

    rows = await OtherOutbound.filter(
        tenant_id=tenant_id, id__in=list(ids), deleted_at__isnull=True
    ).all()
    return {
        int(r.id): _LocalDoc(
            source_id=int(r.id),
            local_code=str(r.outbound_code or ""),
            local_status=str(r.status or ""),
            local_qty=_dec(r.total_quantity),
        )
        for r in rows
    }


async def _load_other_inbound(
    tenant_id: int, ids: Sequence[int]
) -> Dict[int, _LocalDoc]:
    from apps.kuaizhizao.models.other_inbound import OtherInbound

    rows = await OtherInbound.filter(
        tenant_id=tenant_id, id__in=list(ids), deleted_at__isnull=True
    ).all()
    return {
        int(r.id): _LocalDoc(
            source_id=int(r.id),
            local_code=str(getattr(r, "inbound_code", None) or ""),
            local_status=str(r.status or ""),
            local_qty=_dec(getattr(r, "total_quantity", 0)),
        )
        for r in rows
    }


async def _load_production_picking(
    tenant_id: int, ids: Sequence[int]
) -> Dict[int, _LocalDoc]:
    from apps.kuaizhizao.models.production_picking import ProductionPicking
    from apps.kuaizhizao.models.production_picking_item import ProductionPickingItem

    rows = await ProductionPicking.filter(
        tenant_id=tenant_id, id__in=list(ids), deleted_at__isnull=True
    ).all()
    items = await ProductionPickingItem.filter(
        tenant_id=tenant_id,
        picking_id__in=list(ids),
        deleted_at__isnull=True,
    ).all()
    qty_by_picking: Dict[int, Decimal] = {}
    for item in items:
        pid = int(getattr(item, "picking_id", 0) or 0)
        qty_by_picking[pid] = qty_by_picking.get(pid, Decimal("0")) + _dec(
            getattr(item, "picked_quantity", 0)
        )
    return {
        int(r.id): _LocalDoc(
            source_id=int(r.id),
            local_code=str(r.picking_code or ""),
            local_status=str(r.status or ""),
            local_qty=qty_by_picking.get(int(r.id), Decimal("0")),
        )
        for r in rows
    }


def _spec_for(source_type: str) -> ReconcileSpec:
    st = str(source_type or "").strip()
    specs: Dict[str, ReconcileSpec] = {
        "purchase_receipt": ReconcileSpec(
            source_type="purchase_receipt",
            target_type="kingdee_im_purinbill",
            form_id=BIZ_IM_PURINBILL,
            doc_label="采购入库",
            resolve_config=_config_purchase_receipt,
            load_locals=_load_purchase_receipts,
        ),
        "finished_goods_receipt": ReconcileSpec(
            source_type="finished_goods_receipt",
            target_type="kingdee_im_otherinbill",
            form_id=BIZ_IM_OTHERINBILL,
            doc_label="成品入库",
            resolve_config=lambda tid, sid: _config_im_warehouse(
                tid, sid, source_type="finished_goods_receipt"
            ),
            load_locals=_load_finished_goods,
        ),
        "sales_delivery": ReconcileSpec(
            source_type="sales_delivery",
            target_type="kingdee_im_saloutbill",
            form_id=BIZ_IM_SALOUTBILL,
            doc_label="销售出库",
            resolve_config=lambda tid, sid: _config_im_warehouse(
                tid, sid, source_type="sales_delivery"
            ),
            load_locals=_load_sales_delivery,
        ),
        "other_outbound": ReconcileSpec(
            source_type="other_outbound",
            target_type="kingdee_im_otheroutbill",
            form_id=BIZ_IM_OTHEROUTBILL,
            doc_label="其他出库",
            resolve_config=lambda tid, sid: _config_im_warehouse(
                tid, sid, source_type="other_outbound"
            ),
            load_locals=_load_other_outbound,
        ),
        "other_inbound": ReconcileSpec(
            source_type="other_inbound",
            target_type="kingdee_im_otherinbill",
            form_id=BIZ_IM_OTHERINBILL,
            doc_label="其他入库",
            resolve_config=lambda tid, sid: _config_im_warehouse(
                tid, sid, source_type="other_inbound"
            ),
            load_locals=_load_other_inbound,
        ),
        "production_picking": ReconcileSpec(
            source_type="production_picking",
            target_type="kingdee_im_otheroutbill",
            form_id=BIZ_IM_OTHEROUTBILL,
            doc_label="生产领料",
            resolve_config=lambda tid, sid: _config_im_warehouse(
                tid, sid, source_type="production_picking"
            ),
            load_locals=_load_production_picking,
        ),
    }
    spec = specs.get(st)
    if not spec:
        raise ValidationError(
            f"同步对比暂不支持源类型 {st!r}（仅仓储金蝶 IM 外推单据）"
        )
    return spec


def _classify(
    *,
    local: Optional[_LocalDoc],
    bill_no: str,
    remote: Optional[Dict[str, Any]],
    query_error: Optional[str],
) -> Tuple[str, List[str], Optional[str], Optional[str], Optional[str]]:
    """返回 result, mismatch_fields, remote_billno, remote_status, remote_qty_str."""
    if local is None:
        return "local_missing", [], None, None, None
    if query_error:
        return "error", [], bill_no or None, None, None
    if not bill_no:
        return "not_pushed", [], None, None, None
    if remote is None:
        return "remote_missing", [], bill_no, None, None

    remote_status_raw = remote.get("billstatus")
    remote_status = _billstatus_label(remote_status_raw)
    remote_qty = _sum_remote_qty(remote)
    mismatches: List[str] = []
    if not _qty_equal(local.local_qty, remote_qty):
        mismatches.append("qty")
    bill_code = normalize_kingdee_im_billstatus(remote_status_raw)
    local_posted = str(local.local_status or "").strip() in _POSTED_LOCAL_STATUSES
    if local_posted and bill_code and bill_code != "C":
        mismatches.append("status")
    if mismatches:
        return (
            "mismatch",
            mismatches,
            str(remote.get("billno") or bill_no),
            remote_status,
            str(remote_qty),
        )
    return (
        "matched",
        [],
        str(remote.get("billno") or bill_no),
        remote_status,
        str(remote_qty),
    )


async def reconcile_documents(
    tenant_id: int,
    *,
    source_type: str,
    source_ids: Sequence[int],
) -> Dict[str, Any]:
    spec = _spec_for(source_type)
    cleaned: List[int] = []
    seen = set()
    for raw in source_ids:
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            continue
        if sid <= 0 or sid in seen:
            continue
        seen.add(sid)
        cleaned.append(sid)
    if not cleaned:
        raise ValidationError("请提供待对比的本地单据 ID（当前页或勾选）")
    if len(cleaned) > MAX_RECONCILE_IDS:
        raise ValidationError(f"单次对比最多 {MAX_RECONCILE_IDS} 张单据")

    sample_id = cleaned[0]
    try:
        config = await spec.resolve_config(tenant_id, sample_id)
    except Exception as exc:
        logger.warning(
            "document_push_reconcile config failed source={} err={}",
            spec.source_type,
            exc,
        )
        raise BusinessLogicError(
            f"无法读取{spec.doc_label}数据互通连接配置：{exc}"
        ) from exc

    pipeline = DocumentPushPipeline()
    try:
        connection: IntegrationConfig = await pipeline._resolve_connection(
            tenant_id,
            connector_type="kingdee_cosmic",
            config=config,
        )
    except Exception as exc:
        raise BusinessLogicError(f"未找到可用的金蝶连接器：{exc}") from exc

    locals_map = await spec.load_locals(tenant_id, cleaned)

    from apps.kuaizhizao.models.document_relation import DocumentRelation

    relations = await DocumentRelation.filter(
        tenant_id=tenant_id,
        source_type=spec.source_type,
        source_id__in=cleaned,
        target_type=spec.target_type,
        relation_mode="push",
    ).order_by("-id")
    bill_by_source: Dict[int, str] = {}
    for rel in relations:
        sid = int(rel.source_id)
        if sid in bill_by_source:
            continue
        code = str(rel.target_code or "").strip()
        if code:
            bill_by_source[sid] = code

    rows: List[Dict[str, Any]] = []
    summary = {
        "matched": 0,
        "mismatch": 0,
        "not_pushed": 0,
        "remote_missing": 0,
        "local_missing": 0,
        "error": 0,
    }

    for sid in cleaned:
        local = locals_map.get(sid)
        bill_no = bill_by_source.get(sid, "")
        remote: Optional[Dict[str, Any]] = None
        query_error: Optional[str] = None
        if bill_no:
            try:
                remote = await query_kingdee_cosmic_bill_by_billno(
                    connection,
                    form_id=spec.form_id,
                    bill_no=bill_no,
                )
            except Exception as exc:
                query_error = str(exc)
                logger.warning(
                    "document_push_reconcile query failed billno={} err={}",
                    bill_no,
                    exc,
                )

        result, mismatch_fields, remote_billno, remote_status, remote_qty = _classify(
            local=local,
            bill_no=bill_no,
            remote=remote,
            query_error=query_error,
        )
        summary[result] = int(summary.get(result, 0)) + 1
        rows.append(
            {
                "source_id": sid,
                "local_code": local.local_code if local else "",
                "local_status": local.local_status if local else "",
                "local_qty": str(local.local_qty) if local else None,
                "remote_billno": remote_billno,
                "remote_status": remote_status,
                "remote_qty": remote_qty,
                "result": result,
                "mismatch_fields": mismatch_fields,
                "message": query_error,
            }
        )

    return {
        "success": True,
        "source_type": spec.source_type,
        "target_type": spec.target_type,
        "form_id": spec.form_id,
        "doc_label": spec.doc_label,
        "total": len(rows),
        "summary": summary,
        "rows": rows,
    }
