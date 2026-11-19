"""Tests for purchase requisition → purchase order required date resolution."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.kuaizhizao.services.purchase_requisition_service import PurchaseRequisitionService
from apps.kuaizhizao.services import purchase_requisition_service as requisition_module


def _item(required_date=None):
    return SimpleNamespace(required_date=required_date)


def test_resolve_requisition_item_required_date_prefers_line():
    item = _item(date(2026, 8, 18))
    resolved = PurchaseRequisitionService._resolve_requisition_item_required_date(
        item,
        date(2026, 4, 3),
        date(2026, 4, 2),
    )
    assert resolved == date(2026, 8, 18)


def test_resolve_requisition_item_required_date_falls_back_to_header():
    item = _item(None)
    resolved = PurchaseRequisitionService._resolve_requisition_item_required_date(
        item,
        date(2026, 8, 18),
        date(2026, 4, 2),
    )
    assert resolved == date(2026, 8, 18)


def test_resolve_requisition_item_required_date_falls_back_to_today():
    item = _item(None)
    resolved = PurchaseRequisitionService._resolve_requisition_item_required_date(
        item,
        None,
        date(2026, 4, 2),
    )
    assert resolved == date(2026, 4, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quantities,occupied,pullable_only,expected_ids,triplet",
    [
        ([4, 6], {1: 4}, True, [2], (10, 4, 6)),
        ([10], {1: 4}, True, [1], (10, 4, 6)),
        ([4, 6], {1: 4, 2: 6}, True, [], None),
        ([4, 6], {1: 4, 2: 6}, False, [2], (10, 10, 0)),
    ],
)
async def test_open_lines_use_actual_occupancy_and_group_split_rows(
    monkeypatch, quantities, occupied, pullable_only, expected_ids, triplet,
):
    req = SimpleNamespace(
        id=11, requisition_code="PR-11", status="已通过",
        review_status="已通过", requisition_date=date(2026, 11, 19), applicant_name="Operator",
    )
    rows = [
        SimpleNamespace(
            id=index, requisition_id=11, material_id=5,
            quantity=Decimal(qty), purchase_order_id=100 if index in occupied else None,
            material_code="M-5", material_name="Material", material_spec=None,
            unit="件", required_date=None, supplier_id=7,
        )
        for index, qty in enumerate(quantities, 1)
    ]
    req_query = MagicMock()
    req_query.filter.return_value = req_query
    req_query.only = AsyncMock(return_value=[req])
    item_query = MagicMock()
    item_query.all = AsyncMock(return_value=rows)
    monkeypatch.setattr(requisition_module.PurchaseRequisition, "filter", MagicMock(return_value=req_query))
    monkeypatch.setattr(requisition_module.PurchaseRequisitionItem, "filter", MagicMock(return_value=item_query))
    monkeypatch.setattr(requisition_module, "requisition_open_line_can_push", lambda *args, **kwargs: True)
    service = PurchaseRequisitionService()
    monkeypatch.setattr(
        service, "_occupied_purchase_order_qty_by_requisition_item_ids",
        AsyncMock(return_value={key: Decimal(value) for key, value in occupied.items()}),
    )
    result = await service.list_purchase_order_pull_lines(1, pullable_only=pullable_only)
    assert [row["id"] for row in result["data"]] == expected_ids
    for row in result["data"]:
        assert (
            row["suggested_quantity"], row["pushed_quantity"], row["remaining_quantity"],
        ) == triplet
        assert row["document_date"] == "2026-11-19"
