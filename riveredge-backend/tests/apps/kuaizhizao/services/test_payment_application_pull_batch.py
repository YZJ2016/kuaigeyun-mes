"""付款申请：同供应商多选采购订单/入库合并一张申请。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from apps.kuaizhizao.schemas.payment_application import PaymentApplicationLineCreate
from apps.kuaizhizao.services.payment_application_pull_service import PaymentApplicationPullService
from infra.exceptions.exceptions import BusinessLogicError, ValidationError


@pytest.mark.asyncio
async def test_create_from_purchase_orders_rejects_mixed_supplier():
    svc = PaymentApplicationPullService()
    preview_a = {
        "has_blocking_issues": False,
        "supplier_id": 1,
        "supplier_name": "A",
        "source_code": "PO1",
        "max_push_quantity": 100.0,
    }
    preview_b = {
        "has_blocking_issues": False,
        "supplier_id": 2,
        "supplier_name": "B",
        "source_code": "PO2",
        "max_push_quantity": 50.0,
    }

    with patch.object(
        svc,
        "preview_from_purchase_order",
        new=AsyncMock(side_effect=[preview_a, preview_b]),
    ), patch(
        "apps.kuaizhizao.services.payment_application_pull_service.PurchaseOrder.get",
        new=AsyncMock(),
    ), patch(
        "apps.kuaizhizao.services.payment_application_line_materials.lines_from_purchase_order_items",
        new=AsyncMock(return_value=[]),
    ):
        with pytest.raises(BusinessLogicError, match="同一供应商"):
            await svc.create_from_purchase_orders(1, [10, 20], created_by=1)


@pytest.mark.asyncio
async def test_create_from_purchase_orders_merges_same_supplier():
    svc = PaymentApplicationPullService()
    line = PaymentApplicationLineCreate.model_validate(
        {
            "sourceType": "purchase_order",
            "sourceId": 10,
            "requestAmount": Decimal("100"),
            "lineKind": "prepayment",
        }
    )
    preview = {
        "has_blocking_issues": False,
        "supplier_id": 5,
        "supplier_name": "供应商甲",
        "source_code": "PO1",
        "max_push_quantity": 100.0,
    }
    order = SimpleNamespace(
        id=10, supplier_id=5, department_id=3, department_name="采购部"
    )

    preview_b = {**preview, "source_code": "PO2"}
    order_b = SimpleNamespace(
        id=11, supplier_id=5, department_id=3, department_name="采购部"
    )

    with patch.object(
        svc,
        "preview_from_purchase_order",
        new=AsyncMock(side_effect=[preview, preview_b]),
    ), patch(
        "apps.kuaizhizao.models.purchase_order.PurchaseOrder.get",
        new=AsyncMock(side_effect=[order, order_b, order]),
    ), patch(
        "apps.kuaizhizao.services.payment_application_po_header.resolve_invoice_status_from_purchase_order",
        new=AsyncMock(return_value="发票后补"),
    ), patch(
        "apps.kuaizhizao.services.payment_application_line_materials.lines_from_purchase_order_items",
        new=AsyncMock(return_value=[line]),
    ), patch.object(
        svc._apps,
        "create_application",
        new=AsyncMock(return_value=SimpleNamespace(application_code="PA001")),
    ) as create_mock:
        await svc.create_from_purchase_orders(1, [10, 11], created_by=99)

    create_mock.assert_awaited_once()
    call_args = create_mock.await_args
    create_payload = call_args.args[1]
    assert create_payload.supplier_id == 5
    assert create_payload.application_kind == "prepayment"
    assert len(create_payload.items) == 2


def test_normalize_source_ids_empty_raises():
    with pytest.raises(ValidationError, match="至少选择"):
        PaymentApplicationPullService._normalize_source_ids([])


@pytest.mark.asyncio
async def test_create_from_purchase_receipts_rejects_mixed_supplier():
    svc = PaymentApplicationPullService()
    preview_a = {
        "has_blocking_issues": False,
        "supplier_id": 1,
        "supplier_name": "A",
        "source_code": "RK1",
        "items": [
            {
                "sourceType": "purchase_receipt",
                "sourceId": 1,
                "requestAmount": 10,
                "lineKind": "goods",
            }
        ],
    }
    preview_b = {
        "has_blocking_issues": False,
        "supplier_id": 2,
        "supplier_name": "B",
        "source_code": "RK2",
        "items": [
            {
                "sourceType": "purchase_receipt",
                "sourceId": 2,
                "requestAmount": 20,
                "lineKind": "goods",
            }
        ],
    }

    with patch.object(
        svc,
        "preview_from_purchase_receipt",
        new=AsyncMock(side_effect=[preview_a, preview_b]),
    ):
        with pytest.raises(BusinessLogicError, match="同一供应商"):
            await svc.create_from_purchase_receipts(1, [1, 2], created_by=1)
