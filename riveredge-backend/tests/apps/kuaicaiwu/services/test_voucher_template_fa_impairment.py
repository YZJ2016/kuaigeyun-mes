"""固定资产减值凭证模板。"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from apps.kuaicaiwu.services.voucher_template_service import VoucherTemplateService


def test_fa_impairment_event_alias():
    svc = VoucherTemplateService()
    assert svc.EVENT_ALIASES["FA_IMPAIRMENT"] == "fa_impairment"
    assert svc.EVENT_ALIASES["FIXED_ASSET_IMPAIRMENT"] == "fa_impairment"


def test_fa_impairment_default_template_accounts():
    svc = VoucherTemplateService()
    rows = svc.DEFAULT_TEMPLATES["fa_impairment"]
    assert rows[0]["account_code"] == "6701"
    assert rows[1]["account_code"] == "1603"
    assert rows[0]["summary"] == "减值"
    assert rows[1]["summary"] == "减值"


def test_build_draft_lines_from_fa_impairment_event():
    svc = VoucherTemplateService()
    event = MagicMock()
    event.event_type = "FA_IMPAIRMENT"
    event.business_type = "fixed_asset_impairment"
    event.notes = "减值"
    event.amount = Decimal("100")
    event.payload = {}

    debit_account = MagicMock(id=1, account_code="6701", account_name="资产减值损失")
    credit_account = MagicMock(id=2, account_code="1603", account_name="固定资产减值准备")
    debit_account.aux_customer = False
    debit_account.aux_supplier = False
    debit_account.aux_department = False
    credit_account.aux_customer = False
    credit_account.aux_supplier = False
    credit_account.aux_department = False

    async def resolve_side_effect(_tenant_id, code):
        if code == "6701":
            return debit_account
        if code == "1603":
            return credit_account
        return None

    svc._resolve_account = AsyncMock(side_effect=resolve_side_effect)

    lines = asyncio.run(svc.build_draft_lines_from_event(1, event))
    assert len(lines) == 2
    assert lines[0]["account_code"] == "6701"
    assert lines[0]["debit_amount"] == Decimal("100")
    assert lines[0]["credit_amount"] == Decimal("0")
    assert lines[0]["summary"] == "减值"
    assert lines[1]["account_code"] == "1603"
    assert lines[1]["credit_amount"] == Decimal("100")
    assert lines[1]["debit_amount"] == Decimal("0")
    assert lines[1]["summary"] == "减值"
