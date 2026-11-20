"""采购入库按订单类型解析打印模板代码。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.kuaizhizao.services.print_service import DocumentPrintService


@pytest.mark.asyncio
async def test_resolve_asset_print_template_code():
    tpl = SimpleNamespace(code="PURCHASE_RECEIPT_PRINT_003")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            DocumentPrintService,
            "_find_print_template",
            AsyncMock(return_value=tpl),
        )
        code = await DocumentPrintService._resolve_purchase_receipt_print_template_code(
            2,
            {"order_type": "资产采购"},
        )
    assert code == "PURCHASE_RECEIPT_PRINT_003"


@pytest.mark.asyncio
async def test_resolve_standard_print_template_code():
    tpl = SimpleNamespace(code="PURCHASE_RECEIPT_PRINT_001")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            DocumentPrintService,
            "_find_print_template",
            AsyncMock(return_value=tpl),
        )
        code = await DocumentPrintService._resolve_purchase_receipt_print_template_code(
            2,
            {"order_type": "标准采购"},
        )
    assert code == "PURCHASE_RECEIPT_PRINT_001"