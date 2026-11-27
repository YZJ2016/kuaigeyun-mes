"""继电器产线节拍产能可生产自制件（product_ids / products）CRUD 单元测试。"""

from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from apps.ind_relay.api import router as relay_router


@asynccontextmanager
async def _noop_tx():
    yield


def _list_query(items):
    q = MagicMock()
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.all = AsyncMock(return_value=items)
    return q


@pytest.mark.asyncio
async def test_create_line_capacity_syncs_products_and_returns_summary(monkeypatch):
    line = SimpleNamespace(id=10, code="L1", name="一线")
    cap_row = SimpleNamespace(
        id=1,
        production_line_id=10,
        production_line_code="L1",
        production_line_name="一线",
        takt_seconds=Decimal("12"),
        daily_capacity_qty=Decimal("2000"),
        changeover_minutes_default=Decimal("15"),
        is_active=True,
        remarks=None,
    )
    mat_a = SimpleNamespace(id=101, main_code="M-101", code="M-101", name="继电器A")
    mat_b = SimpleNamespace(id=102, main_code="M-102", code="M-102", name="继电器B")
    created_bindings = []

    monkeypatch.setattr(relay_router, "in_transaction", _noop_tx)
    monkeypatch.setattr(relay_router.ProductionLine, "get_or_none", AsyncMock(return_value=line))
    monkeypatch.setattr(relay_router.RelayLineCapacity, "get_or_none", AsyncMock(return_value=None))
    monkeypatch.setattr(relay_router.RelayLineCapacity, "create", AsyncMock(return_value=cap_row))
    monkeypatch.setattr(
        relay_router,
        "load_audit_fields_for_create",
        AsyncMock(
            return_value={
                "created_by": 7,
                "created_by_name": "tester",
                "updated_by": 7,
                "updated_by_name": "tester",
            }
        ),
    )
    monkeypatch.setattr(
        relay_router,
        "load_audit_fields_for_update",
        AsyncMock(return_value={"updated_by": 7, "updated_by_name": "tester"}),
    )
    monkeypatch.setattr(
        relay_router.Material, "filter", MagicMock(return_value=_list_query([mat_a, mat_b]))
    )
    monkeypatch.setattr(
        relay_router.RelayLineProduct, "filter", MagicMock(return_value=_list_query([]))
    )

    async def _fake_create_binding(**kwargs):
        created_bindings.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(relay_router.RelayLineProduct, "create", _fake_create_binding)

    resp = await relay_router.create_line_capacity(
        body=relay_router.LineCapacityCreate(
            production_line_id=10,
            takt_seconds=12,
            daily_capacity_qty=2000,
            changeover_minutes_default=15,
            product_ids=[101, 102, 101],
        ),
        tenant_id=1,
        current_user=SimpleNamespace(id=7),
    )

    assert resp.product_ids == [101, 102]
    assert resp.product_count == 2
    assert [(p.id, p.code, p.name) for p in resp.products] == [
        (101, "M-101", "继电器A"),
        (102, "M-102", "继电器B"),
    ]
    assert len(created_bindings) == 2
    assert created_bindings[0]["created_by"] == 7
    assert created_bindings[0]["created_by_name"] == "tester"


@pytest.mark.asyncio
async def test_sync_line_products_rejects_foreign_tenant_material(monkeypatch):
    monkeypatch.setattr(
        relay_router.Material,
        "filter",
        MagicMock(return_value=_list_query([SimpleNamespace(id=101, main_code="M-101", code="M-101", name="A")])),
    )
    with pytest.raises(HTTPException) as exc_info:
        await relay_router._sync_line_products(1, 10, [101, 999], 7)
    assert exc_info.value.status_code == 400
    assert "999" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_update_line_capacity_preserves_products_when_omitted_and_updates_when_given(monkeypatch):
    cap_row = SimpleNamespace(
        id=1,
        production_line_id=10,
        production_line_code="L1",
        production_line_name="一线",
        takt_seconds=Decimal("12"),
        daily_capacity_qty=Decimal("2000"),
        changeover_minutes_default=Decimal("15"),
        is_active=True,
        remarks=None,
        save=AsyncMock(),
    )
    existing_binding = SimpleNamespace(
        id=50,
        production_line_id=10,
        product_id=101,
        product_code="M-101",
        product_name="继电器A",
        deleted_at=None,
        save=AsyncMock(),
    )

    monkeypatch.setattr(relay_router, "in_transaction", _noop_tx)
    monkeypatch.setattr(relay_router.RelayLineCapacity, "get_or_none", AsyncMock(return_value=cap_row))
    monkeypatch.setattr(
        relay_router,
        "load_audit_fields_for_update",
        AsyncMock(return_value={"updated_by": 7, "updated_by_name": "tester"}),
    )
    monkeypatch.setattr(
        relay_router,
        "load_audit_fields_for_create",
        AsyncMock(
            return_value={
                "created_by": 7,
                "created_by_name": "tester",
                "updated_by": 7,
                "updated_by_name": "tester",
            }
        ),
    )
    monkeypatch.setattr(
        relay_router.RelayLineProduct,
        "filter",
        MagicMock(return_value=_list_query([existing_binding])),
    )

    # 1) Omitting product_ids (e.g. toggling is_active) preserves existing bindings
    resp_toggle = await relay_router.update_line_capacity(
        row_id=1,
        body=relay_router.LineCapacityUpdate(is_active=False),
        tenant_id=1,
        current_user=SimpleNamespace(id=7),
    )
    assert resp_toggle.is_active is False
    assert resp_toggle.product_ids == [101]
    assert existing_binding.deleted_at is None

    # 2) Passing product_ids=[102] soft-deletes 101 and creates 102
    mat_b = SimpleNamespace(id=102, main_code="M-102", code="M-102", name="继电器B")
    monkeypatch.setattr(
        relay_router.Material, "filter", MagicMock(return_value=_list_query([mat_b]))
    )
    create_mock = AsyncMock()
    monkeypatch.setattr(relay_router.RelayLineProduct, "create", create_mock)

    resp_replace = await relay_router.update_line_capacity(
        row_id=1,
        body=relay_router.LineCapacityUpdate(product_ids=[102]),
        tenant_id=1,
        current_user=SimpleNamespace(id=7),
    )
    assert resp_replace.product_ids == [102]
    assert existing_binding.deleted_at is not None
    create_mock.assert_awaited_once()
