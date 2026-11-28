"""明细采购发票审核通过后：收票结束回写、已立账价差应付调整。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from loguru import logger

from apps.kuaicaiwu.constants.finance_source_types import (
    PAYABLE_SOURCE_PURCHASE_INVOICE_PRICE_ADJUST,
)
from apps.kuaicaiwu.config.finance_settlement_contract import SETTLEMENT_MODE_DETAIL
from apps.kuaicaiwu.models.payable import Payable
from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
from apps.kuaicaiwu.models.purchase_invoice_item import PurchaseInvoiceItem
from apps.kuaicaiwu.models.purchase_receipt_line_finance_occupancy import (
    PurchaseReceiptLineFinanceOccupancy,
)
from apps.kuaicaiwu.schemas.finance import PayableCreate
from apps.kuaicaiwu.services.finance_service import PayableService
from apps.kuaizhizao.models.purchase_receipt_item import PurchaseReceiptItem
from apps.kuaizhizao.services.document_recognition import (
    resolve_payable_recognition_for_purchase_invoice,
    should_auto_payable_on_purchase_invoice,
)
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.services.business_config_service import BusinessConfigService

_MONEY = Decimal("0.01")
_QTY = Decimal("0.0001")
_KIND_INVOICE = "invoice"

_business_config = BusinessConfigService()
_payable_service = PayableService()


def _q_money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(_MONEY)


def _q_qty(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(_QTY)


async def _sum_invoice_occupied_incl_by_receipt_item(
    tenant_id: int,
    receipt_id: int,
    item_ids: Sequence[int],
) -> dict[int, Decimal]:
    if not item_ids:
        return {}
    rows = await PurchaseReceiptLineFinanceOccupancy.filter(
        tenant_id=tenant_id,
        purchase_receipt_id=int(receipt_id),
        purchase_receipt_item_id__in=list(item_ids),
        occupancy_kind=_KIND_INVOICE,
        deleted_at__isnull=True,
    ).all()
    out: dict[int, Decimal] = {}
    for row in rows:
        iid = int(row.purchase_receipt_item_id)
        out[iid] = _q_money(out.get(iid, Decimal("0")) + _q_money(row.amount))
    return out


async def _line_settlement_gross_by_item_id(
    tenant_id: int,
    receipt_id: int,
    item_ids: Sequence[int],
) -> dict[int, Decimal]:
    from apps.kuaicaiwu.services.purchase_receipt_finance_pull_lines import (
        _purchase_receipt_line_gross_by_item_id,
    )

    _, items, _, line_gross_by_id = await _purchase_receipt_line_gross_by_item_id(
        tenant_id, int(receipt_id)
    )
    wanted = {int(x) for x in item_ids if int(x) > 0}
    return {
        int(iid): _q_money(gross)
        for iid, gross in line_gross_by_id.items()
        if iid in wanted
    }


async def sum_outsource_batch_invoice_occupied_incl(
    tenant_id: int,
    batch_id: int,
) -> Decimal:
    rows = await PurchaseReceiptLineFinanceOccupancy.filter(
        tenant_id=tenant_id,
        purchase_receipt_id=int(batch_id),
        purchase_receipt_item_id=int(batch_id),
        occupancy_kind=_KIND_INVOICE,
        deleted_at__isnull=True,
    ).all()
    return _q_money(sum((_q_money(r.amount) for r in rows), Decimal("0")))


async def refresh_outsource_order_receipt_invoice_receipt_complete(
    tenant_id: int,
    batch_id: int,
) -> bool:
    """委外收货批次收票结束：开票占用价税合计 ≥ 批次可收票上限。"""
    from apps.kuaicaiwu.services.purchase_invoice_pull_service import (
        PurchaseInvoicePullService,
    )
    from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt

    batch = await OutsourceOrderReceipt.get_or_none(
        tenant_id=tenant_id, id=int(batch_id), deleted_at__isnull=True
    )
    if not batch:
        return False
    flag = bool(getattr(batch, "invoice_receipt_complete", False))
    pull_svc = PurchaseInvoicePullService()
    gross = await pull_svc.outsource_order_receipt_settlement_gross(tenant_id, int(batch_id))
    if gross <= 0:
        if flag:
            await OutsourceOrderReceipt.filter(
                tenant_id=tenant_id, id=int(batch_id)
            ).update(invoice_receipt_complete=False)
        return False
    occupied = await sum_outsource_batch_invoice_occupied_incl(tenant_id, int(batch_id))
    complete = occupied + _MONEY >= gross
    if complete == flag:
        return flag
    await OutsourceOrderReceipt.filter(tenant_id=tenant_id, id=int(batch_id)).update(
        invoice_receipt_complete=complete
    )
    return complete


async def refresh_purchase_receipt_items_invoice_receipt_complete(
    tenant_id: int,
    receipt_id: int,
    *,
    item_ids: Optional[Iterable[int]] = None,
) -> List[int]:
    """收票结束：行占用价税合计 ≥ 行可收票上限则置 invoice_receipt_complete。"""
    filters = {
        "tenant_id": tenant_id,
        "receipt_id": int(receipt_id),
        "deleted_at__isnull": True,
    }
    if item_ids is not None:
        ids = [int(x) for x in item_ids if int(x) > 0]
        if not ids:
            return []
        filters["id__in"] = ids
    items = await PurchaseReceiptItem.filter(**filters).all()
    if not items:
        return []
    iids = [int(it.id) for it in items]
    gross_map = await _line_settlement_gross_by_item_id(tenant_id, receipt_id, iids)
    occ_map = await _sum_invoice_occupied_incl_by_receipt_item(tenant_id, receipt_id, iids)
    marked: List[int] = []
    for it in items:
        iid = int(it.id)
        gross = _q_money(gross_map.get(iid, Decimal("0")))
        occ = _q_money(occ_map.get(iid, Decimal("0")))
        if gross <= 0:
            complete = False
        else:
            complete = occ + _MONEY >= gross
        if complete != bool(getattr(it, "invoice_receipt_complete", False)):
            await PurchaseReceiptItem.filter(tenant_id=tenant_id, id=iid).update(
                invoice_receipt_complete=complete
            )
            if complete:
                marked.append(iid)
    return marked


async def _expected_incl_for_invoice_item(
    tenant_id: int,
    receipt_id: int,
    receipt_item_id: int,
    invoice_qty: Decimal,
    *,
    cache: Optional[dict] = None,
) -> Decimal:
    if cache is None:
        cache = {}
    if receipt_id not in cache:
        cache[receipt_id] = {"gross_map": {}, "items": {}}
    entry = cache[receipt_id]
    if receipt_item_id not in entry["gross_map"]:
        loaded = await _line_settlement_gross_by_item_id(
            tenant_id, receipt_id, [receipt_item_id]
        )
        entry["gross_map"].update(loaded)
        entry["gross_map"].setdefault(
            receipt_item_id, loaded.get(receipt_item_id, Decimal("0"))
        )
    gross = _q_money(entry["gross_map"].get(int(receipt_item_id), Decimal("0")))
    if receipt_item_id not in entry["items"]:
        entry["items"][receipt_item_id] = await PurchaseReceiptItem.get_or_none(
            tenant_id=tenant_id, id=int(receipt_item_id), deleted_at__isnull=True
        )
    item = entry["items"][receipt_item_id]
    if not item or gross <= 0:
        return Decimal("0")
    line_qty = _q_qty(item.receipt_quantity or 0)
    qty = _q_qty(invoice_qty)
    if qty <= 0:
        return Decimal("0")
    if line_qty <= 0:
        return gross if qty > 0 else Decimal("0")
    if qty >= line_qty:
        return gross
    return _q_money((gross / line_qty) * qty)


def _actual_incl_for_invoice_item(row: PurchaseInvoiceItem) -> Decimal:
    return _q_money(row.amount) + _q_money(row.tax_amount)


async def compute_purchase_invoice_price_diff_incl(
    tenant_id: int,
    invoice_id: int,
) -> Decimal:
    """相对入库源价，明细发票行价税合计差额（不含优惠调整应付）。"""
    items = await PurchaseInvoiceItem.filter(
        tenant_id=tenant_id,
        purchase_invoice_id=int(invoice_id),
        deleted_at__isnull=True,
    ).order_by("id").all()
    total = Decimal("0")
    cache: dict = {}
    for row in items:
        doc_type = str(row.source_doc_type or "").strip()
        if doc_type != "purchase_receipt":
            continue
        rid = int(row.source_doc_id or 0)
        sid = int(row.source_line_id or 0)
        if rid <= 0 or sid <= 0:
            continue
        qty = _q_qty(row.quantity or 0)
        expected = await _expected_incl_for_invoice_item(
            tenant_id, rid, sid, qty, cache=cache
        )
        actual = _actual_incl_for_invoice_item(row)
        if expected <= 0 and actual <= 0:
            continue
        total += _q_money(actual - expected)
    return _q_money(total)


async def maybe_create_price_diff_adjustment_payable_for_purchase_invoice(
    *,
    tenant_id: int,
    invoice: PurchaseInvoice | Any,
    created_by: int,
) -> Tuple[Optional[int], Optional[str]]:
    """已立账（入库立应付等）：发票与源价不一致时生成价差调整应付。"""
    strategy = await resolve_payable_recognition_for_purchase_invoice(tenant_id, invoice)
    if should_auto_payable_on_purchase_invoice(strategy):
        return None, None

    diff = await compute_purchase_invoice_price_diff_incl(tenant_id, int(invoice.id))
    if abs(diff) < _MONEY:
        return None, None

    existing = await Payable.get_or_none(
        tenant_id=tenant_id,
        source_type=PAYABLE_SOURCE_PURCHASE_INVOICE_PRICE_ADJUST,
        source_id=int(invoice.id),
        deleted_at__isnull=True,
    )
    if existing:
        return int(existing.id), existing.payable_code

    if not await _business_config.check_node_enabled(tenant_id, "payable"):
        return None, None

    from apps.kuaicaiwu.services.finance_due_date import resolve_partner_due_date

    biz_date = getattr(invoice, "invoice_date", None) or to_site_date(resolve_business_datetime())
    due = await resolve_partner_due_date(
        tenant_id, "supplier", int(invoice.supplier_id), biz_date
    )
    payable = await _payable_service.create_payable(
        tenant_id=tenant_id,
        payable_data=PayableCreate(
            source_type=PAYABLE_SOURCE_PURCHASE_INVOICE_PRICE_ADJUST,
            source_id=invoice.id,
            source_code=invoice.invoice_code,
            supplier_id=invoice.supplier_id,
            supplier_name=invoice.supplier_name,
            total_amount=diff,
            paid_amount=Decimal("0.00"),
            remaining_amount=diff,
            due_date=due,
            business_date=biz_date,
            status="未付款",
            invoice_received=True,
            invoice_number=invoice.invoice_number,
            notes=f"采购收票价差调整(发票{invoice.invoice_code},差额{diff})",
        ),
        created_by=created_by,
        submit_review=False,
    )
    try:
        from apps.kuaizhizao.schemas.document_relation import DocumentRelationCreate
        from apps.kuaizhizao.services.document_relation_new_service import DocumentRelationNewService

        rel_svc = DocumentRelationNewService()
        await rel_svc.create_relation(
            tenant_id=tenant_id,
            relation_data=DocumentRelationCreate(
                source_type="purchase_invoice",
                source_id=invoice.id,
                source_code=invoice.invoice_code,
                source_name=None,
                target_type="payable",
                target_id=payable.id,
                target_code=payable.payable_code,
                target_name=None,
                relation_type="source",
                relation_mode="push",
                relation_desc="采购收票价差调整应付",
            ),
            created_by=created_by,
        )
    except Exception as rel_e:
        logger.warning("创建采购发票→价差调整应付 单据关联失败: {}", rel_e)
    return int(payable.id), payable.payable_code


async def finalize_detail_purchase_invoice_after_approve(
    *,
    tenant_id: int,
    invoice_id: int,
    user_id: int,
) -> None:
    invoice = await PurchaseInvoice.get_or_none(
        tenant_id=tenant_id, id=int(invoice_id), deleted_at__isnull=True
    )
    if not invoice:
        return
    mode = str(getattr(invoice, "settlement_mode", "") or "").strip()
    if mode != SETTLEMENT_MODE_DETAIL:
        return

    line_items = await PurchaseInvoiceItem.filter(
        tenant_id=tenant_id,
        purchase_invoice_id=int(invoice_id),
        deleted_at__isnull=True,
    ).all()
    by_receipt: dict[int, set[int]] = {}
    for row in line_items:
        if str(row.source_doc_type or "").strip() != "purchase_receipt":
            continue
        rid = int(row.source_doc_id or 0)
        sid = int(row.source_line_id or 0)
        if rid > 0 and sid > 0:
            by_receipt.setdefault(rid, set()).add(sid)

    for receipt_id, item_id_set in by_receipt.items():
        await refresh_purchase_receipt_items_invoice_receipt_complete(
            tenant_id,
            receipt_id,
            item_ids=item_id_set,
        )

    outsource_batch_ids: set[int] = set()
    for row in line_items:
        if str(row.source_doc_type or "").strip() != "outsource_order_receipt":
            continue
        bid = int(row.source_doc_id or row.source_line_id or 0)
        if bid > 0:
            outsource_batch_ids.add(bid)
    for batch_id in outsource_batch_ids:
        await refresh_outsource_order_receipt_invoice_receipt_complete(tenant_id, batch_id)

    invoice = await PurchaseInvoice.get_or_none(
        tenant_id=tenant_id, id=int(invoice_id), deleted_at__isnull=True
    )
    if not invoice:
        return

    adj_id, _ = await maybe_create_price_diff_adjustment_payable_for_purchase_invoice(
        tenant_id=tenant_id,
        invoice=invoice,
        created_by=user_id,
    )
    if not adj_id:
        return
    from apps.kuaicaiwu.services.finance_audit_workflow import (
        _APPROVED_REVIEW,
        _PENDING_REVIEW,
        _norm_review,
        submit_finance_review,
    )

    payable = await Payable.get_or_none(
        tenant_id=tenant_id, id=int(adj_id), deleted_at__isnull=True
    )
    if not payable:
        return
    rs = _norm_review(getattr(payable, "review_status", None))
    if rs in _APPROVED_REVIEW or rs in _PENDING_REVIEW:
        return
    await submit_finance_review(
        model=Payable,
        tenant_id=tenant_id,
        doc_id=int(adj_id),
        updated_by=user_id,
        doc_label="应付单",
        node_key="payable",
        allow_committed=True,
    )