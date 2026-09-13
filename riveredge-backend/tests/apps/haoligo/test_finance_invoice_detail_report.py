"""发票明细报表：按开票日期展开行。"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.haoligo.services.finance_invoice_detail_report import build_invoice_detail_report_rows


@pytest.mark.asyncio
async def test_build_invoice_detail_report_rows_flattens_lines():
    inv = MagicMock()
    inv.id = 11
    inv.invoice_no = "INV-001"
    inv.invoice_code = "CODE"
    inv.invoice_date = date(2026, 4, 21)
    inv.supplier_id = 3
    inv.status = "已登记"
    inv.total_amount = Decimal("100.00")

    ln = MagicMock()
    ln.id = 101
    ln.invoice_id = 11
    ln.line_no = 1
    ln.material_code = "M1"
    ln.material_name = "垫片"
    ln.spec = "10mm"
    ln.unit = "个"
    ln.quantity = Decimal("2")
    ln.quantity_literal = "2.0"
    ln.invoice_unit_price = Decimal("10.5")
    ln.invoice_unit_price_literal = "10.50"
    ln.tax_amount = Decimal("1.37")
    ln.line_status = "一致"
    ln.price_diff_amount = None
    ln.price_diff_ratio = None

    supplier = MagicMock()
    supplier.id = 3
    supplier.supplier_code = "S01"
    supplier.supplier_name = "测试供应商"

    inv_qs = MagicMock()
    inv_qs.filter.return_value = inv_qs
    inv_qs.exclude.return_value = inv_qs
    inv_qs.order_by.return_value = inv_qs
    inv_qs.all = AsyncMock(return_value=[inv])

    line_qs = MagicMock()
    line_qs.filter.return_value = line_qs
    line_qs.order_by.return_value = line_qs
    line_qs.all = AsyncMock(return_value=[ln])

    supplier_qs = MagicMock()
    supplier_qs.filter.return_value = supplier_qs
    supplier_qs.all = AsyncMock(return_value=[supplier])

    with (
        patch(
            "apps.haoligo.services.finance_invoice_detail_report.HaoligoFinanceInvoice.filter",
            return_value=inv_qs,
        ),
        patch(
            "apps.haoligo.services.finance_invoice_detail_report.HaoligoFinanceSupplier.filter",
            return_value=supplier_qs,
        ),
        patch(
            "apps.haoligo.services.finance_invoice_detail_report.HaoligoFinanceInvoiceLine.filter",
            return_value=line_qs,
        ),
    ):
        rows = await build_invoice_detail_report_rows(
            1,
            invoice_date_from=date(2026, 4, 1),
            invoice_date_to=date(2026, 4, 30),
        )

    assert len(rows) == 1
    assert rows[0]["invoice_no"] == "INV-001"
    assert rows[0]["material_code"] == "M1"
    assert rows[0]["quantity_literal"] == "2.0"
    assert rows[0]["line_amount"] == Decimal("21.0")
    assert rows[0]["supplier_name"] == "测试供应商"
