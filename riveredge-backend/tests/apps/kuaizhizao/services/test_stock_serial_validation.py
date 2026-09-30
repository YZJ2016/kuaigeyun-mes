from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from apps.kuaizhizao.services.inventory_service import InventoryService
from apps.master_data.models.material_serial import MaterialSerial
from infra.exceptions.exceptions import BusinessLogicError


def _locked_query(first_result):
    """spec 141：序列号台账读取须走 select_for_update 行锁。"""
    query = MagicMock()
    query.select_for_update = MagicMock(return_value=query)
    query.first = AsyncMock(return_value=first_result)
    return query


@pytest.mark.asyncio
@pytest.mark.parametrize("record,message", [
    (None, "不存在"),
    (SimpleNamespace(material_id=2, status="in_stock"), "不属于"),
    (SimpleNamespace(material_id=1, status="out_stock"), "不在库"),
])
async def test_invalid_serial_reports_business_error(monkeypatch, record, message):
    query = _locked_query(record)
    monkeypatch.setattr(MaterialSerial, "filter", lambda **kw: query)
    with pytest.raises(BusinessLogicError, match=message):
        await InventoryService._mark_serials_out_stock(1, 1, ["SN-1"])
    query.select_for_update.assert_called_once()


@pytest.mark.asyncio
async def test_valid_serial_is_marked_out_of_stock(monkeypatch):
    record = SimpleNamespace(material_id=1, status="in_stock", save=AsyncMock())
    query = _locked_query(record)
    monkeypatch.setattr(MaterialSerial, "filter", lambda **kw: query)
    ledger = AsyncMock()
    monkeypatch.setattr(
        "apps.kuaizhizao.services.material_serial_document_ledger_service.record_serial_document_ledger",
        ledger,
    )
    await InventoryService._mark_serials_out_stock(1, 1, ["SN-1"])
    ledger.assert_awaited_once()
    assert record.status == "out_stock"
    record.save.assert_awaited_once()
    query.select_for_update.assert_called_once()
