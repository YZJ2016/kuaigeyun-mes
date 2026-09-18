"""固定资产折旧凭证模板。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from apps.kuaicaiwu.services.voucher_template_service import VoucherTemplateService


def test_fa_depreciation_event_alias():
    svc = VoucherTemplateService()
    assert svc.EVENT_ALIASES["FA_DEPRECIATION"] == "fa_depreciation"
    assert svc.EVENT_ALIASES["FIXED_ASSET_DEPRECIATION"] == "fa_depreciation"


def test_fa_depreciation_default_template_accounts():
    svc = VoucherTemplateService()
    rows = svc.DEFAULT_TEMPLATES["fa_depreciation"]
    assert rows[0]["account_code"] == "6602"
    assert rows[0]["side"] == "debit"
    assert rows[1]["account_code"] == "1602"
    assert rows[1]["side"] == "credit"


def test_fa_depreciation_template_rows_from_payload():
    rows = VoucherTemplateService._fa_depreciation_template_rows(
        {
            "expense_account_code": "5101",
            "accumulated_depreciation_account_code": "1702",
        },
        summary="2026-09 固定资产折旧",
    )
    assert rows[0]["side"] == "debit"
    assert rows[0]["account_code"] == "5101"
    assert rows[1]["side"] == "credit"
    assert rows[1]["account_code"] == "1702"


def test_build_draft_lines_from_fa_depreciation_event():
    svc = VoucherTemplateService()
    event = MagicMock()
    event.event_type = "FA_DEPRECIATION"
    event.business_type = "fixed_asset"
    event.notes = "2026-09 固定资产折旧 测试资产"
    event.amount = Decimal("1583.33")
    event.payload = {
        "expense_account_code": "5101",
        "accumulated_depreciation_account_code": "1702",
    }

    debit_account = MagicMock(id=1, account_code="5101", account_name="制造费用")
    credit_account = MagicMock(id=2, account_code="1702", account_name="累计摊销")
    for account in (debit_account, credit_account):
        account.aux_customer = False
        account.aux_supplier = False
        account.aux_department = False

    async def resolve_side_effect(_tenant_id, code):
        if code == "5101":
            return debit_account
        if code == "1702":
            return credit_account
        return None

    svc._resolve_account = AsyncMock(side_effect=resolve_side_effect)
    svc._resolve_partner_from_event = AsyncMock(return_value={})

    lines = asyncio.run(svc.build_draft_lines_from_event(1, event))
    assert len(lines) == 2
    assert lines[0]["account_code"] == "5101"
    assert lines[0]["debit_amount"] == Decimal("1583.33")
    assert lines[0]["credit_amount"] == Decimal("0")
    assert lines[1]["account_code"] == "1702"
    assert lines[1]["credit_amount"] == Decimal("1583.33")
    assert lines[1]["debit_amount"] == Decimal("0")
