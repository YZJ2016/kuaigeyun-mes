"""工序委外分批收货立应付。"""

from __future__ import annotations

from decimal import Decimal

from apps.kuaicaiwu.constants.finance_source_types import (
    PAYABLE_SOURCE_OUTSOURCE_ORDER_RECEIPT,
)
from apps.kuaizhizao.models.outsource_order import OutsourceOrder
from apps.kuaizhizao.models.outsource_order_receipt import OutsourceOrderReceipt
from apps.kuaizhizao.services.document_recognition import (
    payable_recognition_from_doc,
    should_auto_payable_on_purchase_receipt,
)
from apps.kuaizhizao.utils.document_amount_write import line_total_qty_unit_price
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
async def maybe_auto_payable_for_outsource_order_receipt_batch(
    *,
    tenant_id: int,
    outsource_order_id: int,
    batch_id: int,
    created_by: int,
) -> None:
    from apps.common.app_orm import require_finance_orm

    require_finance_orm()
    row = await OutsourceOrder.filter(
        tenant_id=tenant_id,
        id=int(outsource_order_id),
        deleted_at__isnull=True,
    ).first()
    batch = await OutsourceOrderReceipt.filter(
        tenant_id=tenant_id,
        id=int(batch_id),
        deleted_at__isnull=True,
    ).first()
    if not row or not batch or batch.ledger_posted:
        return
    strategy = payable_recognition_from_doc(row)
    if not should_auto_payable_on_purchase_receipt(strategy):
        return
    unit_price = Decimal(str(row.unit_price or 0))
    qual = Decimal(str(batch.qualified_quantity or 0))
    total_amount = line_total_qty_unit_price(qual, unit_price)
    if total_amount <= 0:
        return

    from apps.kuaicaiwu.services.finance_due_date import resolve_partner_due_date
    from apps.kuaicaiwu.services.finance_integration_hooks import (
        link_finance_document_relation,
        record_finance_accounting_event,
    )
    from apps.kuaicaiwu.services.finance_service import PayableService
    from apps.kuaicaiwu.schemas.finance import PayableCreate

    payable_service = PayableService()
    biz_date = to_site_date(resolve_business_datetime())
    due_date = await resolve_partner_due_date(tenant_id, "supplier", int(row.supplier_id), biz_date)
    payable_data = PayableCreate(
        source_type=PAYABLE_SOURCE_OUTSOURCE_ORDER_RECEIPT,
        source_id=int(batch.id),
        source_code=f"{row.code}-{batch.id}",
        supplier_id=int(row.supplier_id),
        supplier_name=str(row.supplier_name or ""),
        total_amount=float(total_amount),
        paid_amount=0.0,
        remaining_amount=float(total_amount),
        due_date=due_date,
        business_date=biz_date,
        status="未付款",
        notes=f"由工序委外单 {row.code} 第 {batch.id} 批收货自动生成",
    )
    payable = await payable_service.create_payable(
        tenant_id=tenant_id,
        payable_data=payable_data,
        created_by=created_by,
    )
    batch.ledger_posted = True
    await batch.save(update_fields=["ledger_posted", "updated_at"])
    await link_finance_document_relation(
        tenant_id=tenant_id,
        source_type="outsource_order_receipt",
        source_id=int(batch.id),
        source_code=str(row.code or ""),
        target_type="payable",
        target_id=payable.id,
        target_code=getattr(payable, "payable_code", None),
        relation_desc="工序委外收货自动生成应付单",
        created_by=created_by,
    )
    await record_finance_accounting_event(
        tenant_id=tenant_id,
        event_type="OUTSOURCE_ORDER_RECEIPT_TO_PAYABLE",
        source_type="outsource_order_receipt",
        source_id=int(batch.id),
        created_by=created_by,
    )