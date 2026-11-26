"""切换租户发票开立粒度时，将历史另一种粒度发票同步为新粒度。"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List

from loguru import logger
from tortoise.transactions import in_transaction

from apps.kuaicaiwu.config.finance_settlement_contract import (
    SETTLEMENT_MODE_DETAIL,
    SETTLEMENT_MODE_SUMMARY,
)
from apps.kuaicaiwu.models.invoice import Invoice, InvoiceItem
from apps.kuaicaiwu.models.purchase_invoice import PurchaseInvoice
from apps.kuaicaiwu.models.purchase_invoice_item import PurchaseInvoiceItem
from apps.kuaicaiwu.services.invoice_settlement_guard import normalize_settlement_mode
from apps.kuaicaiwu.services.invoice_settlement_policy import (
    get_tenant_invoice_settlement_mode,
)
from apps.kuaicaiwu.services.purchase_receipt_line_finance_occupancy_service import (
    PurchaseReceiptLineFinanceOccupancyService,
    record_purchase_receipt_invoice_occupancy,
)
from apps.kuaicaiwu.services.sales_delivery_line_finance_occupancy_service import (
    record_sales_delivery_invoice_occupancy,
    release_sales_delivery_invoice_occupancy,
)
from apps.kuaicaiwu.services.sales_invoice_detail_occupancy import (
    record_detail_sales_invoice_occupancy_on_approve,
)
from infra.exceptions.exceptions import ValidationError


def _is_approved(review_status: str | None, status: str | None) -> bool:
    rs = str(review_status or "").strip()
    st = str(status or "").strip()
    return rs in ("已审核", "APPROVED", "approved") or st in ("已审核", "approved", "APPROVED")


async def preview_invoice_settlement_mode_migration(
    tenant_id: int,
    target_mode: str,
) -> Dict[str, Any]:
    target = normalize_settlement_mode(target_mode)
    current = await get_tenant_invoice_settlement_mode(tenant_id)
    if target == current:
        return {
            "current_mode": current,
            "target_mode": target,
            "purchase_opposite_count": 0,
            "sales_opposite_count": 0,
            "needs_migration": False,
        }
    opposite = (
        SETTLEMENT_MODE_DETAIL if target == SETTLEMENT_MODE_SUMMARY else SETTLEMENT_MODE_SUMMARY
    )
    purchase_count = await PurchaseInvoice.filter(
        tenant_id=tenant_id,
        settlement_mode=opposite,
        deleted_at__isnull=True,
    ).count()
    sales_count = await Invoice.filter(
        tenant_id=tenant_id,
        category="OUT",
        settlement_mode=opposite,
        deleted_at__isnull=True,
    ).count()
    return {
        "current_mode": current,
        "target_mode": target,
        "purchase_opposite_count": purchase_count,
        "sales_opposite_count": sales_count,
        "needs_migration": purchase_count > 0 or sales_count > 0,
    }


async def migrate_invoices_for_settlement_mode_switch(tenant_id: int, target_mode: str) -> Dict[str, Any]:
    target = normalize_settlement_mode(target_mode)
    current = await get_tenant_invoice_settlement_mode(tenant_id)
    if target == current:
        return {
            "purchase_migrated": 0,
            "sales_migrated": 0,
            "purchase_items_adjusted": 0,
            "sales_items_adjusted": 0,
        }
    opposite = (
        SETTLEMENT_MODE_DETAIL if target == SETTLEMENT_MODE_SUMMARY else SETTLEMENT_MODE_SUMMARY
    )
    preview = await preview_invoice_settlement_mode_migration(tenant_id, target)
    if not preview["needs_migration"]:
        return {
            "purchase_migrated": 0,
            "sales_migrated": 0,
            "purchase_items_adjusted": 0,
            "sales_items_adjusted": 0,
        }

    purchase_ids = list(
        await PurchaseInvoice.filter(
            tenant_id=tenant_id,
            settlement_mode=opposite,
            deleted_at__isnull=True,
        ).values_list("id", flat=True)
    )
    sales_ids = list(
        await Invoice.filter(
            tenant_id=tenant_id,
            category="OUT",
            settlement_mode=opposite,
            deleted_at__isnull=True,
        ).values_list("id", flat=True)
    )

    purchase_items_adjusted = 0
    sales_items_adjusted = 0

    async with in_transaction():
        if purchase_ids:
            await PurchaseInvoice.filter(id__in=purchase_ids, tenant_id=tenant_id).update(
                settlement_mode=target
            )
            if target == SETTLEMENT_MODE_SUMMARY:
                purchase_items_adjusted = await PurchaseInvoiceItem.filter(
                    tenant_id=tenant_id,
                    purchase_invoice_id__in=purchase_ids,
                    deleted_at__isnull=True,
                ).update(source_line_id=None, partner_statement_line_id=None)
                await _rebuild_purchase_invoice_occupancy_after_detail_to_summary(
                    tenant_id, purchase_ids
                )
            else:
                await _rebuild_purchase_invoice_occupancy_after_summary_to_detail(
                    tenant_id, purchase_ids
                )

        if sales_ids:
            await Invoice.filter(id__in=sales_ids, tenant_id=tenant_id).update(settlement_mode=target)
            if target == SETTLEMENT_MODE_SUMMARY:
                sales_items_adjusted = await InvoiceItem.filter(
                    tenant_id=tenant_id,
                    invoice_id__in=sales_ids,
                    deleted_at__isnull=True,
                ).update(source_line_id=None, partner_statement_line_id=None)
                await _rebuild_sales_invoice_occupancy_after_detail_to_summary(tenant_id, sales_ids)
            else:
                await _rebuild_sales_invoice_occupancy_after_summary_to_detail(tenant_id, sales_ids)

    logger.info(
        "租户 {} 发票粒度迁移 {} -> {}：采购 {} 张，销售 {} 张",
        tenant_id,
        opposite,
        target,
        len(purchase_ids),
        len(sales_ids),
    )
    return {
        "purchase_migrated": len(purchase_ids),
        "sales_migrated": len(sales_ids),
        "purchase_items_adjusted": int(purchase_items_adjusted or 0),
        "sales_items_adjusted": int(sales_items_adjusted or 0),
        "from_mode": opposite,
        "to_mode": target,
    }


_MONEY = Decimal("0.01")


def _q_money(val: Any) -> Decimal:
    return Decimal(str(val or 0)).quantize(_MONEY)


def _allocate_weighted_by_doc(
    items: List[Dict[str, Any]],
    *,
    doc_type: str,
    total: Decimal,
) -> Dict[int, Decimal]:
    """按明细行实际价税合计聚合分摊至源单，末单吸收分位尾差；无行额时等权均分。"""
    raw_by_doc: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for it in items:
        if str(it.get("source_doc_type") or "") != doc_type:
            continue
        did = int(it.get("source_doc_id") or 0)
        if did <= 0:
            continue
        line_val = _q_money(it.get("amount") or 0) + _q_money(it.get("tax_amount") or 0)
        raw_by_doc[did] += line_val
    if not raw_by_doc or total <= 0:
        return {}
    doc_ids = list(raw_by_doc.keys())
    weight_sum = sum(raw_by_doc.values(), Decimal("0"))
    use_equal = weight_sum <= 0
    if use_equal:
        weight_sum = Decimal(len(doc_ids))
    allocated = Decimal("0")
    out: Dict[int, Decimal] = {}
    for idx, did in enumerate(doc_ids):
        if idx == len(doc_ids) - 1:
            part = _q_money(total - allocated)
        else:
            w = Decimal("1") if use_equal else raw_by_doc[did]
            part = _q_money(total * (w / weight_sum))
            allocated += part
        if part > 0:
            out[did] = part
    return out


async def _rebuild_purchase_invoice_occupancy_after_detail_to_summary(
    tenant_id: int,
    purchase_invoice_ids: List[int],
) -> None:
    occ_svc = PurchaseReceiptLineFinanceOccupancyService()
    invoices = await PurchaseInvoice.filter(
        id__in=purchase_invoice_ids,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    )
    from apps.kuaicaiwu.models.purchase_receipt_line_finance_occupancy import (
        PurchaseReceiptLineFinanceOccupancy,
    )

    for inv in invoices:
        inv_id = int(inv.id)
        rows = await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            target_doc_type="PurchaseInvoice",
            target_doc_id=inv_id,
            occupancy_kind="invoice",
            deleted_at__isnull=True,
        ).values("purchase_receipt_id", "amount")
        by_receipt: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in rows:
            rid = int(row.get("purchase_receipt_id") or 0)
            if rid <= 0:
                continue
            by_receipt[rid] += Decimal(str(row.get("amount") or 0))
        await occ_svc.soft_delete_by_target(tenant_id, "PurchaseInvoice", inv_id)
        total = _q_money(inv.total_amount or 0)
        if not by_receipt and total > 0:
            items = await PurchaseInvoiceItem.filter(
                tenant_id=tenant_id,
                purchase_invoice_id=inv_id,
                deleted_at__isnull=True,
            ).values("source_doc_type", "source_doc_id", "amount", "tax_amount")
            by_receipt = _allocate_weighted_by_doc(
                list(items), doc_type="purchase_receipt", total=total
            )
        for rid, amt in by_receipt.items():
            if amt <= 0:
                continue
            await record_purchase_receipt_invoice_occupancy(
                tenant_id,
                rid,
                inv_id,
                _q_money(amt),
                line_selections=None,
                allow_append=True,
            )


async def _rebuild_purchase_invoice_occupancy_after_summary_to_detail(
    tenant_id: int,
    purchase_invoice_ids: List[int],
) -> None:
    from apps.kuaicaiwu.models.purchase_receipt_line_finance_occupancy import (
        PurchaseReceiptLineFinanceOccupancy,
    )
    from apps.kuaicaiwu.services.purchase_invoice_detail_occupancy import (
        record_detail_purchase_invoice_occupancy,
    )

    occ_svc = PurchaseReceiptLineFinanceOccupancyService()
    invoices = await PurchaseInvoice.filter(
        id__in=purchase_invoice_ids,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
    )
    for inv in invoices:
        inv_id = int(inv.id)
        # 先快照原占用，防止无 PurchaseInvoiceItem 的历史汇总发票丢失既有占用
        prior_rows = await PurchaseReceiptLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            target_doc_type="PurchaseInvoice",
            target_doc_id=inv_id,
            occupancy_kind="invoice",
            deleted_at__isnull=True,
        ).values("purchase_receipt_id", "amount")
        prior_by_receipt: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in prior_rows:
            rid = int(row.get("purchase_receipt_id") or 0)
            if rid > 0:
                prior_by_receipt[rid] += Decimal(str(row.get("amount") or 0))

        has_line_sources = await PurchaseInvoiceItem.filter(
            tenant_id=tenant_id,
            purchase_invoice_id=inv_id,
            deleted_at__isnull=True,
            source_line_id__not_isnull=True,
        ).exists()
        if has_line_sources:
            await occ_svc.soft_delete_by_target(tenant_id, "PurchaseInvoice", inv_id)
            await record_detail_purchase_invoice_occupancy(tenant_id, inv_id)
            continue

        total = _q_money(inv.total_amount or 0)
        items = await PurchaseInvoiceItem.filter(
            tenant_id=tenant_id,
            purchase_invoice_id=inv_id,
            deleted_at__isnull=True,
        ).values("source_doc_type", "source_doc_id", "amount", "tax_amount")
        by_receipt = _allocate_weighted_by_doc(
            list(items), doc_type="purchase_receipt", total=total
        )
        if not by_receipt:
            # 历史汇总发票无明细行，保留原有占用不清空
            continue
        await occ_svc.soft_delete_by_target(tenant_id, "PurchaseInvoice", inv_id)
        for rid, amt in by_receipt.items():
            if amt <= 0:
                continue
            await record_purchase_receipt_invoice_occupancy(
                tenant_id,
                rid,
                inv_id,
                _q_money(amt),
                line_selections=None,
                allow_append=True,
            )


async def _rebuild_sales_invoice_occupancy_after_detail_to_summary(
    tenant_id: int,
    sales_invoice_ids: List[int],
) -> None:
    from apps.kuaicaiwu.models.sales_delivery_line_finance_occupancy import (
        SalesDeliveryLineFinanceOccupancy,
    )

    invoices = await Invoice.filter(
        id__in=sales_invoice_ids,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        category="OUT",
    )
    for inv in invoices:
        if not _is_approved(inv.review_status, inv.status):
            continue
        inv_id = int(inv.id)
        prior_rows = await SalesDeliveryLineFinanceOccupancy.filter(
            tenant_id=tenant_id,
            target_doc_type="sales_invoice",
            target_doc_id=inv_id,
            occupancy_kind="invoice",
            deleted_at__isnull=True,
        ).values("sales_delivery_id", "amount")
        by_delivery: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in prior_rows:
            did = int(row.get("sales_delivery_id") or 0)
            if did > 0:
                by_delivery[did] += Decimal(str(row.get("amount") or 0))
        await release_sales_delivery_invoice_occupancy(tenant_id, inv_id)
        total = _q_money(inv.total_amount or 0)
        if not by_delivery and total > 0:
            items = await InvoiceItem.filter(
                tenant_id=tenant_id,
                invoice_id=inv_id,
                deleted_at__isnull=True,
            ).values("source_doc_type", "source_doc_id", "amount", "tax_amount")
            by_delivery = _allocate_weighted_by_doc(
                list(items), doc_type="sales_delivery", total=total
            )
        for did, amt in by_delivery.items():
            if amt <= 0:
                continue
            await record_sales_delivery_invoice_occupancy(
                tenant_id,
                sales_delivery_id=did,
                invoice_id=inv_id,
                amount=_q_money(amt),
                line_slices=None,
            )


async def _rebuild_sales_invoice_occupancy_after_summary_to_detail(
    tenant_id: int,
    sales_invoice_ids: List[int],
) -> None:
    invoices = await Invoice.filter(
        id__in=sales_invoice_ids,
        tenant_id=tenant_id,
        deleted_at__isnull=True,
        category="OUT",
    )
    for inv in invoices:
        if not _is_approved(inv.review_status, inv.status):
            continue
        inv_id = int(inv.id)
        has_line_sources = await InvoiceItem.filter(
            tenant_id=tenant_id,
            invoice_id=inv_id,
            deleted_at__isnull=True,
            source_line_id__not_isnull=True,
        ).exists()
        if has_line_sources:
            await release_sales_delivery_invoice_occupancy(tenant_id, inv_id)
            await record_detail_sales_invoice_occupancy_on_approve(tenant_id, inv_id)
            continue
        total = _q_money(inv.total_amount or 0)
        items = await InvoiceItem.filter(
            tenant_id=tenant_id,
            invoice_id=inv_id,
            deleted_at__isnull=True,
        ).values("source_doc_type", "source_doc_id", "amount", "tax_amount")
        by_delivery = _allocate_weighted_by_doc(
            list(items), doc_type="sales_delivery", total=total
        )
        if not by_delivery:
            continue
        await release_sales_delivery_invoice_occupancy(tenant_id, inv_id)
        for did, amt in by_delivery.items():
            if amt <= 0:
                continue
            await record_sales_delivery_invoice_occupancy(
                tenant_id,
                sales_delivery_id=did,
                invoice_id=inv_id,
                amount=_q_money(amt),
                line_slices=None,
            )


async def validate_or_migrate_settlement_mode_change(
    tenant_id: int,
    new_mode: str,
    *,
    migrate_opposite_invoices: bool,
) -> None:
    from apps.kuaicaiwu.services.invoice_settlement_policy import (
        validate_invoice_settlement_mode_change,
    )

    try:
        await validate_invoice_settlement_mode_change(tenant_id, new_mode)
    except ValidationError:
        if not migrate_opposite_invoices:
            raise ValidationError(
                "已存在另一种粒度的发票单据，禁止切换发票开立模式。"
                "保存时可选择同步迁移历史发票后再切换。"
            )
        await migrate_invoices_for_settlement_mode_switch(tenant_id, new_mode)
        await validate_invoice_settlement_mode_change(tenant_id, new_mode)